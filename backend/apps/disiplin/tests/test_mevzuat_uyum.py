"""Mevzuat uyum düzeltmeleri (2026-09 gözden geçirmesi) — md. 157/7, 163/2, 169, 170,
171, 172/1-a, 182, 191, 197.

Her test, gözden geçirmede yeniden üretilen bir kusurun artık OLUŞMADIĞINI sabitler.
"""

from __future__ import annotations

from datetime import date

import pytest

from apps.disiplin import discipline_periods, selectors, services
from apps.disiplin import documents as doc_engine
from apps.disiplin.models import (
    AppealResult,
    ApprovalAuthority,
    CaseStage,
    DecisionApprovalStatus,
    DisciplineCase,
    DisciplineDecision,
    DocumentType,
    PenaltyType,
    PrincipalDecision,
)
from apps.disiplin.tests.factories import (
    DisciplineDecisionTypeFactory,
    PersonnelFactory,
    SchoolYearFactory,
    StudentFactory,
    approve,
)
from apps.okul.models import Holiday, HolidayKind, SchoolYear
from apps.okul.services import persons
from apps.okul.services.calendar import is_school_open_day, is_working_day, seed_holidays

pytestmark = pytest.mark.django_db


def _case(
    *, refer: bool = True, student_ids: list[int] | None = None
) -> tuple[DisciplineCase, int]:
    SchoolYearFactory()
    if student_ids is None:
        student_ids = [StudentFactory().pk]
    case = services.create_case(
        petition_date=date(2026, 5, 18),
        petitioner_name="İdare",
        petitioner_role="IDARE",
        summary="olay",
        student_ids=student_ids,
    )
    if refer:
        services.add_event(
            case,
            CaseStage.DECIDED,
            date(2026, 5, 19),
            override=True,
            override_reason="Rehberlik atlandı.",
            principal_decisions=[PrincipalDecision.DISCIPLINE_COMMITTEE],
        )
    return case, student_ids[0]


def _final_decision(
    penalty: str = PenaltyType.REPRIMAND, **kwargs: object
) -> tuple[DisciplineCase, DisciplineDecision]:
    case, sid = _case()
    d = services.record_decision(
        case,
        student_id=sid,
        penalty_type=penalty,
        decision_date=date(2026, 5, 22),
        **kwargs,  # type: ignore[arg-type]
    )
    approve(d)
    services.notify_decision(d, notified_on=date(2026, 5, 22))
    return case, d


# ---------------------------------------------------------------------------
# md. 163/2 — ceza yalnız kurulda görüşülüp karara bağlanan dosyada
# ---------------------------------------------------------------------------
def test_kurula_sevksiz_dosyaya_ceza_girilemez() -> None:
    case, sid = _case(refer=False)
    with pytest.raises(ValueError, match="md. 163/2"):
        services.record_decision(
            case,
            student_id=sid,
            penalty_type=PenaltyType.REPRIMAND,
            decision_date=date(2026, 5, 20),
        )


def test_kapali_dosyaya_ceza_girilemez() -> None:
    case, sid = _case(refer=False)
    services.add_event(
        case,
        CaseStage.DECIDED,
        date(2026, 5, 19),
        override=True,
        override_reason="x",
        principal_decisions=[PrincipalDecision.WRITTEN_WARNING],
    )
    case.refresh_from_db()
    assert case.current_stage == CaseStage.CLOSED
    with pytest.raises(ValueError, match="kapatılmış"):
        services.record_decision(
            case,
            student_id=sid,
            penalty_type=PenaltyType.REPRIMAND,
            decision_date=date(2026, 5, 20),
        )


def test_karar_tarihi_sevkten_once_olamaz() -> None:
    case, sid = _case()
    with pytest.raises(ValueError, match="sevk tarihinden önce"):
        services.record_decision(
            case,
            student_id=sid,
            penalty_type=PenaltyType.REPRIMAND,
            decision_date=date(2026, 5, 18),
        )


