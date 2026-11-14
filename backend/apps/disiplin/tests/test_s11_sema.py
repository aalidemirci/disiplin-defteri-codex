"""Kullanıcı kararı 14.11.2026 — S11 (şema gerektirenler) regresyon testleri.

- S11a: ders yılı başına KALICI dosya numarası sayacı — imha (md. 157/7, hard-delete)
        edilen dosyanın numarası yeniden verilmez.
- S11b: md. 197 / üst kurul onayında okul kurulunun VERDİĞİ ceza (tür + gün) ve ilk
        İADE tarihi kayıtta saklanır; belgeler tahmin yerine kaydı basar.

Göç testleri gerçek "eski şema → göç → doğrula" senaryosudur (MigrationExecutor):
program son kullanıcıda açılışta `migrate --no-input` ile güncellendiğinden göç
dolu tablolarla, soft-delete satırlarla ve geri alınarak denenir.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from typing import Any

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.template.loader import render_to_string
from django.utils import timezone

from apps.disiplin import documents as doc_engine
from apps.disiplin import services
from apps.disiplin.models import (
    CaseNumberCounter,
    CaseStage,
    DecisionApprovalStatus,
    DisciplineCase,
    DisciplineDecision,
    DocumentType,
    PenaltyType,
    PrincipalDecision,
)
from apps.disiplin.serializers import DecisionSerializer
from apps.disiplin.services import purge as purge_service
from apps.disiplin.tests.factories import (
    SchoolYearFactory,
    StudentFactory,
    committee_attendees,
    committee_for,
    decide,
)
from apps.okul.models import SchoolYear
from apps.okul.services import school_year as school_year_service
from apps.okul.services import setup as okul_setup

pytestmark = pytest.mark.django_db

_SUSPENSION = "Okuldan kısa süreli uzaklaştırma"


def _school() -> SchoolYear:
    year: SchoolYear = SchoolYearFactory()
    okul_setup.update_school_config(
        fields={
            "school_name": "Deneme Anadolu Lisesi",
            "district": "Menteşe",
            "principal_name": "ALİ ÖRNEK",
        }
    )
    return year


def _open_case(student: Any | None = None) -> DisciplineCase:
    s = student or StudentFactory()
    return services.create_case(
        petition_date=date(2026, 3, 2),
        petitioner_name="İdare",
        petitioner_role="IDARE",
        summary="Sınıf içinde uygunsuz davranış.",
        student_ids=[s.pk],
    )


def _warning_case() -> DisciplineCase:
    """Dal A: yazılı uyarıyla kapanmış, imha kapsamındaki dosya (md. 157/7)."""
    s = StudentFactory()
    case = _open_case(s)
    services.add_event(
        case,
        CaseStage.DECIDED,
        date(2026, 3, 5),
        override=True,
        override_reason="Rehberlik atlandı.",
        principal_decisions=[PrincipalDecision.WRITTEN_WARNING],
    )
    services.issue_warning(
        case, student_id=s.pk, warning_date=date(2026, 3, 5), summary="Dikkat çekildi."
    )
    case.refresh_from_db()
    return case


def _purge(case: DisciplineCase) -> None:
    record = purge_service.issue_record(case_ids=[case.pk], confirmed=True)
    purge_service.execute(token=record.token, confirmed=True)
    assert not DisciplineCase.all_objects.filter(pk=case.pk).exists()


# =============================================================================
# S11a — kalıcı dosya numarası sayacı
# =============================================================================
def test_s11a_imha_edilen_dosyanin_numarasi_yeniden_verilmez() -> None:
    _school()
    first = _warning_case()
    assert first.case_no == "2025-2026-0001"
    _purge(first)

    assert _open_case().case_no == "2025-2026-0002"


def test_s11a_son_dosya_imha_edilse_de_sayac_ilerlemis_kalir() -> None:
    """İmha sayaca DOKUNMAZ: arada ve sonda imha edilen numaralar tüketilmiş kalır."""
    year = _school()
    _open_case()
    second = _warning_case()
    third = _warning_case()
    _purge(second)
    _purge(third)

    assert CaseNumberCounter.objects.get(school_year=year).last_seq == 3
    assert _open_case().case_no == "2025-2026-0004"


def test_s11a_soft_delete_edilen_dosyanin_numarasi_tuketilmis_sayilir() -> None:
    _school()
    case = _open_case()
    case.delete()  # soft-delete

    assert _open_case().case_no == "2025-2026-0002"


def test_s11a_iki_ders_yili_bagimsiz_sayar() -> None:
    old = _school()
    assert _open_case().case_no == "2025-2026-0001"
    assert _open_case().case_no == "2025-2026-0002"

    new = school_year_service.create_school_year(
        name="2026-2027", start_date=date(2026, 9, 7), end_date=date(2027, 6, 25), activate=True
    )
    assert _open_case().case_no == "2026-2027-0001"

    # Geçmiş yıl yeniden etkinleştirilirse kendi sayacından sürer.
    old.refresh_from_db()
    school_year_service.activate_school_year(old)
    assert _open_case().case_no == "2025-2026-0003"
    assert CaseNumberCounter.objects.get(school_year=old).last_seq == 3
    assert CaseNumberCounter.objects.get(school_year=new).last_seq == 1


def test_s11a_numara_bicimi_ve_aktif_yil_invarianti_degismez() -> None:
    with pytest.raises(ValueError, match="Aktif ders yılı"):
        services.generate_case_no()
    _school()
    assert services.generate_case_no() == "2025-2026-0001"


def test_s11a_sayac_geride_kalsa_da_var_olan_numara_yeniden_verilmez() -> None:
    """Sigorta: sayaç satırı tablodaki en büyük numaranın gerisindeyse (elle düzeltilmiş
    veri, eski yedek) numara çakışmaz — sayaç tabloya yetişir."""
    year = _school()
    DisciplineCase.objects.create(
        case_no="2025-2026-0007",
        petition_date=date(2026, 3, 2),
        petitioner_name="İdare",
        petitioner_role="IDARE",
        summary="x",
    )
    assert _open_case().case_no == "2025-2026-0008"
    assert CaseNumberCounter.objects.get(school_year=year).last_seq == 8


# =============================================================================
# S11b — özgün ceza ve ilk iade tarihi (servis)
# =============================================================================
def _committee_case(student: Any) -> DisciplineCase:
    _school()
    case = _open_case(student)
    services.add_event(
        case,
        CaseStage.DECIDED,
        date(2026, 3, 5),
        override=True,
        override_reason="Rehberlik atlandı.",
        principal_decisions=[PrincipalDecision.DISCIPLINE_COMMITTEE],
    )
    return case


def _suspension(case: DisciplineCase, student: Any, days: int = 5) -> DisciplineDecision:
    return decide(
        case,
        student_id=student.pk,
        penalty_type=PenaltyType.SHORT_TERM_SUSPENSION,
        suspension_days=days,
        decision_date=date(2026, 3, 10),
    )


def _return_and_refer(decision: DisciplineDecision) -> None:
    services.record_principal_review(
        decision, action="RETURN", reason="Ceza ağır.", decided_on=date(2026, 3, 11)
    )
    services.record_principal_review(
        decision, action="REFER", reason="Kurul ısrar etti.", decided_on=date(2026, 3, 16)
    )


def _md197_modified() -> tuple[DisciplineCase, Any, DisciplineDecision]:
    """Okul kurulu 5 gün uzaklaştırma verdi → iade → ilçeye sevk → ilçe KINAMA yaptı."""
    student = StudentFactory()
    case = _committee_case(student)
    decision = _suspension(case, student, days=5)
    _return_and_refer(decision)
    services.set_decision_approval(
        decision,
        approval_status="APPROVED",
        approved_on=date(2026, 3, 20),
        modified_penalty_type=PenaltyType.REPRIMAND,
    )
    decision.refresh_from_db()
    return case, student, decision


def test_s11b_yeni_kararda_ozgun_ceza_alanlari_bostur() -> None:
    student = StudentFactory()
    decision = _suspension(_committee_case(student), student)
    assert decision.board_penalty_type == ""
    assert decision.board_suspension_days is None
    assert decision.first_returned_at is None


def test_s11b_md197_onayinda_degisen_cezada_ozgun_ceza_saklanir() -> None:
    _case, _student, decision = _md197_modified()
    assert decision.penalty_type == PenaltyType.REPRIMAND  # yürürlükteki ceza
    assert decision.behavior_point_deduction == 10  # puan GÜNCEL cezadan (md. 170)
    assert decision.board_penalty_type == PenaltyType.SHORT_TERM_SUSPENSION
    assert decision.board_suspension_days == 5


def test_s11b_ilce_onayinda_degisen_okul_degistirmede_ozgun_ceza_saklanir() -> None:
    student = StudentFactory()
    case = _committee_case(student)
    decision = decide(
        case,
        student_id=student.pk,
        penalty_type=PenaltyType.SCHOOL_CHANGE,
        decision_date=date(2026, 3, 10),
    )
    services.set_decision_approval(
        decision,
        approval_status="APPROVED",
        approved_on=date(2026, 3, 20),
        modified_penalty_type=PenaltyType.SHORT_TERM_SUSPENSION,
        modified_suspension_days=3,
    )
    decision.refresh_from_db()
    assert decision.board_penalty_type == PenaltyType.SCHOOL_CHANGE
    assert decision.board_suspension_days is None


def test_s11b_ikinci_degisiklik_ozgun_cezayi_ezmez() -> None:
    """Yanlış girilen ilçe kararı düzeltilirken kurulun verdiği ceza KORUNUR."""
    _case, _student, decision = _md197_modified()
    services.set_decision_approval(decision, approval_status="PENDING")  # geri al
    services.set_decision_approval(
        decision,
        approval_status="APPROVED",
        approved_on=date(2026, 3, 20),
        modified_penalty_type=PenaltyType.SHORT_TERM_SUSPENSION,
        modified_suspension_days=2,
    )
    decision.refresh_from_db()
    assert decision.suspension_days == 2
    assert (decision.board_penalty_type, decision.board_suspension_days) == (
        PenaltyType.SHORT_TERM_SUSPENSION,
        5,
    )


def test_s11b_ceza_kurulun_verdigine_donse_de_ozgun_ceza_kayitta_kalir() -> None:
    """Bir kez kaydedilen özgün ceza, ceza kurulun verdiğine geri dönse de BOŞALTILMAZ:
    "boş" yalnız "hiç değişmedi / göç öncesi" demektir (yoksa belgeler tahmine düşer)."""
    _case, _student, decision = _md197_modified()
    services.set_decision_approval(
        decision,
        approval_status="APPROVED",
        approved_on=date(2026, 3, 20),
        modified_penalty_type=PenaltyType.SHORT_TERM_SUSPENSION,
        modified_suspension_days=5,
    )
    decision.refresh_from_db()
    assert (decision.penalty_type, decision.suspension_days) == (
        PenaltyType.SHORT_TERM_SUSPENSION,
        5,
    )
    assert (decision.board_penalty_type, decision.board_suspension_days) == (
        PenaltyType.SHORT_TERM_SUSPENSION,
        5,
    )


def test_s11b_itirazla_degisen_cezada_da_ozgun_ceza_saklanir() -> None:
    """İlk değişiklik itirazdan gelirse de kurulun verdiği ceza karara yazılır; itiraz
    kaydındaki `previous_*` (itiraza KONU ceza) ayrıca dolar."""
    student = StudentFactory()
    decision = _suspension(_committee_case(student), student, days=4)
    services.set_decision_approval(
        decision, approval_status="APPROVED", approved_on=date(2026, 3, 11)
    )
    services.notify_decision(decision, notified_on=date(2026, 3, 11))
    appeal = services.file_appeal(decision, filed_on=date(2026, 3, 12), filed_by_role="PARENT")
    services.resolve_appeal(
        appeal,
        result="REDUCED",
        resulted_on=date(2026, 3, 20),
        new_penalty_type=PenaltyType.REPRIMAND,
    )
    decision.refresh_from_db()
    appeal.refresh_from_db()
    assert (decision.board_penalty_type, decision.board_suspension_days) == (
        PenaltyType.SHORT_TERM_SUSPENSION,
        4,
    )
    assert (appeal.previous_penalty_type, appeal.previous_suspension_days) == (
        PenaltyType.SHORT_TERM_SUSPENSION,
        4,
    )


def _school_change_modified_then_pending() -> DisciplineDecision:
    """Okul değiştirme → ilçe onayı yanlışlıkla "değiştirildi: kınama" → onay geri alındı."""
    student = StudentFactory()
    case = _committee_case(student)
    decision = decide(
        case,
        student_id=student.pk,
        penalty_type=PenaltyType.SCHOOL_CHANGE,
        decision_date=date(2026, 3, 10),
    )
    services.set_decision_approval(
        decision,
        approval_status="APPROVED",
        approved_on=date(2026, 3, 20),
        modified_penalty_type=PenaltyType.REPRIMAND,
    )
    services.set_decision_approval(decision, approval_status="PENDING")
    decision.refresh_from_db()
    return decision


def test_s11b_onay_geri_alininca_ceza_kurulun_verdigine_doner() -> None:
    """Yanlış girilen üst kurul onayı "beklemede"ye alınınca üst kurul değişikliği de
    geri alınır: ceza, puan ve onay mercii kurulun verdiği cezaya göre (§7.6 — tek yönlü
    kapan olmasın; düzenleme formu kurulun GERÇEK cezasıyla açılsın)."""
    decision = _school_change_modified_then_pending()
    assert decision.approval_status == DecisionApprovalStatus.PENDING
    assert decision.penalty_type == PenaltyType.SCHOOL_CHANGE
    assert decision.behavior_point_deduction == 40
    assert decision.approval_authority == "DISTRICT_BOARD"  # ilçe onayı gereği kaybolmaz
    assert decision.board_penalty_type == ""
    assert decision.board_suspension_days is None


def test_s11b_onay_geri_alininca_uzaklastirma_gun_sayisi_da_geri_gelir() -> None:
    """md. 197 sevkli karar: ilçe kınamaya çevirmişti; geri almada 5 gün uzaklaştırma
    geri gelir ve karar "ilçe kurulunda"ya döner."""
    _case, _student, decision = _md197_modified()
    services.set_decision_approval(decision, approval_status="PENDING")
    decision.refresh_from_db()
    assert decision.approval_status == DecisionApprovalStatus.REFERRED_TO_DISTRICT
    assert (decision.penalty_type, decision.suspension_days) == (
        PenaltyType.SHORT_TERM_SUSPENSION,
        5,
    )
    assert decision.behavior_point_deduction == 20
    assert (decision.board_penalty_type, decision.board_suspension_days) == ("", None)


def test_s11b_onay_geri_alindiktan_sonra_aynen_onay_degisiklik_notu_tasimaz(
    ctx: dict[str, Any],
) -> None:
    case, student, decision = _md197_modified()
    services.set_decision_approval(decision, approval_status="PENDING")
    services.set_decision_approval(
        decision, approval_status="APPROVED", approved_on=date(2026, 3, 20)
    )
    committee_for(SchoolYearFactory())
    _generate(case, DocumentType.COMMITTEE_DECISION, student_id=student.pk)
    assert ctx["board_penalty_display"] == f"{_SUSPENSION} — 5 gün"
    assert ctx["current_penalty_display"] == f"{_SUSPENSION} — 5 gün"
    assert ctx["penalty_change_note"] == ""


def test_s11b_itirazli_kararda_onay_geri_alma_cezaya_dokunmaz() -> None:
    """İtiraz kaydı varsa ceza itiraz kanalında değişmiş olabilir: geri yükleme YOK."""
    _case, _student, decision = _md197_modified()
    services.notify_decision(decision, notified_on=date(2026, 3, 20))
    services.file_appeal(decision, filed_on=date(2026, 3, 23), filed_by_role="PARENT")
    # Tebliğli karar onaysız hâle döndürülemez; koruma atlatılsa bile ceza değişmemeli.
    DisciplineDecision.objects.filter(pk=decision.pk).update(notified_at=None)
    decision.refresh_from_db()
    services.set_decision_approval(decision, approval_status="PENDING")
    decision.refresh_from_db()
    assert decision.penalty_type == PenaltyType.REPRIMAND
    assert (decision.board_penalty_type, decision.board_suspension_days) == (
        PenaltyType.SHORT_TERM_SUSPENSION,
        5,
    )


def test_s11b_duzenleme_formu_kurulun_cezasiyla_gelir_girilen_ceza_gecerlidir() -> None:
    """Düzenleme yalnız PENDING + tebliğsiz + itirazsız kararda açıktır (§8); o duruma
    geçiş özgün cezayı zaten geri yükler. Düzenlemede kullanıcının GİRDİĞİ ceza kurulun
    yeni kararıdır — eski "özgün ceza" izi taşınmaz."""
    decision = _school_change_modified_then_pending()
    services.update_decision(
        decision,
        penalty_type=decision.penalty_type,  # form kayıttaki (geri yüklenmiş) cezayla açılır
        decision_date=date(2026, 3, 10),
        notes="Açıklama düzeltildi.",
    )
    decision.refresh_from_db()
    assert decision.penalty_type == PenaltyType.SCHOOL_CHANGE
    assert decision.approval_authority == "DISTRICT_BOARD"
    assert (decision.board_penalty_type, decision.board_suspension_days) == ("", None)

    services.update_decision(
        decision, penalty_type=PenaltyType.REPRIMAND, decision_date=date(2026, 3, 10)
    )
    decision.refresh_from_db()
    assert decision.penalty_type == PenaltyType.REPRIMAND
    assert decision.approval_authority == "PRINCIPAL"
    assert decision.board_penalty_type == ""


def test_s11b_duzenlemede_kalmis_ozgun_ceza_izi_temizlenir() -> None:
    """Savunma: özgün ceza izi bir biçimde PENDING kararda kalmışsa (elle düzeltilmiş
    veri) düzenleme onu taşımaz — girilen ceza kurulun kararıdır."""
    student = StudentFactory()
    decision = _suspension(_committee_case(student), student, days=4)
    DisciplineDecision.objects.filter(pk=decision.pk).update(
        board_penalty_type=PenaltyType.SCHOOL_CHANGE
    )
    decision.refresh_from_db()
    services.update_decision(
        decision,
        penalty_type=PenaltyType.SHORT_TERM_SUSPENSION,
        suspension_days=4,
        decision_date=date(2026, 3, 10),
    )
    decision.refresh_from_db()
    assert decision.board_penalty_type == ""


# -----------------------------------------------------------------------------
# S11b — zincir: onayda değişiklik → itirazla kurulun verdiği cezaya dönüş
# -----------------------------------------------------------------------------
def _changed_then_back() -> tuple[DisciplineCase, Any, DisciplineDecision]:
    """Kurul 3 gün verdi → iade + ilçeye sevk → ilçe onayda 5 güne çıkardı → tebliğ →
    itiraz → il kurulu 3 güne indirdi (kurulun verdiği cezaya DÖNÜŞ)."""
    student = StudentFactory()
    case = _committee_case(student)
    decision = _suspension(case, student, days=3)
    _return_and_refer(decision)
    services.set_decision_approval(
        decision,
        approval_status="APPROVED",
        approved_on=date(2026, 3, 20),
        modified_penalty_type=PenaltyType.SHORT_TERM_SUSPENSION,
        modified_suspension_days=5,
    )
    services.notify_decision(decision, notified_on=date(2026, 3, 20))
    appeal = services.file_appeal(decision, filed_on=date(2026, 3, 23), filed_by_role="PARENT")
    services.resolve_appeal(
        appeal,
        result="REDUCED",
        resulted_on=date(2026, 3, 30),
        new_penalty_type=PenaltyType.SHORT_TERM_SUSPENSION,
        new_suspension_days=3,
    )
    decision.refresh_from_db()
    return case, student, decision


def test_s11b_zincir_ozgun_cezaya_donuste_kayit_korunur_puan_yururlukten() -> None:
    _case, _student, decision = _changed_then_back()
    assert (decision.penalty_type, decision.suspension_days) == (
        PenaltyType.SHORT_TERM_SUSPENSION,
        3,
    )
    assert decision.behavior_point_deduction == 20  # §8: yürürlükteki cezadan
    assert (decision.board_penalty_type, decision.board_suspension_days) == (
        PenaltyType.SHORT_TERM_SUSPENSION,
        3,
    )
    data = DecisionSerializer(decision).data
    assert data["board_penalty_type"] == PenaltyType.SHORT_TERM_SUSPENSION
    assert data["board_suspension_days"] == 3


def test_s11b_zincir_ek1_ve_form18_kurulun_verdigi_cezayi_basar(ctx: dict[str, Any]) -> None:
    """Eski kusur: alan boşalınca belge TAHMİNE düşüp "kurulun verdiği 5 gün" basıyordu;
    kurul 5 günü hiç vermedi (o, ilçenin onayda bağladığı cezaydı)."""
    case, student, _decision = _changed_then_back()
    committee_for(SchoolYearFactory())
    for document_type in (DocumentType.COMMITTEE_DECISION, DocumentType.APPEAL_LETTER):
        _generate(case, document_type, student_id=student.pk)
        assert ctx["decision"].penalty_type == PenaltyType.SHORT_TERM_SUSPENSION
        assert ctx["decision"].suspension_days == 3
        assert ctx["board_penalty_display"] == f"{_SUSPENSION} — 3 gün"
        assert ctx["current_penalty_display"] == f"{_SUSPENSION} — 3 gün"
        assert ctx["penalty_change_note"] == ""
        assert "— 5 gün" not in _html(ctx)


def test_s11b_zincir_karar_defteri_kurulun_verdigi_cezayi_basar() -> None:
    case, _student, _decision = _changed_then_back()
    meeting = services.create_council_meeting(
        school_year_id=SchoolYearFactory().pk,
        council_type="DISCIPLINE",
        meeting_date=date(2026, 3, 10),
        attendees=committee_attendees(),
        minutes_type="CASE_REVIEW",
        discipline_case_id=case.pk,
    )
    rows = doc_engine._council_minutes_context(meeting)["case_decisions"]
    assert [r["penalty_display"] for r in rows] == [f"{_SUSPENSION} — 3 gün"]


def test_s11b_zincir_ust_kurul_tebligleri_dogru_cezayi_basar(ctx: dict[str, Any]) -> None:
    """Onay tebliği: özne kurulun VERDİĞİ ceza (3 gün). İtiraz sonucu tebliği: itiraza
    KONU ceza (ilçenin bağladığı 5 gün), yürürlükteki ceza 3 gün."""
    case, student, _decision = _changed_then_back()
    _generate(
        case,
        DocumentType.BOARD_DECISION_NOTICE,
        student_id=student.pk,
        notice_kind="approval",
        board_outcome="MODIFIED",
        result_summary="Ceza 5 gün uzaklaştırmaya çevrilerek onaylanmıştır.",
    )
    assert ctx["decision"].suspension_days == 3
    assert ctx["board_penalty_display"] == f"{_SUSPENSION} — 3 gün"

    _generate(
        case,
        DocumentType.BOARD_DECISION_NOTICE,
        student_id=student.pk,
        notice_kind="appeal_result",
        result_summary="5 gün uzaklaştırma 3 güne indirilmiştir.",
    )
    assert ctx["decision"].suspension_days == 5
    assert ctx["appealed_penalty_display"] == f"{_SUSPENSION} — 5 gün"
    assert ctx["current_penalty_display"] == f"{_SUSPENSION} — 3 gün"


def test_s11b_zincir_ceza_tebligi_yururlukteki_cezayi_basar(ctx: dict[str, Any]) -> None:
    case, student, _decision = _changed_then_back()
    _generate(case, DocumentType.PENALTY_NOTICE, student_id=student.pk)
    assert ctx["decision"].penalty_type == PenaltyType.SHORT_TERM_SUSPENSION
    assert ctx["decision"].suspension_days == 3


def test_s11b_ilceye_sevk_ilk_iade_tarihini_ezmez() -> None:
    student = StudentFactory()
    decision = _suspension(_committee_case(student), student)
    services.record_principal_review(
        decision, action="RETURN", reason="Ceza ağır.", decided_on=date(2026, 3, 11)
    )
    assert decision.first_returned_at == date(2026, 3, 11)
    assert decision.returned_at == date(2026, 3, 11)

    services.record_principal_review(
        decision, action="REFER", reason="Kurul ısrar etti.", decided_on=date(2026, 3, 16)
    )
    decision.refresh_from_db()
    assert decision.first_returned_at == date(2026, 3, 11)  # İADE tarihi korunur
    assert decision.returned_at == date(2026, 3, 16)  # son md. 197 adımı (sevk) tarihi
    assert decision.approval_status == DecisionApprovalStatus.REFERRED_TO_DISTRICT


def test_s11b_yeni_alanlar_karar_yanitinda_salt_okurdur() -> None:
    _case, _student, decision = _md197_modified()
    data = DecisionSerializer(decision).data
    assert data["board_penalty_type"] == PenaltyType.SHORT_TERM_SUSPENSION
    assert data["board_suspension_days"] == 5
    assert data["first_returned_at"] == "2026-03-11"
    read_only = set(DecisionSerializer.Meta.read_only_fields)
    assert {"board_penalty_type", "board_suspension_days", "first_returned_at"} <= read_only


# =============================================================================
# S11b — belgeler
# =============================================================================
@pytest.fixture
def ctx(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Şablona giden son bağlamı yakalar (PDF üretmeden)."""
    captured: dict[str, Any] = {}

    def fake(template: str, context: dict[str, Any]) -> tuple[bytes, int]:
        captured.clear()
        captured.update(context)
        captured["__template__"] = template
        return b"%PDF-sahte", 1

    monkeypatch.setattr(doc_engine, "render_pdf_paged", fake)
    return captured


