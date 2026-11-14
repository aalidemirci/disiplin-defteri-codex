"""S8 — TOPLANTI ZORUNLU (kullanıcı kararı, 14.11.2026) — md. 191/1, 196/1.

Yeni disiplin kararı yalnız kayıtlı, yeter sayısı olan kurul toplantısına bağlı girilir;
karar tarihi = toplantı tarihi. GEÇİŞ: toplantısız girilmiş ESKİ kararlar (`meeting IS NULL`)
geçerli kalır — onay / tebliğ / itiraz / kapanış sürer, kayıt kendiliğinden DEĞİŞTİRİLMEZ,
geriye dönük toplantı uydurulmaz.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.disiplin import documents as doc_engine
from apps.disiplin import selectors, services
from apps.disiplin.models import (
    AppealFiledByRole,
    AppealResult,
    CaseStage,
    DisciplineCase,
    DisciplineCommittee,
    DisciplineCommitteeMember,
    DisciplineDecision,
    DisciplineMeeting,
    PenaltyType,
    PrincipalDecision,
)
from apps.disiplin.services.committee import case_meeting_quorum
from apps.disiplin.tests.factories import (
    PersonnelFactory,
    SchoolYearFactory,
    StudentFactory,
    approve,
    committee_for,
    legacy_decision,
    orm_meeting,
)

pytestmark = pytest.mark.django_db

SEVK = date(2026, 5, 19)
T1 = date(2026, 5, 22)
T2 = date(2026, 5, 27)


def _case(students: int = 1) -> tuple[DisciplineCase, list[int]]:
    """Kurula sevk edilmiş açık dosya + öğrenci kimlikleri."""
    SchoolYearFactory()
    ids = [StudentFactory().pk for _ in range(students)]
    case = services.create_case(
        petition_date=date(2026, 5, 18),
        petitioner_name="İdare",
        petitioner_role="IDARE",
        summary="Uydurma olay.",
        student_ids=ids,
    )
    services.add_event(
        case,
        CaseStage.DECIDED,
        SEVK,
        override=True,
        override_reason="Rehberlik atlandı.",
        principal_decisions=[PrincipalDecision.DISCIPLINE_COMMITTEE],
    )
    case.refresh_from_db()
    return case, ids


def _committee() -> tuple[DisciplineCommittee, list[DisciplineCommitteeMember]]:
    """Başkan + iki asıl öğretmen üye (tam sayı 3, yeter sayı 2)."""
    committee = committee_for(SchoolYearFactory())
    return committee, list(DisciplineCommitteeMember.objects.filter(committee=committee))


def _meeting(case: DisciplineCase, on: date, **kwargs: Any) -> DisciplineMeeting:
    _committee_obj, members = _committee()
    return services.record_meeting(
        case, meeting_date=on, attendee_member_ids=[m.pk for m in members], **kwargs
    )


def _record(case: DisciplineCase, sid: int, **kwargs: Any) -> DisciplineDecision:
    return services.record_decision(
        case, student_id=sid, penalty_type=PenaltyType.REPRIMAND, **kwargs
    )


# ---------------------------------------------------------------------------
# record_decision — toplantı şartı
# ---------------------------------------------------------------------------
def test_toplantisiz_dosyada_karar_eyleme_donuk_reddedilir() -> None:
    case, (sid,) = _case()
    with pytest.raises(ValueError, match="kayıtlı kurul toplantısı yok") as err:
        _record(case, sid, decision_date=T1)
    assert "md. 191/1" in str(err.value)
    assert "Kurul toplantıları" in str(err.value)  # ne yapılacağı söylenir
    assert not DisciplineDecision.all_objects.filter(case=case).exists()


def test_tek_toplantida_karar_kendiliginden_baglanir_tarih_toplanti_tarihidir() -> None:
    case, (sid,) = _case()
    meeting = _meeting(case, T1)
    decision = _record(case, sid)
    assert decision.meeting_id == meeting.pk
    assert decision.decision_date == T1
    assert decision.decision_no == "2025-2026/0001"


def test_birden_cok_toplantida_secim_istenir() -> None:
    case, (sid,) = _case()
    _meeting(case, T1)
    second = _meeting(case, T2)
    with pytest.raises(ValueError, match="birden çok kurul toplantısı") as err:
        _record(case, sid)
    assert "22.05.2026" in str(err.value) and "27.05.2026" in str(err.value)
    decision = _record(case, sid, meeting=second)
    assert decision.decision_date == T2


def test_karar_tarihi_toplanti_tarihinden_farkli_girilemez() -> None:
    case, (sid,) = _case()
    meeting = _meeting(case, T1)
    with pytest.raises(ValueError, match=r"Karar tarihi toplantı tarihidir \(22\.05\.2026\)"):
        _record(case, sid, meeting=meeting, decision_date=T2)
    assert _record(case, sid, meeting=meeting, decision_date=T1).decision_date == T1


def test_baska_dosyanin_ya_da_silinmis_toplanti_reddedilir() -> None:
    case, (sid,) = _case()
    other, _ids = _case()
    foreign = _meeting(other, T1)
    with pytest.raises(ValueError, match="bu dosyaya ait değil"):
        _record(case, sid, meeting=foreign)
    own = _meeting(case, T1)
    services.delete_meeting(own)
    own.refresh_from_db()
    with pytest.raises(ValueError, match="silinmiş"):
        _record(case, sid, meeting=own)


def test_eski_sira_korunur_kapali_ve_sevksiz_dosya_kendi_iletisiyle_reddedilir() -> None:
    """Toplantı şartı, eski retlerin (ceza türü → kapalı dosya → sevk) ARDINDAN denetlenir."""
    case, (sid,) = _case()
    with pytest.raises(ValueError, match="Geçersiz ceza türü"):
        services.record_decision(case, student_id=sid, penalty_type="YOK")
    services.revert_stage(case, target_stage=CaseStage.PETITION, reason="Yanlış sevk.")
    case.refresh_from_db()
    with pytest.raises(ValueError, match=r"md\. 163/2"):
        _record(case, sid)


# ---------------------------------------------------------------------------
# Yeter sayı yeniden doğrulaması (md. 191/1)
# ---------------------------------------------------------------------------
def test_yeter_sayisiz_eski_toplantiya_karar_baglanamaz() -> None:
    """Yeter sayı denetimi eklenmeden önce kaydedilmiş toplantı (ORM) karar anında reddedilir;
    toplantıya karar bağlı olmadığı için silinip yeniden kaydedilebilir (kapan yok)."""
    case, (sid,) = _case()
    _committee()
    meeting = orm_meeting(case, T1, attendees=0)
    assert case_meeting_quorum(meeting) == {"full": 3, "required": 2, "present": 1, "ok": False}
    with pytest.raises(ValueError, match="yeter sayı yok") as err:
        _record(case, sid, meeting=meeting)
    assert "md. 191/1" in str(err.value)
    assert "silip" in str(err.value)
    services.delete_meeting(meeting)
    assert _record(case, sid, meeting=_meeting(case, T1)).meeting_id is not None


def test_sonradan_kuruldan_cikarilan_katilimci_sayilmaya_devam_eder() -> None:
    case, (sid,) = _case()
    committee, members = _committee()
    # Tam sayıyı büyüt (başkan + 4 asıl = 5, yeter sayı 3); toplantıya başkan + 2 üye katılır.
    for _ in range(2):
        services.add_committee_member(
            committee, member_type="TEACHER", person_id=PersonnelFactory().pk
        )
    meeting = services.record_meeting(
        case, meeting_date=T1, attendee_member_ids=[m.pk for m in members]
    )
    services.remove_committee_member(members[0])  # toplantıdan SONRA kuruldan çıkarıldı
    quorum = case_meeting_quorum(meeting)
    assert quorum["present"] == 3  # başkan + o gün katılan iki üye
    assert quorum["ok"] is True
    assert _record(case, sid, meeting=meeting).meeting_id == meeting.pk


def test_baskanin_katilmadigi_toplantida_baskan_sayilmaz() -> None:
    case, (sid,) = _case()
    _committee_obj, members = _committee()
    meeting = services.record_meeting(
        case,
        meeting_date=T1,
        attendee_member_ids=[m.pk for m in members],
        chair_absent=True,
        acting_chair_member_id=members[0].pk,
    )
    assert case_meeting_quorum(meeting) == {"full": 3, "required": 2, "present": 2, "ok": True}
    assert _record(case, sid, meeting=meeting).decision_date == T1
    # Tek üyeyle + başkansız eski kayıt: 1 kişi → yetersiz.
    thin = orm_meeting(case, T2, attendees=1)
    DisciplineMeeting.objects.filter(pk=thin.pk).update(
        chair_absent=True, acting_chair_id=members[0].pk
    )
    thin.refresh_from_db()
    assert case_meeting_quorum(thin)["ok"] is False


def test_sevkten_onceki_tarihli_toplantiya_karar_baglanamaz() -> None:
    case, (sid,) = _case()
    early = orm_meeting(case, date(2026, 5, 15))
    with pytest.raises(ValueError, match="sevk tarihinden önce") as err:
        _record(case, sid, meeting=early)
    assert "19.05.2026" in str(err.value)


# ---------------------------------------------------------------------------
# update_decision — bağ ve tarih
# ---------------------------------------------------------------------------
def test_bagli_kararda_tarih_yalniz_baska_toplantiya_baglanarak_degisir() -> None:
    case, (sid,) = _case()
    first = _meeting(case, T1)
    second = _meeting(case, T2)
    decision = _record(case, sid, meeting=first)
    with pytest.raises(ValueError, match="başka bir toplantıya bağlayın"):
        services.update_decision(decision, penalty_type=PenaltyType.REPRIMAND, decision_date=T2)
    # Tarih verilmeden (ya da aynı tarihle) yapılan düzenleme bağı ve tarihi korur.
    services.update_decision(decision, penalty_type=PenaltyType.REPRIMAND, notes="not")
    services.update_decision(decision, penalty_type=PenaltyType.REPRIMAND, decision_date=T1)
    decision.refresh_from_db()
    assert (decision.meeting_id, decision.decision_date) == (first.pk, T1)

    number = decision.decision_no
    services.update_decision(
        decision, penalty_type=PenaltyType.REPRIMAND, decision_no=number, meeting=second
    )
    decision.refresh_from_db()
    assert (decision.meeting_id, decision.decision_date) == (second.pk, T2)
    assert decision.decision_no == number  # karar numarası değişmez
    # İlk toplantı artık serbest (kapan yok).
    services.delete_meeting(first)


def test_bagli_kararin_bagi_kaldirilamaz() -> None:
    case, (sid,) = _case()
    meeting = _meeting(case, T1)
    decision = _record(case, sid, meeting=meeting)
    with pytest.raises(ValueError, match="bağ kaldırılamaz"):
        services.update_decision(decision, penalty_type=PenaltyType.REPRIMAND, meeting=None)
    decision.refresh_from_db()
    assert decision.meeting_id == meeting.pk


def test_eski_kararda_tarih_duzenlenir_toplanti_zorlanmaz_istege_bagli_baglanir() -> None:
    case, (sid,) = _case()
    decision = legacy_decision(
        case, student_id=sid, penalty_type=PenaltyType.REPRIMAND, decision_date=T1
    )
    assert decision.meeting is None
    # Toplantı yokken düzenleme KİLİTLENMEZ; tarih eskisi gibi değişir, `None` etkisizdir.
    services.update_decision(
        decision, penalty_type=PenaltyType.REPRIMAND, decision_date=T2, meeting=None
    )
    decision.refresh_from_db()
    assert (decision.meeting_id, decision.decision_date) == (None, T2)
    # İsteğe bağlı bağlama: tarih toplantı tarihine çekilir.
    meeting = _meeting(case, T1)
    services.update_decision(decision, penalty_type=PenaltyType.REPRIMAND, meeting=meeting)
    decision.refresh_from_db()
    assert (decision.meeting_id, decision.decision_date) == (meeting.pk, T1)


def test_duzenlemede_yeter_sayisiz_toplantiya_baglanamaz() -> None:
    case, (sid,) = _case()
    decision = _record(case, sid, meeting=_meeting(case, T1))
    thin = orm_meeting(case, T2, attendees=0)
    with pytest.raises(ValueError, match="yeter sayı yok"):
        services.update_decision(decision, penalty_type=PenaltyType.REPRIMAND, meeting=thin)


# ---------------------------------------------------------------------------
# rebind_decision_meeting — tarih değişmeden bağ taşıma
# ---------------------------------------------------------------------------
def test_onayli_tebligli_karar_ayni_tarihli_toplantiya_tasinir() -> None:
    """§7.6 çıkışı: yanlış kaydedilmiş toplantıya onaylı karar bağlıysa toplantı silinemez;
    doğru kayıt AYNI tarihle girilir, karar taşınır, eski kayıt silinir."""
    case, (sid,) = _case()
    wrong = _meeting(case, T1)
    decision = _record(case, sid, meeting=wrong)
    approve(decision)
    services.notify_decision(decision, notified_on=T1)
    with pytest.raises(ValueError, match="silinemez"):
        services.delete_meeting(wrong)

    other_day = _meeting(case, T2)
    with pytest.raises(ValueError, match="aynı tarihli") as err:
        services.rebind_decision_meeting(decision, other_day)
    assert "22.05.2026" in str(err.value) and "27.05.2026" in str(err.value)

    right = _meeting(case, T1)
    services.rebind_decision_meeting(decision, right)
    decision.refresh_from_db()
    assert decision.meeting_id == right.pk
    assert decision.decision_date == T1  # onay / tebliğ zinciri etkilenmez
    assert decision.notified_at == T1
    services.delete_meeting(wrong)  # artık serbest


def test_rebind_kapali_dosyada_ve_yeter_sayisiz_toplantida_reddedilir() -> None:
    case, (sid,) = _case()
    decision = _record(case, sid, meeting=_meeting(case, T1))
    thin = orm_meeting(case, T1, attendees=0)
    with pytest.raises(ValueError, match="yeter sayı yok"):
        services.rebind_decision_meeting(decision, thin)
    right = _meeting(case, T1)
    services.close_case(case, override=True, override_reason="Test kapanışı.")
    decision.refresh_from_db()
    with pytest.raises(ValueError, match="Dosya kapalı"):
        services.rebind_decision_meeting(decision, right)


def test_eski_karara_ayni_tarihli_toplanti_istege_bagli_baglanir() -> None:
    case, (sid,) = _case()
    decision = legacy_decision(
        case, student_id=sid, penalty_type=PenaltyType.REPRIMAND, decision_date=T1
    )
    approve(decision)
    with pytest.raises(ValueError, match="aynı tarihli"):
        services.rebind_decision_meeting(decision, _meeting(case, T2))
    meeting = _meeting(case, T1)
    services.rebind_decision_meeting(decision, meeting)
    decision.refresh_from_db()
    assert (decision.meeting_id, decision.decision_date) == (meeting.pk, T1)


# ---------------------------------------------------------------------------
# delete_meeting / restore_decision
# ---------------------------------------------------------------------------
def test_karar_bagli_toplanti_silinemez_karar_silinince_serbest_kalir() -> None:
    case, (sid,) = _case()
    meeting = _meeting(case, T1)
    decision = _record(case, sid, meeting=meeting)
    with pytest.raises(ValueError, match="Bu toplantıda verilmiş karar var") as err:
        services.delete_meeting(meeting)
    assert decision.decision_no in str(err.value)
    assert DisciplineMeeting.objects.filter(pk=meeting.pk).exists()

    services.delete_decision(decision)
    decision.refresh_from_db()
    assert decision.meeting_id == meeting.pk  # bağ DEĞİŞMEZ: geri yükleme aynı toplantıya döner
    services.restore_decision(decision)
    services.delete_decision(decision)
    services.delete_meeting(meeting)  # yalnız silinmiş kararı kalan toplantı silinebilir


def test_toplantisi_silinmis_karar_geri_yuklenemez_eski_karar_yuklenir() -> None:
    case, (bound_sid, legacy_sid) = _case(students=2)
    meeting = _meeting(case, T1)
    bound = _record(case, bound_sid, meeting=meeting)
    legacy = legacy_decision(
        case, student_id=legacy_sid, penalty_type=PenaltyType.REPRIMAND, decision_date=T1
    )
    services.delete_decision(bound)
    services.delete_decision(legacy)
    services.delete_meeting(meeting)

    bound.refresh_from_db()
    with pytest.raises(ValueError, match="toplantısı kaydı .*silinmiş") as err:
        services.restore_decision(bound)
    assert "22.05.2026" in str(err.value)
    assert "yeniden" in str(err.value)
    # Toplantısız girilmiş ESKİ karar bugünkü gibi geri yüklenir (eski kararlar geçerli kalır).
    legacy.refresh_from_db()
    services.restore_decision(legacy)
    legacy.refresh_from_db()
    assert legacy.deleted_at is None and legacy.meeting_id is None


# ---------------------------------------------------------------------------
# GEÇİŞ — toplantısız girilmiş eski karar yürür
# ---------------------------------------------------------------------------
def test_gecis_toplantisiz_eski_karar_onay_teblig_itiraz_kapanis_yurur() -> None:
    case, (sid,) = _case()
    decision = legacy_decision(
        case, student_id=sid, penalty_type=PenaltyType.REPRIMAND, decision_date=T1
    )
    approve(decision)
    services.notify_decision(decision, notified_on=T1)
    appeal = services.file_appeal(
        decision, filed_on=date(2026, 5, 25), filed_by_role=AppealFiledByRole.values[0]
    )
    services.resolve_appeal(appeal, result=AppealResult.UPHELD, resulted_on=date(2026, 6, 1))
    decision.refresh_from_db()
    assert selectors.decision_is_final(decision)[0] is True
    services.confirm_e_school_entry(decision, processed_on=date(2026, 6, 2))
    assert selectors.close_eligible(case, today=date(2026, 6, 10))[0] is True
    services.close_case(case)
    case.refresh_from_db()
    decision.refresh_from_db()
    assert case.closed_at is not None
    assert decision.meeting_id is None  # kayıt kendiliğinden DEĞİŞTİRİLMEDİ
    assert not DisciplineMeeting.all_objects.filter(case=case).exists()  # toplantı uydurulmadı


# ---------------------------------------------------------------------------
# Vekâlet uyarısı (S7) — karara bağlı toplantıda çıkış "sil" değil "taşı"dır
# ---------------------------------------------------------------------------
def test_vekalet_uyarisi_karar_bagli_toplantida_tasimayi_onerir() -> None:
    SchoolYearFactory()
    committee, members = _committee()
    student = StudentFactory()
    case = services.create_case(
        petition_date=date(2026, 5, 18),
        petitioner_name=committee.chair.full_name,
        petitioner_role="OGRETMEN",
        petitioner_user_id=committee.chair_id,
        summary="Uydurma olay.",
        student_ids=[student.pk],
    )
    services.add_event(
        case,
        CaseStage.DECIDED,
        SEVK,
        override=True,
        override_reason="Rehberlik atlandı.",
        principal_decisions=[PrincipalDecision.DISCIPLINE_COMMITTEE],
    )
    case.refresh_from_db()
    # S7 öncesi (vekâletsiz) kaydedilmiş toplantı + ona bağlı karar.
    old = orm_meeting(case, T1)
    _record(case, student.pk, meeting=old)
    (warning,) = services.case_chair_warnings(case)
    assert "AYNI tarihle yeniden kaydedin" in warning
    assert "kararları yeni kayda bağlayın" in warning
    assert "silip" not in warning  # yapılamayan adım önerilmez (§7.6)

    right = services.record_meeting(
        case,
        meeting_date=T1,
        attendee_member_ids=[m.pk for m in members],
        chair_absent=True,
        acting_chair_member_id=members[0].pk,
    )
    decision = DisciplineDecision.objects.get(case=case)
    services.rebind_decision_meeting(decision, right)
    services.delete_meeting(old)
    assert services.case_chair_warnings(case) == []


# ---------------------------------------------------------------------------
# EK-1 — imza heyeti kararın BAĞLI toplantısından
# ---------------------------------------------------------------------------
def _signer_names(case: DisciplineCase, student_id: int) -> list[str]:
    from apps.okul.models import Student

    ctx = doc_engine._ek1_context(case, Student.objects.get(pk=student_id))
    return sorted(str(m.member_name) for m in ctx["members"])


def test_ek1_imza_heyeti_kararin_bagli_toplantisindan_basilir() -> None:
    case, (first_sid, second_sid, legacy_sid) = _case(students=3)
    committee, members = _committee()
    substitute = services.add_committee_member(
        committee, member_type="TEACHER", person_id=PersonnelFactory().pk, is_substitute=True
    )
    early = services.record_meeting(
        case, meeting_date=T1, attendee_member_ids=[m.pk for m in members]
    )
    late = services.record_meeting(
        case, meeting_date=T2, attendee_member_ids=[members[0].pk, substitute.pk]
    )
    _record(case, first_sid, meeting=early)
    _record(case, second_sid, meeting=late)
    legacy_decision(
        case, student_id=legacy_sid, penalty_type=PenaltyType.REPRIMAND, decision_date=T1
    )
    early_names = sorted(m.member_name for m in members)
    late_names = sorted([members[0].member_name, substitute.member_name])
    assert _signer_names(case, first_sid) == early_names  # SON toplantı değil, bağlı toplantı
    assert _signer_names(case, second_sid) == late_names
    # Toplantısız girilmiş eski karar: dosyanın SON toplantısı (S7 kuralı aynen).
    assert _signer_names(case, legacy_sid) == late_names


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
def _url(case: DisciplineCase, tail: str = "") -> str:
    return f"/api/v1/discipline/cases/{case.pk}/{tail}"


def test_api_karar_girisi_toplanti_ister_ve_baglar() -> None:
    client = APIClient()
    case, (sid,) = _case()
    body = {"student": sid, "penalty_type": "REPRIMAND"}
    resp = client.post(_url(case, "decisions/"), body, format="json")
    assert resp.status_code == 400
    assert resp.json()["code"] == "validation_error"
    assert "kayıtlı kurul toplantısı yok" in resp.json()["message"]

    meeting = _meeting(case, T1)
    other, _ids = _case()
    foreign = _meeting(other, T1)
    resp = client.post(_url(case, "decisions/"), {**body, "meeting": foreign.pk}, format="json")
    assert resp.status_code == 400
    assert "bu dosyaya ait değil" in resp.json()["message"]
    resp = client.post(
        _url(case, "decisions/"),
        {**body, "meeting": meeting.pk, "decision_date": "2026-05-27"},
        format="json",
    )
    assert resp.status_code == 400
    assert "Karar tarihi toplantı tarihidir" in resp.json()["message"]

    resp = client.post(_url(case, "decisions/"), body, format="json")  # tek toplantı: seçilir
    assert resp.status_code == 201, resp.content
    data = resp.json()
    assert data["meeting"] == meeting.pk
    assert data["meeting_date"] == data["decision_date"] == "2026-05-22"


def test_api_toplanti_listesi_yeter_sayi_ve_bagli_kararlari_verir() -> None:
    client = APIClient()
    case, (sid,) = _case()
    meeting = _meeting(case, T1)
    decision = _record(case, sid, meeting=meeting)
    orm_meeting(case, T2, attendees=0)
    rows = {row["id"]: row for row in client.get(_url(case, "meeting/")).json()}
    row = rows[meeting.pk]
    assert row["quorum"] == {"full": 3, "required": 2, "present": 3, "ok": True}
    assert row["decisions"] == [
        {
            "id": decision.pk,
            "student": sid,
            "student_name": decision.student.full_name,
            "decision_no": decision.decision_no,
        }
    ]
    (thin,) = [r for r in rows.values() if r["id"] != meeting.pk]
    assert thin["quorum"]["ok"] is False and thin["decisions"] == []

    resp = client.delete(_url(case, f"meeting/{meeting.pk}/"))
    assert resp.status_code == 400
    assert "Bu toplantıda verilmiş karar var" in resp.json()["message"]


def test_api_duzenlemede_baska_toplantiya_baglama_ve_bag_kaldirma_reddi() -> None:
    client = APIClient()
    case, (sid,) = _case()
    first = _meeting(case, T1)
    second = _meeting(case, T2)
    decision = _record(case, sid, meeting=first)
    url = _url(case, f"decisions/{decision.pk}/")

    resp = client.patch(url, {"notes": "yalnız not"}, format="json")  # tarih/bağ korunur
    assert resp.status_code == 200, resp.content
    assert resp.json()["meeting"] == first.pk and resp.json()["decision_date"] == "2026-05-22"

    resp = client.patch(url, {"decision_date": "2026-05-27"}, format="json")
    assert resp.status_code == 400
    resp = client.patch(url, {"meeting": None}, format="json")
    assert resp.status_code == 400
    assert "bağ kaldırılamaz" in resp.json()["message"]
    resp = client.patch(url, {"meeting": 999999}, format="json")
    assert resp.status_code == 400

    resp = client.patch(url, {"meeting": second.pk}, format="json")
    assert resp.status_code == 200, resp.content
    assert resp.json()["meeting"] == second.pk
    assert resp.json()["meeting_date"] == resp.json()["decision_date"] == "2026-05-27"


def test_api_bag_tasima_ucu_ve_toplanti_kaydi_yok_bilgisi() -> None:
    client = APIClient()
    case, (sid,) = _case()
    decision = legacy_decision(
        case, student_id=sid, penalty_type=PenaltyType.REPRIMAND, decision_date=T1
    )
    approve(decision)
    listed = client.get(_url(case, "decisions/")).json()["decisions"]
    assert listed[0]["meeting"] is None and listed[0]["meeting_date"] is None

    url = _url(case, f"decisions/{decision.pk}/meeting/")
    other_day = _meeting(case, T2)
    resp = client.post(url, {"meeting": other_day.pk}, format="json")
    assert resp.status_code == 400
    assert "aynı tarihli" in resp.json()["message"]
    assert client.post(url, {}, format="json").status_code == 400

    same_day = _meeting(case, T1)
    resp = client.post(url, {"meeting": same_day.pk}, format="json")
    assert resp.status_code == 200, resp.content
    assert resp.json()["meeting"] == same_day.pk
    assert resp.json()["meeting_date"] == "2026-05-22"


def test_api_cop_kutusunda_toplantisi_silinmis_karar_geri_yuklenemez() -> None:
    client = APIClient()
    case, (sid,) = _case()
    meeting = _meeting(case, T1)
    decision = _record(case, sid, meeting=meeting)
    services.delete_decision(decision)
    services.delete_meeting(meeting)
    (row,) = client.get(_url(case, "decisions/deleted/")).json()
    assert row["meeting"] == meeting.pk and row["meeting_date"] is None
    resp = client.post(_url(case, f"decisions/{decision.pk}/restore/"), format="json")
    assert resp.status_code == 400
    assert "silinmiş" in resp.json()["message"]


# ---------------------------------------------------------------------------
# Gözden geçirme bulguları (14.11.2026)
# ---------------------------------------------------------------------------
YENI_SEVK = date(2026, 6, 1)


def _refer_again(case: DisciplineCase, on: date = YENI_SEVK) -> None:
    """Sevki geri alıp `on` tarihiyle yeniden kurula sevk eder."""
    services.revert_stage(case, target_stage=CaseStage.PETITION, reason="Yanlış sevk.")
    case.refresh_from_db()
    services.add_event(
        case,
        CaseStage.DECIDED,
        on,
        override=True,
        override_reason="Rehberlik atlandı.",
        principal_decisions=[PrincipalDecision.DISCIPLINE_COMMITTEE],
    )
    case.refresh_from_db()


def test_yeniden_sevkten_onceki_toplantiya_bagli_karar_geri_yuklenemez() -> None:
    """md. 163/2: karar kurula sevkten önce olamaz — çöp kutusundan dönen karar da."""
    case, (sid,) = _case()
    meeting = _meeting(case, T1)
    decision = _record(case, sid, meeting=meeting)
    services.delete_decision(decision)
    _refer_again(case)
    assert selectors.committee_referred_on(case) == YENI_SEVK

    decision.refresh_from_db()
    decision.case.refresh_from_db()
    with pytest.raises(ValueError, match="sevk tarihinden") as err:
        services.restore_decision(decision)
    assert "22.05.2026" in str(err.value) and "01.06.2026" in str(err.value)
    assert "geri yüklenemez" in str(err.value)
    assert "yeniden girin" in str(err.value)  # eyleme dönük
    decision.refresh_from_db()
    assert decision.deleted_at is not None
    # Çıkış var (§7.6): sevkten sonraki toplantıya yeni karar girilir.
    later = _meeting(case, date(2026, 6, 3))
    assert _record(case, sid, meeting=later).decision_date == date(2026, 6, 3)


def test_ayni_sevkte_silinen_bagli_karar_geri_yuklenir() -> None:
    case, (sid,) = _case()
    decision = _record(case, sid, meeting=_meeting(case, T1))
    services.delete_decision(decision)
    decision.refresh_from_db()
    services.restore_decision(decision)
    decision.refresh_from_db()
    assert decision.deleted_at is None


def test_sevkten_onceki_toplantiya_bagli_karar_duzenlenemez_baska_toplantiya_baglanir() -> None:
    """S8 öncesinde her düzenleme sevk öncesi tarihi reddediyordu; bağlı kararda da reddedilir."""
    case, (sid,) = _case()
    meeting = _meeting(case, T1)
    decision = _record(case, sid, meeting=meeting)
    # Sevk öncesinde kalmış bağlı toplantı (yeniden sevk sonrası durumun ORM taklidi).
    early = date(2026, 5, 15)
    DisciplineMeeting.objects.filter(pk=meeting.pk).update(meeting_date=early)
    DisciplineDecision.objects.filter(pk=decision.pk).update(decision_date=early)
    decision.refresh_from_db()
    with pytest.raises(ValueError, match="sevk tarihinden") as err:
        services.update_decision(decision, penalty_type=PenaltyType.NO_PENALTY)
    assert "15.05.2026" in str(err.value) and "19.05.2026" in str(err.value)
    assert "toplantıya bağlayın" in str(err.value)
    # Aynı toplantı açıkça gönderilse de sonuç aynı.
    meeting.refresh_from_db()
    with pytest.raises(ValueError, match="sevk tarihinden"):
        services.update_decision(decision, penalty_type=PenaltyType.NO_PENALTY, meeting=meeting)
    # Çıkış (§7.6): sevkten sonraki toplantıya bağlanır ya da silinir.
    later = _meeting(case, T2)
    services.update_decision(decision, penalty_type=PenaltyType.NO_PENALTY, meeting=later)
    decision.refresh_from_db()
    assert (decision.meeting_id, decision.decision_date) == (later.pk, T2)


def test_bagli_toplanti_acikca_gonderilirse_yeniden_dogrulanmaz() -> None:
    """Kararın ZATEN bağlı olduğu toplantı gönderilirse bağ korunur: kurul sonradan büyüyüp
    toplantı yetersiz görünse de beklemedeki karar düzenlenebilir kalır."""
    case, (sid,) = _case()
    committee, members = _committee()
    meeting = services.record_meeting(
        case, meeting_date=T1, attendee_member_ids=[members[0].pk]
    )  # başkan + 1 üye = 2/3
    decision = _record(case, sid, meeting=meeting)
    for _ in range(2):
        services.add_committee_member(
            committee, member_type="TEACHER", person_id=PersonnelFactory().pk
        )
    assert case_meeting_quorum(meeting)["ok"] is False
    services.update_decision(decision, penalty_type=PenaltyType.NO_PENALTY)
    services.update_decision(
        decision, penalty_type=PenaltyType.REPRIMAND, meeting=meeting, decision_date=T1
    )
    decision.refresh_from_db()
    assert (decision.meeting_id, decision.decision_date) == (meeting.pk, T1)
    assert decision.penalty_type == PenaltyType.REPRIMAND
    # Tarih eşitliği denetimi sürer.
    with pytest.raises(ValueError, match="Karar tarihi toplantı tarihidir"):
        services.update_decision(
            decision, penalty_type=PenaltyType.REPRIMAND, meeting=meeting, decision_date=T2
        )
    # BAŞKA yetersiz toplantıya bağlama hâlâ reddedilir.
    thin = orm_meeting(case, T2, attendees=0)
    with pytest.raises(ValueError, match="yeter sayı yok"):
        services.update_decision(decision, penalty_type=PenaltyType.REPRIMAND, meeting=thin)


def test_yeter_sayi_reddi_karar_bagli_toplantida_silmeyi_onermez() -> None:
    """Yapılamayan adım önerilmez (§7.6): karar bağlı toplantı silinemez — yeni toplantı önerilir."""
    case, (first_sid, second_sid) = _case(students=2)
    committee, members = _committee()
    meeting = services.record_meeting(case, meeting_date=T1, attendee_member_ids=[members[0].pk])
    _record(case, first_sid, meeting=meeting)
    for _ in range(2):
        services.add_committee_member(
            committee, member_type="TEACHER", person_id=PersonnelFactory().pk
        )
    with pytest.raises(ValueError, match="yeter sayı yok") as err:
        _record(case, second_sid, meeting=meeting)
    assert "silip" not in str(err.value)
    assert "yeni bir toplantı" in str(err.value)


def test_toplanti_silme_reddinde_numarasiz_karar_yalniz_adla_anilir() -> None:
    case, (sid,) = _case()
    meeting = _meeting(case, T1)
    decision = _record(case, sid, meeting=meeting)
    services.update_decision(decision, penalty_type=PenaltyType.REPRIMAND, decision_no="")
    with pytest.raises(ValueError, match="Bu toplantıda verilmiş karar var") as err:
        services.delete_meeting(meeting)
    assert "— )" not in str(err.value) and " — " not in str(err.value)
    assert decision.student.full_name in str(err.value)


def test_ek1_ve_katilimci_adlari_sonradan_kuruldan_cikarilan_uyeyi_korur() -> None:
    """md. 196/1: kararı veren heyet imzalar — toplantıdan SONRA kuruldan çıkarılan üye
    EK-1 imza ızgarasında ve katılımcı listesinde kalır (yeter sayı sayımıyla aynı küme)."""
    from apps.disiplin.serializers import MeetingSerializer

    case, (sid,) = _case()
    _committee_obj, members = _committee()
    meeting = services.record_meeting(
        case, meeting_date=T1, attendee_member_ids=[m.pk for m in members]
    )
    _record(case, sid, meeting=meeting)
    names = sorted(m.member_name for m in members)
    services.remove_committee_member(members[0])
    assert _signer_names(case, sid) == names
    meeting.refresh_from_db()
    data = MeetingSerializer(meeting).data
    assert sorted(data["attendee_names"]) == names
    assert len(data["attendee_names"]) + 1 == data["quorum"]["present"]
    # Katılanların HEPSİ çıkarılsa da bugünkü kurula düşülmez.
    services.remove_committee_member(members[1])
    assert _signer_names(case, sid) == names