# ---------------------------------------------------------------------------
# md. 163/2, 169/2 — onaysız karar tebliğ edilemez / kesinleşemez / puan düşürmez
# ---------------------------------------------------------------------------
def test_onaysiz_karar_teblig_edilemez_ve_kesinlesmez() -> None:
    case, sid = _case()
    d = services.record_decision(
        case,
        student_id=sid,
        penalty_type=PenaltyType.SCHOOL_CHANGE,
        decision_date=date(2026, 5, 20),
    )
    with pytest.raises(ValueError, match="onaylanmadan tebliğ"):
        services.notify_decision(d, notified_on=date(2026, 5, 21))
    final, reason = selectors.decision_is_final(d, today=date(2026, 7, 1))
    assert final is False and "onaylanmadı" in reason
    assert selectors.behavior_point_for_student(sid) == 100
    approve(d)
    assert selectors.behavior_point_for_student(sid) == 60  # okul değiştirme −40


def test_teblig_tarihi_onaydan_once_olamaz() -> None:
    case, sid = _case()
    d = services.record_decision(
        case, student_id=sid, penalty_type=PenaltyType.REPRIMAND, decision_date=date(2026, 5, 20)
    )
    services.set_decision_approval(d, approval_status="APPROVED", approved_on=date(2026, 5, 22))
    with pytest.raises(ValueError, match="onay tarihinden önce"):
        services.notify_decision(d, notified_on=date(2026, 5, 21))


def test_teblig_edilmis_karar_onaysiza_dondurulemez() -> None:
    _case_, d = _final_decision()
    with pytest.raises(ValueError, match="onaysız duruma"):
        services.set_decision_approval(d, approval_status="PENDING")


# ---------------------------------------------------------------------------
# md. 169/4 — itiraz sonucu kesindir
# ---------------------------------------------------------------------------
def test_sonuclanmis_itiraza_yeniden_itiraz_ve_yeniden_sonuc_yok() -> None:
    _c, d = _final_decision()
    ap = services.file_appeal(d, filed_on=date(2026, 5, 25), filed_by_role="PARENT")
    services.resolve_appeal(ap, result=AppealResult.UPHELD, resulted_on=date(2026, 6, 5))
    with pytest.raises(ValueError, match="md. 169/4"):
        services.file_appeal(d, filed_on=date(2026, 6, 8), filed_by_role="PARENT")
    with pytest.raises(ValueError, match="md. 169/4"):
        services.resolve_appeal(ap, result=AppealResult.OVERTURNED, resulted_on=date(2026, 6, 9))


def test_itiraz_tarihi_teblig_oncesi_olamaz() -> None:
    _c, d = _final_decision()
    with pytest.raises(ValueError, match="tebliğ tarihinden önce"):
        services.file_appeal(d, filed_on=date(2026, 5, 21), filed_by_role="PARENT")


def test_18_yas_itiraz_kontrolu() -> None:
    _c, d = _final_decision()
    d.student.birth_date = date(2008, 5, 26)
    d.student.save()
    with pytest.raises(ValueError, match="18 yaşını tamamlamamış"):
        services.file_appeal(d, filed_on=date(2026, 5, 25), filed_by_role="STUDENT_ADULT")
    ap = services.file_appeal(d, filed_on=date(2026, 5, 26), filed_by_role="STUDENT_ADULT")
    assert ap.pk is not None


def test_cezasiz_karara_itiraz_yok() -> None:
    _c, d = _final_decision(PenaltyType.NO_PENALTY)
    with pytest.raises(ValueError, match="itiraz yolu yoktur"):
        services.file_appeal(d, filed_on=date(2026, 5, 25), filed_by_role="PARENT")