def _html(ctx: dict[str, Any]) -> str:
    return " ".join(render_to_string(ctx["__template__"], ctx).split())


def _generate(case: DisciplineCase, document_type: str, **kwargs: Any) -> None:
    kwargs.setdefault("generated_on", date(2026, 3, 23))
    doc_engine.generate_document(case, document_type=document_type, **kwargs)


def test_s11b_md197_ek1_kurulun_verdigi_cezayi_basar(ctx: dict[str, Any]) -> None:
    """Eski SINIR: md. 197 ile ilçeye giden kararda özgün ceza tahmin edilemiyordu."""
    case, student, _decision = _md197_modified()
    committee_for(SchoolYearFactory())
    _generate(case, DocumentType.COMMITTEE_DECISION, student_id=student.pk)
    assert ctx["decision"].penalty_type == PenaltyType.SHORT_TERM_SUSPENSION
    assert ctx["decision"].suspension_days == 5
    assert ctx["statute_label"] == "Madde 164/2"
    assert ctx["board_penalty_display"] == f"{_SUSPENSION} — 5 gün"
    assert ctx["current_penalty_display"] == "Kınama"
    assert "onay aşamasında İlçe öğrenci disiplin kurulunca" in ctx["penalty_change_note"]


def test_s11b_md197_karar_defteri_kurulun_verdigi_cezayi_basar() -> None:
    case, _student, _decision = _md197_modified()
    meeting = services.create_council_meeting(
        school_year_id=SchoolYearFactory().pk,
        council_type="DISCIPLINE",
        meeting_date=date(2026, 3, 10),
        attendees=committee_attendees(),
        minutes_type="CASE_REVIEW",
        discipline_case_id=case.pk,
    )
    rows = doc_engine._council_minutes_context(meeting)["case_decisions"]
    assert [r["penalty_display"] for r in rows] == [f"{_SUSPENSION} — 5 gün"]