# ---------------------------------------------------------------------------
# md. 170, 200/Ç — "değiştirildi" sonucu ceza ve puanı günceller
# ---------------------------------------------------------------------------
def test_itirazda_degistirilen_ceza_puani_gunceller() -> None:
    _c, d = _final_decision(PenaltyType.SHORT_TERM_SUSPENSION, suspension_days=3)
    sid = d.student_id
    assert selectors.behavior_point_for_student(sid) == 80
    ap = services.file_appeal(d, filed_on=date(2026, 5, 25), filed_by_role="PARENT")
    with pytest.raises(ValueError, match="yeni ceza"):
        services.resolve_appeal(ap, result=AppealResult.REDUCED, resulted_on=date(2026, 6, 5))
    services.resolve_appeal(
        ap,
        result=AppealResult.REDUCED,
        resulted_on=date(2026, 6, 5),
        new_penalty_type=PenaltyType.REPRIMAND,
    )
    d.refresh_from_db()
    ap.refresh_from_db()
    assert d.penalty_type == PenaltyType.REPRIMAND
    assert d.suspension_days is None
    assert d.behavior_point_deduction == 10
    assert ap.previous_penalty_type == PenaltyType.SHORT_TERM_SUSPENSION
    assert selectors.behavior_point_for_student(sid) == 90


def test_ilce_onayinda_okul_degistirme_degistirilebilir() -> None:
    case, sid = _case()
    d = services.record_decision(
        case,
        student_id=sid,
        penalty_type=PenaltyType.SCHOOL_CHANGE,
        decision_date=date(2026, 5, 20),
    )
    services.set_decision_approval(
        d,
        approval_status="APPROVED",
        approved_on=date(2026, 5, 29),
        modified_penalty_type=PenaltyType.SHORT_TERM_SUSPENSION,
        modified_suspension_days=5,
    )
    d.refresh_from_db()
    assert d.penalty_type == PenaltyType.SHORT_TERM_SUSPENSION
    assert d.behavior_point_deduction == 20
    # Onaylayan merci ilçe kaldı → itiraz il kurulunda (md. 169/4).
    assert d.approval_authority == ApprovalAuthority.DISTRICT_BOARD
    services.notify_decision(d, notified_on=date(2026, 6, 1))
    ap = services.file_appeal(d, filed_on=date(2026, 6, 2), filed_by_role="PARENT")
    assert ap.appeal_authority == ApprovalAuthority.PROVINCIAL_BOARD


def test_mudur_okul_kurulu_kararini_degistiremez() -> None:
    case, sid = _case()
    d = services.record_decision(
        case, student_id=sid, penalty_type=PenaltyType.REPRIMAND, decision_date=date(2026, 5, 20)
    )
    with pytest.raises(ValueError, match="md. 197"):
        services.set_decision_approval(
            d,
            approval_status="APPROVED",
            approved_on=date(2026, 5, 21),
            modified_penalty_type=PenaltyType.NO_PENALTY,
        )


def test_bozulan_karar_yeniden_onaylanamaz() -> None:
    _c, d = _final_decision()
    ap = services.file_appeal(d, filed_on=date(2026, 5, 25), filed_by_role="PARENT")
    services.resolve_appeal(ap, result=AppealResult.OVERTURNED, resulted_on=date(2026, 6, 1))
    d.refresh_from_db()
    with pytest.raises(ValueError, match="bozulmuş"):
        services.set_decision_approval(d, approval_status="APPROVED", approved_on=date(2026, 6, 2))


# ---------------------------------------------------------------------------
# md. 197 — bir defa iade; ilçe kararına itiraz il kurulunda
# ---------------------------------------------------------------------------
def test_md197_bir_defa_iade() -> None:
    case, sid = _case()
    d = services.record_decision(
        case, student_id=sid, penalty_type=PenaltyType.REPRIMAND, decision_date=date(2026, 5, 20)
    )
    services.record_principal_review(d, action="RETURN", reason="a", decided_on=date(2026, 5, 21))
    # Kurul kararı değiştirip yeniden sunsa (PENDING) bile ikinci iade yok.
    services.set_decision_approval(d, approval_status="PENDING")
    with pytest.raises(ValueError, match="bir kez iade"):
        services.record_principal_review(
            d, action="RETURN", reason="b", decided_on=date(2026, 5, 25)
        )


def test_md197_ilce_sevkinde_itiraz_il_kurulunda() -> None:
    case, sid = _case()
    d = services.record_decision(
        case, student_id=sid, penalty_type=PenaltyType.REPRIMAND, decision_date=date(2026, 5, 20)
    )
    services.record_principal_review(d, action="RETURN", reason="a", decided_on=date(2026, 5, 21))
    services.record_principal_review(
        d, action="REFER", reason="ısrar", decided_on=date(2026, 5, 26)
    )
    d.refresh_from_db()
    assert d.approval_status == DecisionApprovalStatus.REFERRED_TO_DISTRICT
    assert d.referred_to_district is True
    assert "a" in d.return_reason and "ısrar" in d.return_reason  # iki gerekçe de korunur
    # İlçe kurulu kararı bağlar (APPROVED) → itiraz il kurulunda (md. 169/4, 202/1-b).
    services.set_decision_approval(d, approval_status="APPROVED", approved_on=date(2026, 6, 5))
    services.notify_decision(d, notified_on=date(2026, 6, 8))
    ap = services.file_appeal(d, filed_on=date(2026, 6, 9), filed_by_role="PARENT")
    assert ap.appeal_authority == ApprovalAuthority.PROVINCIAL_BOARD


# ---------------------------------------------------------------------------
# md. 171/3, 157/7 — kaldırılan/cezasız karar "önceki ceza" sayılmaz
# ---------------------------------------------------------------------------
def test_bozulan_ve_cezasiz_karar_onceki_ceza_ve_triajda_sayilmaz() -> None:
    SchoolYearFactory()
    sid = StudentFactory().pk
    case1, _ = _case(student_ids=[sid])
    d1 = services.record_decision(
        case1, student_id=sid, penalty_type=PenaltyType.REPRIMAND, decision_date=date(2026, 5, 22)
    )
    approve(d1)
    services.notify_decision(d1, notified_on=date(2026, 5, 22))
    ap = services.file_appeal(d1, filed_on=date(2026, 5, 25), filed_by_role="PARENT")
    services.resolve_appeal(ap, result=AppealResult.OVERTURNED, resulted_on=date(2026, 6, 1))
    case2, _ = _case(student_ids=[sid])
    approve(
        services.record_decision(
            case2,
            student_id=sid,
            penalty_type=PenaltyType.NO_PENALTY,
            decision_date=date(2026, 5, 22),
        )
    )
    history = selectors.student_discipline_history(sid)
    assert history.penalty_count == 0
    case3, _ = _case(student_ids=[sid])
    d3 = services.record_decision(
        case3, student_id=sid, penalty_type=PenaltyType.REPRIMAND, decision_date=date(2026, 6, 3)
    )
    assert d3.prior_penalties_summary == ""


def test_md171_ceza_kaldirma_puan_iadesi_ve_geri_alma() -> None:
    _c, d = _final_decision()
    sid = d.student_id
    ap = services.file_appeal(d, filed_on=date(2026, 5, 25), filed_by_role="PARENT")
    with pytest.raises(ValueError, match="kesinleşmiş"):
        services.remove_penalty(d, removed_on=date(2026, 6, 20))  # itiraz sürüyor
    services.resolve_appeal(ap, result=AppealResult.UPHELD, resulted_on=date(2026, 6, 5))
    assert selectors.behavior_point_for_student(sid) == 90
    services.remove_penalty(d, removed_on=date(2026, 6, 20), note="Öğretmenler kurulu 20.06")
    assert selectors.behavior_point_for_student(sid) == 100
    assert selectors.student_discipline_history(sid).penalty_count == 0
    services.undo_penalty_removal(d)
    assert selectors.behavior_point_for_student(sid) == 90


# ---------------------------------------------------------------------------
# md. 169 — aşama olayıyla kapanış, kapanış uygunluğunu delemez
# ---------------------------------------------------------------------------
def test_kapatildi_olayi_uygunluk_denetimini_atlayamaz() -> None:
    case, sid = _case()
    services.record_decision(
        case, student_id=sid, penalty_type=PenaltyType.REPRIMAND, decision_date=date(2026, 5, 20)
    )
    services.add_event(
        case,
        CaseStage.COMMITTEE_DONE,
        date(2026, 5, 20),
        committee_decision_type=DisciplineDecisionTypeFactory(),
        committee_decision_text="kınama",
    )
    with pytest.raises(ValueError, match="kapatılamaz"):
        services.add_event(case, CaseStage.CLOSED, date(2026, 5, 21))
    ev = services.add_event(
        case, CaseStage.CLOSED, date(2026, 5, 21), override=True, override_reason="Nakil gitti"
    )
    assert ev.is_override is True and ev.override_reason == "Nakil gitti"