def test_s11b_onaya_sevk_yazisi_ozgun_cezayi_gun_sayisiyla_basar(ctx: dict[str, Any]) -> None:
    """Okul değiştirme → ilçe onayda uzaklaştırmaya çevirir; ardından il kurulu itirazda
    kınamaya indirir. Onaya sevk yazısı kurulun VERDİĞİ cezayı (okul değiştirme) basar."""
    student = StudentFactory()
    case = _committee_case(student)
    decision = decide(
        case,
        student_id=student.pk,
        penalty_type=PenaltyType.SCHOOL_CHANGE,
        decision_date=date(2026, 3, 10),
    )
    services.set_decision_approval(
        decision,
        approval_status="APPROVED",
        approved_on=date(2026, 3, 20),
        modified_penalty_type=PenaltyType.SHORT_TERM_SUSPENSION,
        modified_suspension_days=3,
    )
    services.notify_decision(decision, notified_on=date(2026, 3, 20))
    appeal = services.file_appeal(decision, filed_on=date(2026, 3, 23), filed_by_role="PARENT")
    services.resolve_appeal(
        appeal,
        result="REDUCED",
        resulted_on=date(2026, 3, 30),
        new_penalty_type=PenaltyType.REPRIMAND,
    )
    _generate(case, DocumentType.APPROVAL_REQUEST_LETTER, student_id=student.pk)
    assert ctx["decision"].get_penalty_type_display() == "Okul değiştirme"
    assert ctx["statute_label"] == "Madde 164/3"
    note = ctx["penalty_change_note"]
    assert "onay aşamasında İlçe öğrenci disiplin kurulunca" in note
    assert "ardından itiraz üzerine İl öğrenci disiplin kurulunca" in note