# ---------------------------------------------------------------------------
# md. 157/7, 157/7-e — yazılı uyarı yalnız ilk kez
# ---------------------------------------------------------------------------
def test_ikinci_kez_yazili_uyari_yolu_engellenir() -> None:
    SchoolYearFactory()
    sid = StudentFactory().pk
    first, _ = _case(refer=False, student_ids=[sid])
    services.add_event(
        first,
        CaseStage.DECIDED,
        date(2026, 5, 19),
        override=True,
        override_reason="x",
        principal_decisions=[PrincipalDecision.WRITTEN_WARNING],
    )
    second, _ = _case(refer=False, student_ids=[sid])
    # Uyarı kaydı eklenmemiş olsa da Dal A dosyası geçmiş sayılır.
    assert selectors.student_discipline_history(sid, exclude_case_id=second.pk).warning_count == 1
    services.add_event(second, CaseStage.GUIDANCE_REFERRED, date(2026, 5, 19))
    services.add_event(
        second, CaseStage.GUIDANCE_RETURNED, date(2026, 5, 20), guidance_outcome="rapor"
    )
    with pytest.raises(ValueError, match="md. 157/7"):
        services.add_event(
            second,
            CaseStage.DECIDED,
            date(2026, 5, 21),
            principal_decisions=[PrincipalDecision.WRITTEN_WARNING],
        )
    # Kurula sevk her zaman serbest.
    services.add_event(
        second,
        CaseStage.DECIDED,
        date(2026, 5, 21),
        principal_decisions=[PrincipalDecision.DISCIPLINE_COMMITTEE],
    )


# ---------------------------------------------------------------------------
# md. 191 — yeter sayı + şikâyetçi/zarar gören üye
# ---------------------------------------------------------------------------
def _committee_with_members(n_teachers: int = 2) -> list[int]:
    year = SchoolYear.objects.get(is_active=True)
    committee = services.create_committee(school_year_id=year.pk, chair_id=PersonnelFactory().pk)
    ids = []
    for _ in range(n_teachers):
        ids.append(
            services.add_committee_member(
                committee, member_type="TEACHER", person_id=PersonnelFactory().pk
            ).pk
        )
    ids.append(
        services.add_committee_member(committee, member_type="PARENT", member_name="VELİ ÜYE").pk
    )
    return ids


def test_toplanti_yeter_sayisi() -> None:
    case, _ = _case()
    ids = _committee_with_members()  # başkan + 3 asıl = 4 → en az 3 kişi
    with pytest.raises(ValueError, match="yeter sayısı"):
        services.record_meeting(case, meeting_date=date(2026, 5, 20), attendee_member_ids=[])
    with pytest.raises(ValueError, match="yeter sayısı"):
        services.record_meeting(case, meeting_date=date(2026, 5, 20), attendee_member_ids=ids[:1])
    m = services.record_meeting(case, meeting_date=date(2026, 5, 20), attendee_member_ids=ids[:2])
    assert m.attendees.count() == 2


def test_sikayetci_uye_kurula_katilamaz() -> None:
    SchoolYearFactory()
    teacher = PersonnelFactory()
    case = services.create_case(
        petition_date=date(2026, 5, 18),
        petitioner_name="",
        petitioner_role="OGRETMEN",
        petitioner_user_id=teacher.pk,
        summary="olay",
        student_ids=[StudentFactory().pk],
    )
    year = SchoolYear.objects.get(is_active=True)
    committee = services.create_committee(school_year_id=year.pk, chair_id=PersonnelFactory().pk)
    m1 = services.add_committee_member(committee, member_type="TEACHER", person_id=teacher.pk)
    m2 = services.add_committee_member(
        committee, member_type="TEACHER", person_id=PersonnelFactory().pk
    )
    with pytest.raises(ValueError, match="md. 191/2"):
        services.record_meeting(
            case, meeting_date=date(2026, 5, 20), attendee_member_ids=[m1.pk, m2.pk]
        )


# ---------------------------------------------------------------------------
# md. 172/1-a — uzaklaştırma "okulun açık olduğu sürede"
# ---------------------------------------------------------------------------
def test_ara_tatil_is_gunu_ama_okul_kapali() -> None:
    SchoolYearFactory()
    Holiday.objects.create(
        name="1. ara tatil",
        start_date=date(2025, 11, 10),
        end_date=date(2025, 11, 14),
        kind=HolidayKind.SCHOOL_BREAK,
    )
    assert is_working_day(date(2025, 11, 11)) is True  # yasal süre işler
    assert is_school_open_day(date(2025, 11, 11)) is False  # ceza günü sayılmaz
    # Cuma 07.11 başlayan 3 günlük uzaklaştırma ara tatili atlar: 07, 17, 18 Kasım.
    end = discipline_periods.suspension_end_date(
        date(2025, 11, 7), 3, is_working_day=is_school_open_day
    )
    assert end == date(2025, 11, 18)


def test_uzaklastirma_hafta_sonu_baslayamaz() -> None:
    case, sid = _case()
    with pytest.raises(ValueError, match="md. 172/1-a"):
        services.record_decision(
            case,
            student_id=sid,
            penalty_type=PenaltyType.SHORT_TERM_SUSPENSION,
            suspension_days=3,
            enforcement_start_date=date(2026, 5, 23),  # Cumartesi
            decision_date=date(2026, 5, 22),
        )


def test_form16_yalniz_uzaklastirmada() -> None:
    case, d = _final_decision()
    with pytest.raises(ValueError, match="yalnız kısa süreli uzaklaştırmada"):
        doc_engine.generate_document(
            case,
            document_type=DocumentType.PENALTY_DAYS_NOTICE,
            generated_on=date(2026, 6, 8),
            student_id=d.student_id,
        )


# ---------------------------------------------------------------------------
# Takvim — yaz tatilindeki resmî tatiller de yasal süreye girer
# ---------------------------------------------------------------------------
def test_temmuz_tatili_itiraz_suresini_uzatir() -> None:
    year = SchoolYear.objects.create(
        name="2025-2026", start_date=date(2025, 9, 1), end_date=date(2026, 6, 30), is_active=True
    )
    seed_holidays(year)
    assert is_working_day(date(2026, 7, 15)) is False
    # Tebliğ Cuma 10.07.2026 → 13, 14, (15 tatil), 16, 17, 20 → son gün 20.07.2026.
    got = discipline_periods.appeal_deadline(date(2026, 7, 10), is_working_day=is_working_day)
    assert got == date(2026, 7, 20)


# ---------------------------------------------------------------------------
# md. 182 — onur kurulu başkanı ödül-disiplin kurulu dışında
# ---------------------------------------------------------------------------
def test_onur_kurulu_baskani_disiplin_kuruluna_uye_olamaz() -> None:
    year = SchoolYearFactory()
    honor_chair = PersonnelFactory()
    services.create_honor_board(school_year_id=year.pk, chair_id=honor_chair.pk)
    committee = services.create_committee(school_year_id=year.pk, chair_id=PersonnelFactory().pk)
    with pytest.raises(ValueError, match="md. 182"):
        services.add_committee_member(committee, member_type="TEACHER", person_id=honor_chair.pk)
    with pytest.raises(ValueError, match="md. 182"):
        services.set_committee_chair(committee, honor_chair.pk)


# ---------------------------------------------------------------------------
# md. 185/4 — eski yılın dosyası kendi yılının kurulunu basar
# ---------------------------------------------------------------------------
def test_dosyanin_kurulu_kendi_ders_yilinin_kurulu() -> None:
    case, _ = _case()
    old_year = SchoolYear.objects.get(is_active=True)
    old = services.create_committee(school_year_id=old_year.pk, chair_id=PersonnelFactory().pk)
    old_year.is_active = False
    old_year.save()
    new_year = SchoolYear.objects.create(
        name="2026-2027", start_date=date(2026, 9, 7), end_date=date(2027, 6, 25), is_active=True
    )
    services.create_committee(school_year_id=new_year.pk, chair_id=PersonnelFactory().pk)
    assert selectors.committee_for_case(case) == old