def test_s11b_ozgun_ceza_bos_eski_kayitta_tahmine_geri_donulur(ctx: dict[str, Any]) -> None:
    """Göçten önce değişmiş kararda alan boştur: onay merciinden tahmin sürer."""
    student = StudentFactory()
    case = _committee_case(student)
    decision = decide(
        case,
        student_id=student.pk,
        penalty_type=PenaltyType.SCHOOL_CHANGE,
        decision_date=date(2026, 3, 10),
    )
    services.set_decision_approval(
        decision,
        approval_status="APPROVED",
        approved_on=date(2026, 3, 20),
        modified_penalty_type=PenaltyType.REPRIMAND,
    )
    DisciplineDecision.objects.filter(pk=decision.pk).update(
        board_penalty_type="", board_suspension_days=None
    )
    _generate(case, DocumentType.APPROVAL_REQUEST_LETTER, student_id=student.pk)
    assert ctx["decision"].get_penalty_type_display() == "Okul değiştirme"


def test_s11b_tebligler_yururlukteki_cezayi_basar(ctx: dict[str, Any]) -> None:
    """§8: Form-14 yürürlükteki (ilçenin bağladığı) cezayı tebliğ eder."""
    case, student, decision = _md197_modified()
    services.notify_decision(decision, notified_on=date(2026, 3, 20))
    _generate(case, DocumentType.PENALTY_NOTICE, student_id=student.pk)
    assert ctx["decision"].penalty_type == PenaltyType.REPRIMAND


def test_s11b_sevk_sonrasi_iade_ve_ilce_yazilari_ilk_iade_tarihini_basar(
    ctx: dict[str, Any],
) -> None:
    student = StudentFactory()
    case = _committee_case(student)
    decision = _suspension(case, student)
    _return_and_refer(decision)  # iade 11.03.2026, sevk 16.03.2026

    _generate(case, DocumentType.RETURN_LETTER, student_id=student.pk)
    assert ctx["return_date_unknown"] is False
    assert ctx["decision"].returned_at == date(2026, 3, 11)
    html = _html(ctx)
    assert '<td class="label">Tarih</td><td>11.03.2026</td>' in html
    assert '<div class="date">11.03.2026</div>' in html
    assert "16.03.2026" not in html

    _generate(case, DocumentType.DISTRICT_REFERRAL_LETTER, student_id=student.pk)
    assert ctx["return_letter_date"] == date(2026, 3, 11)
    assert ctx["decision"].returned_at == date(2026, 3, 16)  # yazının kendi tarihi = sevk
    html = _html(ctx)
    assert "b) Müdürlüğümüzün 11.03.2026 tarihli kurula iade yazısı" in html
    assert '<td class="label">Tarih</td><td>16.03.2026</td>' in html


def test_s11b_ilk_iade_tarihi_bilinmeyen_eski_kayitta_tarih_uydurulmaz(
    ctx: dict[str, Any],
) -> None:
    """Göçten önce sevk edilmiş kararda ilk iade tarihi yoktur: noktalı basılır."""
    student = StudentFactory()
    case = _committee_case(student)
    decision = _suspension(case, student)
    _return_and_refer(decision)
    DisciplineDecision.objects.filter(pk=decision.pk).update(first_returned_at=None)

    _generate(case, DocumentType.RETURN_LETTER, student_id=student.pk)
    assert ctx["return_date_unknown"] is True
    assert ctx["decision"].returned_at is None
    _generate(case, DocumentType.DISTRICT_REFERRAL_LETTER, student_id=student.pk)
    assert ctx["return_letter_date"] is None
    assert "b) Müdürlüğümüzün …/…/202… tarihli kurula iade yazısı" in _html(ctx)