# ---------------------------------------------------------------------------
# K1 — şifreli kipte de TCKN tekilliği servis katmanında
# ---------------------------------------------------------------------------
def test_ayni_tckn_ile_ikinci_ogrenci_eklenemez() -> None:
    persons.create_student(first_name="A", last_name="B", tckn="10000000146")
    with pytest.raises(ValueError, match="T.C. kimlik"):
        persons.create_student(first_name="C", last_name="D", tckn="10000000146")


# ---------------------------------------------------------------------------
# Dal düzeltme — yanlış "yazılı uyarı" geri alınıp kurula sevk edilince Dal B olur
# ---------------------------------------------------------------------------
def test_yanlis_uyari_duzeltilince_dal_b_olur() -> None:
    case, _ = _case(refer=False)
    services.add_event(
        case,
        CaseStage.DECIDED,
        date(2026, 5, 19),
        override=True,
        override_reason="x",
        principal_decisions=[PrincipalDecision.WRITTEN_WARNING],
    )
    case.refresh_from_db()
    services.revert_stage(case, target_stage=CaseStage.PETITION, reason="Yanlış seçim")
    services.add_event(
        case,
        CaseStage.DECIDED,
        date(2026, 5, 20),
        override=True,
        override_reason="Düzeltme",
        principal_decisions=[PrincipalDecision.DISCIPLINE_COMMITTEE],
    )
    assert doc_engine._case_referred_to_committee(case) is True


def test_eski_surumde_onaysiz_teblig_edilmis_karar_sonradan_onaylanabilir() -> None:
    """Geçiş: eski sürüm onaysız tebliğe izin veriyordu — onay sonradan girilebilmeli."""
    case, sid = _case()
    d = services.record_decision(
        case, student_id=sid, penalty_type=PenaltyType.REPRIMAND, decision_date=date(2026, 5, 20)
    )
    DisciplineDecision.objects.filter(pk=d.pk).update(
        notified_at=date(2026, 5, 21), appeal_deadline=date(2026, 5, 28)
    )
    d.refresh_from_db()
    assert selectors.decision_is_final(d, today=date(2026, 7, 1))[0] is False
    services.set_decision_approval(d, approval_status="APPROVED", approved_on=date(2026, 5, 20))
    assert selectors.decision_is_final(d, today=date(2026, 7, 1))[0] is True


# ---------------------------------------------------------------------------
# md. 166 — aynı öğretim yılında tekrar: bir derece ağır ceza (kullanıcı kararı B)
# ---------------------------------------------------------------------------
def _second_case(sid: int) -> DisciplineCase:
    case, _ = _case(student_ids=[sid])
    return case


def _approved_penalty(sid: int, penalty: str, on: date) -> DisciplineDecision:
    case = _second_case(sid)
    d = services.record_decision(case, student_id=sid, penalty_type=penalty, decision_date=on)
    approve(d)
    return d


def test_md166_ayni_yilda_ayni_ceza_gerekcesiz_girilemez() -> None:
    SchoolYearFactory()
    sid = StudentFactory().pk
    _approved_penalty(sid, PenaltyType.REPRIMAND, date(2026, 5, 20))
    case = _second_case(sid)
    with pytest.raises(ValueError, match="md. 166"):
        services.record_decision(
            case, student_id=sid, penalty_type=PenaltyType.REPRIMAND, decision_date=date(2026, 6, 1)
        )
    d = services.record_decision(
        case,
        student_id=sid,
        penalty_type=PenaltyType.REPRIMAND,
        decision_date=date(2026, 6, 1),
        md166_override_reason="  Fiil farklı ve daha hafif nitelikte.  ",
    )
    assert d.md166_override_reason == "Fiil farklı ve daha hafif nitelikte."