# =============================================================================
# Göçler — eski şema → göç → doğrula (dolu tablolar, soft-delete, geri alma)
# =============================================================================
_BEFORE = [("disiplin", "0013_appeal_previous_suspension_days")]
_COUNTER = [("disiplin", "0014_case_number_counter")]
_AFTER = [("disiplin", "0015_decision_board_penalty_first_return")]


@pytest.fixture
def old_schema() -> Iterator[Any]:
    """Veritabanını S11 öncesi şemaya indirir; test bitince en güncel şemaya çıkarır."""
    executor = MigrationExecutor(connection)
    executor.migrate(_BEFORE)
    try:
        yield executor.loader.project_state(_BEFORE).apps
    finally:
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())


def _migrate(target: list[tuple[str, str]]) -> Any:
    executor = MigrationExecutor(connection)
    executor.migrate(target)
    return executor.loader.project_state(target).apps


def _legacy_case(apps: Any, case_no: str, *, deleted: bool = False) -> Any:
    return apps.get_model("disiplin", "DisciplineCase").objects.create(
        case_no=case_no,
        petition_date=date(2026, 3, 2),
        petitioner_name="İdare",
        petitioner_role="IDARE",
        summary="Eski sürümden kalan dosya.",
        deleted_at=timezone.now() if deleted else None,
    )