def test_md166_bir_derece_agir_ceza_ve_cezasiz_karar_serbest() -> None:
    SchoolYearFactory()
    sid = StudentFactory().pk
    _approved_penalty(sid, PenaltyType.REPRIMAND, date(2026, 5, 20))
    heavier = services.record_decision(
        _second_case(sid),
        student_id=sid,
        penalty_type=PenaltyType.SHORT_TERM_SUSPENSION,
        suspension_days=2,
        decision_date=date(2026, 6, 1),
    )
    assert heavier.md166_override_reason == ""
    services.record_decision(
        _second_case(sid),
        student_id=sid,
        penalty_type=PenaltyType.NO_PENALTY,
        decision_date=date(2026, 6, 1),
    )


def test_md166_onaysiz_bozulan_ve_gecen_yil_cezasi_sayilmaz() -> None:
    SchoolYearFactory()
    SchoolYear.objects.create(
        name="2024-2025", start_date=date(2024, 9, 9), end_date=date(2025, 6, 20)
    )
    sid = StudentFactory().pk
    old = _approved_penalty(sid, PenaltyType.REPRIMAND, date(2026, 5, 20))
    DisciplineDecision.objects.filter(pk=old.pk).update(decision_date=date(2025, 3, 3))
    pending_case = _second_case(sid)
    services.record_decision(
        pending_case,
        student_id=sid,
        penalty_type=PenaltyType.REPRIMAND,
        decision_date=date(2026, 5, 21),
    )  # onaysız → ceza değil
    services.record_decision(
        _second_case(sid),
        student_id=sid,
        penalty_type=PenaltyType.REPRIMAND,
        decision_date=date(2026, 6, 1),
    )


def test_md166_duzenlemede_hafiflestirme_gerekce_ister() -> None:
    SchoolYearFactory()
    sid = StudentFactory().pk
    _approved_penalty(sid, PenaltyType.REPRIMAND, date(2026, 5, 20))
    d = services.record_decision(
        _second_case(sid),
        student_id=sid,
        penalty_type=PenaltyType.SHORT_TERM_SUSPENSION,
        suspension_days=2,
        decision_date=date(2026, 6, 1),
    )
    with pytest.raises(ValueError, match="md. 166"):
        services.update_decision(
            d, penalty_type=PenaltyType.REPRIMAND, decision_date=date(2026, 6, 1)
        )
    services.update_decision(
        d,
        penalty_type=PenaltyType.REPRIMAND,
        decision_date=date(2026, 6, 1),
        md166_override_reason="Kurul takdiri.",
    )
    # Gerekçe verilmeden yapılan sonraki düzenleme mevcut gerekçeyi korur.
    services.update_decision(
        d, penalty_type=PenaltyType.REPRIMAND, decision_date=date(2026, 6, 1), notes="not"
    )
    d.refresh_from_db()
    assert d.md166_override_reason == "Kurul takdiri."


def test_md166_api_on_bilgi_ve_400() -> None:
    from rest_framework.test import APIClient

    SchoolYearFactory()
    sid = StudentFactory().pk
    prior = _approved_penalty(sid, PenaltyType.REPRIMAND, date(2026, 5, 20))
    case = _second_case(sid)
    client = APIClient()
    url = f"/api/v1/discipline/cases/{case.pk}/decisions/"
    from unittest import mock

    with mock.patch("django.utils.timezone.localdate", return_value=date(2026, 6, 1)):
        data = client.get(url).json()
    assert data["md166_priors"][str(sid)]["penalty_type"] == PenaltyType.REPRIMAND
    assert data["md166_priors"][str(sid)]["decision_no"] == prior.decision_no
    body = {"student": sid, "penalty_type": "REPRIMAND", "decision_date": "2026-06-01"}
    resp = client.post(url, body, format="json")
    assert resp.status_code == 400
    assert "md. 166" in str(resp.json())
    resp = client.post(url, {**body, "md166_override_reason": "Takdir."}, format="json")
    assert resp.status_code == 201
    assert resp.json()["md166_override_reason"] == "Takdir."