@pytest.mark.django_db(transaction=True)
def test_s11a_goc_sayaci_mevcut_dosyalardan_doldurur(old_schema: Any) -> None:
    year_model = old_schema.get_model("okul", "SchoolYear")
    full = year_model.objects.create(
        name="2025-2026", start_date=date(2025, 9, 8), end_date=date(2026, 6, 26), is_active=True
    )
    empty = year_model.objects.create(
        name="2024-2025", start_date=date(2024, 9, 9), end_date=date(2025, 6, 20)
    )
    other = year_model.objects.create(
        name="2026-2027", start_date=date(2026, 9, 7), end_date=date(2027, 6, 25)
    )
    _legacy_case(old_schema, "2025-2026-0001")
    _legacy_case(old_schema, "2025-2026-0003")  # 0002 eski sürümde imha edilmiş
    _legacy_case(old_schema, "2025-2026-0009", deleted=True)  # soft-delete: tüketilmiş
    _legacy_case(old_schema, "2025-2026-12")  # biçim dışı numara sayılmaz
    _legacy_case(old_schema, "2026-2027-0002")

    apps = _migrate(_AFTER)

    counter = apps.get_model("disiplin", "CaseNumberCounter")
    assert counter.objects.get(school_year_id=full.pk).last_seq == 9
    assert counter.objects.get(school_year_id=empty.pk).last_seq == 0
    assert counter.objects.get(school_year_id=other.pk).last_seq == 2
    # Göçten sonra gerçek servis: soft-delete edilmiş 0009'un numarası da verilmez.
    assert services.generate_case_no() == "2025-2026-0010"

    # Geri alınabilir: sayaç tablosu kalkar, dosyalar ve numaraları yerinde durur.
    apps = _migrate(_BEFORE)
    assert "disiplin_casenumbercounter" not in connection.introspection.table_names()
    assert apps.get_model("disiplin", "DisciplineCase").objects.count() == 5


@pytest.mark.django_db(transaction=True)
def test_s11b_goc_ilk_iade_tarihini_doldurur_ozgun_cezayi_uydurmaz(old_schema: Any) -> None:
    student_model = old_schema.get_model("okul", "Student")
    decision_model = old_schema.get_model("disiplin", "DisciplineDecision")

    def legacy(case_no: str, **fields: Any) -> int:
        deleted = fields.pop("deleted", False)
        student = student_model.objects.create(first_name="EMRE", last_name=case_no)
        row = decision_model.objects.create(
            case=_legacy_case(old_schema, case_no),
            student=student,
            penalty_type="REPRIMAND",
            decision_date=date(2026, 3, 10),
            approval_authority="PRINCIPAL",
            deleted_at=timezone.now() if deleted else None,
            **fields,
        )
        return int(row.pk)

    plain = legacy("2025-2026-0001")
    returned = legacy("2025-2026-0002", approval_status="RETURNED", returned_at=date(2026, 3, 11))
    # İade edilip "onay bekliyor"a alınmış (kurul yeniden görüşüyor) — henüz sevk yok.
    pending = legacy("2025-2026-0003", approval_status="PENDING", returned_at=date(2026, 3, 12))
    # Sevk edilmiş: `returned_at` SEVK tarihidir, ilk iade tarihi bilinemez.
    referred = legacy(
        "2025-2026-0004",
        approval_status="REFERRED",
        returned_at=date(2026, 3, 16),
        referred_to_district=True,
    )
    # İlçe onayda değiştirmiş: kurulun verdiği ceza kayıtta YOK — uydurulmaz.
    modified = legacy(
        "2025-2026-0005",
        approval_status="APPROVED",
        approved_at=date(2026, 3, 20),
        returned_at=date(2026, 3, 16),
        referred_to_district=True,
    )
    soft_deleted = legacy(
        "2025-2026-0006", approval_status="RETURNED", returned_at=date(2026, 3, 13), deleted=True
    )

    apps = _migrate(_AFTER)

    rows = {row.pk: row for row in apps.get_model("disiplin", "DisciplineDecision").objects.all()}
    assert rows[plain].first_returned_at is None
    assert rows[returned].first_returned_at == date(2026, 3, 11)
    assert rows[pending].first_returned_at == date(2026, 3, 12)
    assert rows[referred].first_returned_at is None
    assert rows[modified].first_returned_at is None
    assert rows[soft_deleted].first_returned_at == date(2026, 3, 13)
    for row in rows.values():
        assert row.board_penalty_type == ""
        assert row.board_suspension_days is None
    # Mevcut alanlar göçte bozulmaz.
    assert rows[referred].returned_at == date(2026, 3, 16)
    assert rows[referred].referred_to_district is True
    assert rows[modified].penalty_type == "REPRIMAND"

    # Geri alınabilir: yeni sütunlar kalkar, eski veriler yerinde durur.
    apps = _migrate(_COUNTER)
    old_rows = apps.get_model("disiplin", "DisciplineDecision").objects.all()
    assert {r.pk: r.returned_at for r in old_rows}[returned] == date(2026, 3, 11)
    with connection.cursor() as cursor:
        columns = {
            c.name
            for c in connection.introspection.get_table_description(
                cursor, "disiplin_disciplinedecision"
            )
        }
    assert not {"board_penalty_type", "board_suspension_days", "first_returned_at"} & columns


# --------------------------------------------------- göç öncesi değişmiş eski kayıt


def test_s11b_goc_oncesi_onayda_degismis_kararda_ozgun_ceza_merciden_okunur() -> None:
    """Son denetim bulgusu: S11 göçünden ÖNCE onayda değişmiş kararda özgün ceza alanı
    boştur ve ceza zaten üst kurulun cezasıdır. Göçten sonraki ilk değişiklik o cezayı
    "kurulun verdiği ceza" diye yazmamalı; özgün ceza onay merciinden okunur."""
    student = StudentFactory()
    decision = decide(
        _committee_case(student),
        student_id=student.pk,
        penalty_type=PenaltyType.EXPULSION,
        decision_date=date(2026, 3, 10),
    )
    # Göç öncesi durum: il kurulu onayda okul değiştirmeye çevirmiş, özgün ceza kayıtsız.
    type(decision).objects.filter(pk=decision.pk).update(
        penalty_type=PenaltyType.SCHOOL_CHANGE, board_penalty_type="", board_suspension_days=None
    )
    decision.refresh_from_db()

    assert services.decisions._legacy_board_penalty(decision) == (PenaltyType.EXPULSION, None)


def test_s11b_ilk_kez_degisen_kararda_ozgun_ceza_o_andaki_cezadir() -> None:
    student = StudentFactory()
    decision = _suspension(_committee_case(student), student, days=4)

    assert services.decisions._legacy_board_penalty(decision) == (
        PenaltyType.SHORT_TERM_SUSPENSION,
        4,
    )
