"""Disiplin kararı + itiraz + davranış puanı testleri (F2-T3) — md. 163-175.

OYS `test_discipline_decisions.py` davranışlarının uyarlaması; iş günü hesabı
YEREL tatil takvimiyle (Holiday) uçtan uca doğrulanır.
"""

from __future__ import annotations

from datetime import date

import pytest

from apps.disiplin import selectors, services
from apps.disiplin.models import (
    AppealResult,
    CaseStage,
    DecisionApprovalStatus,
    DisciplineCase,
    PenaltyType,
    PrincipalDecision,
)
from apps.disiplin.tests.factories import SchoolYearFactory, StudentFactory
from apps.okul.models import Holiday

pytestmark = pytest.mark.django_db


def _committee_case() -> tuple[DisciplineCase, int]:
    """Kurula sevk edilmiş dosya + öğrenci pk."""
    SchoolYearFactory()
    s = StudentFactory()
    case = services.create_case(
        petition_date=date(2026, 5, 18),
        petitioner_name="A",
        petitioner_role="IDARE",
        summary="x",
        student_ids=[s.pk],
    )
    services.add_event(
        case,
        CaseStage.DECIDED,
        date(2026, 5, 19),
        override=True,
        override_reason="Rehberlik atlandı.",
        principal_decisions=[PrincipalDecision.DISCIPLINE_COMMITTEE],
    )
    return case, s.pk


# ---------------------------------------------------------------------------
# record / update / delete / restore
# ---------------------------------------------------------------------------
def test_record_decision_otomatik_turetir() -> None:
    case, sid = _committee_case()
    d = services.record_decision(
        case, student_id=sid, penalty_type=PenaltyType.REPRIMAND, decision_date=date(2026, 5, 22)
    )
    assert d.behavior_point_deduction == 10  # md. 170
    assert d.approval_authority == "PRINCIPAL"  # md. 163/2
    assert d.approval_status == DecisionApprovalStatus.PENDING
    assert d.decision_no == "2025-2026/0001"


def test_record_decision_numarasi_ders_yilinda_artar() -> None:
    case1, sid1 = _committee_case()
    first = services.record_decision(
        case1,
        student_id=sid1,
        penalty_type=PenaltyType.REPRIMAND,
        decision_date=date(2026, 5, 22),
    )
    case2, sid2 = _committee_case()
    second = services.record_decision(
        case2,
        student_id=sid2,
        penalty_type=PenaltyType.REPRIMAND,
        decision_date=date(2026, 5, 23),
    )
    assert first.decision_no == "2025-2026/0001"
    assert second.decision_no == "2025-2026/0002"


def test_record_decision_ikinci_karar_hata() -> None:
    case, sid = _committee_case()
    services.record_decision(
        case, student_id=sid, penalty_type=PenaltyType.REPRIMAND, decision_date=date(2026, 5, 22)
    )
    with pytest.raises(ValueError, match="zaten bir karar"):
        services.record_decision(
            case,
            student_id=sid,
            penalty_type=PenaltyType.SHORT_TERM_SUSPENSION,
            decision_date=date(2026, 5, 23),
            suspension_days=3,
        )


def test_record_decision_dahil_olmayan_ogrenci_hata() -> None:
    case, _sid = _committee_case()
    disaridan = StudentFactory()
    with pytest.raises(ValueError, match="dahil değil"):
        services.record_decision(
            case,
            student_id=disaridan.pk,
            penalty_type=PenaltyType.REPRIMAND,
            decision_date=date(2026, 5, 22),
        )


def test_onceki_cezalar_ek1_ozetine_derlenir() -> None:
    """İkinci dosyadaki kararın EK-1 'önceki cezalar' özeti ilk kararı içerir."""
    case1, sid = _committee_case()
    services.record_decision(
        case1, student_id=sid, penalty_type=PenaltyType.REPRIMAND, decision_date=date(2026, 5, 22)
    )
    case2 = services.create_case(
        petition_date=date(2026, 6, 1),
        petitioner_name="B",
        petitioner_role="IDARE",
        summary="ikinci olay",
        student_ids=[sid],
    )
    services.add_event(
        case2,
        CaseStage.DECIDED,
        date(2026, 6, 2),
        override=True,
        override_reason="atla",
        principal_decisions=[PrincipalDecision.DISCIPLINE_COMMITTEE],
    )
    d2 = services.record_decision(
        case2, student_id=sid, penalty_type=PenaltyType.REPRIMAND, decision_date=date(2026, 6, 3)
    )
    assert "22.05.2026" in d2.prior_penalties_summary
    assert "Kınama" in d2.prior_penalties_summary


def test_update_delete_restore_yalniz_beklemede() -> None:
    case, sid = _committee_case()
    d = services.record_decision(
        case, student_id=sid, penalty_type=PenaltyType.REPRIMAND, decision_date=date(2026, 5, 22)
    )
    services.update_decision(
        d,
        penalty_type=PenaltyType.SHORT_TERM_SUSPENSION,
        decision_date=date(2026, 5, 22),
        suspension_days=3,
    )
    d.refresh_from_db()
    assert d.behavior_point_deduction == 20  # yeniden türetildi

    services.delete_decision(d)
    assert selectors.get_decision(case, d.pk) is None
    assert selectors.get_any_decision(case, d.pk) is not None

    services.restore_decision(d)
    assert selectors.get_decision(case, d.pk) is not None


def test_onaylanmis_karar_duzenlenemez() -> None:
    case, sid = _committee_case()
    d = services.record_decision(
        case, student_id=sid, penalty_type=PenaltyType.REPRIMAND, decision_date=date(2026, 5, 22)
    )
    services.set_decision_approval(
        d, approval_status=DecisionApprovalStatus.APPROVED, approved_on=date(2026, 5, 23)
    )
    with pytest.raises(ValueError, match="beklemedeki"):
        services.delete_decision(d)


# ---------------------------------------------------------------------------
# Onay + md. 197 iade/sevk
# ---------------------------------------------------------------------------
def test_onay_kinamada_uygulamayi_acar() -> None:
    case, sid = _committee_case()
    d = services.record_decision(
        case, student_id=sid, penalty_type=PenaltyType.REPRIMAND, decision_date=date(2026, 5, 22)
    )
    services.set_decision_approval(
        d, approval_status=DecisionApprovalStatus.APPROVED, approved_on=date(2026, 5, 23)
    )
    d.refresh_from_db()
    assert d.is_enforced is True


def test_mudur_reddedemez() -> None:
    case, sid = _committee_case()
    d = services.record_decision(
        case, student_id=sid, penalty_type=PenaltyType.REPRIMAND, decision_date=date(2026, 5, 22)
    )
    with pytest.raises(ValueError, match="md. 197"):
        services.set_decision_approval(
            d, approval_status=DecisionApprovalStatus.REJECTED, approved_on=date(2026, 5, 23)
        )


def test_md197_iade_sonrasi_ilceye_sevk() -> None:
    case, sid = _committee_case()
    d = services.record_decision(
        case, student_id=sid, penalty_type=PenaltyType.REPRIMAND, decision_date=date(2026, 5, 22)
    )
    # İadesiz doğrudan sevk YASAK.
    with pytest.raises(ValueError, match="iade edilmiş"):
        services.record_principal_review(
            d, action="REFER", reason="ısrar", decided_on=date(2026, 5, 23)
        )
    services.record_principal_review(
        d, action="RETURN", reason="Gerekçe yetersiz.", decided_on=date(2026, 5, 23)
    )
    d.refresh_from_db()
    assert d.approval_status == DecisionApprovalStatus.RETURNED_TO_COMMITTEE
    services.record_principal_review(
        d, action="REFER", reason="Kurul ısrar etti.", decided_on=date(2026, 5, 25)
    )
    d.refresh_from_db()
    assert d.approval_status == DecisionApprovalStatus.REFERRED_TO_DISTRICT


# ---------------------------------------------------------------------------
# Tebliğ + itiraz — yerel tatil takvimiyle iş günü
# ---------------------------------------------------------------------------
def test_teblig_itiraz_son_gununu_hesaplar() -> None:
    case, sid = _committee_case()
    d = services.record_decision(
        case, student_id=sid, penalty_type=PenaltyType.REPRIMAND, decision_date=date(2026, 5, 22)
    )
    # Cuma 22.05.2026 tebliğ → +5 iş günü (hafta sonları atlanır) = Cuma 29.05.2026.
    services.notify_decision(d, notified_on=date(2026, 5, 22))
    d.refresh_from_db()
    assert d.appeal_deadline == date(2026, 5, 29)


def test_teblig_yerel_tatili_atlar() -> None:
    """Tatil tablosundaki gün iş günü sayılmaz — süre uzar (uçtan uca entegrasyon)."""
    case, sid = _committee_case()
    Holiday.objects.create(
        name="Kurban Bayramı", start_date=date(2026, 5, 27), end_date=date(2026, 5, 28)
    )
    d = services.record_decision(
        case, student_id=sid, penalty_type=PenaltyType.REPRIMAND, decision_date=date(2026, 5, 22)
    )
    services.notify_decision(d, notified_on=date(2026, 5, 22))
    d.refresh_from_db()
    # 25,26 iş; 27,28 tatil; 29 iş; hafta sonu; 1,2 Haziran iş → son gün 02.06.2026.
    assert d.appeal_deadline == date(2026, 6, 2)


def test_itiraz_tebligsiz_hata_ve_sure_disi_isaretlenir() -> None:
    case, sid = _committee_case()
    d = services.record_decision(
        case, student_id=sid, penalty_type=PenaltyType.REPRIMAND, decision_date=date(2026, 5, 22)
    )
    with pytest.raises(ValueError, match="tebliğ"):
        services.file_appeal(d, filed_on=date(2026, 5, 23), filed_by_role="PARENT")
    services.notify_decision(d, notified_on=date(2026, 5, 22))
    gec = services.file_appeal(d, filed_on=date(2026, 6, 15), filed_by_role="PARENT")
    assert gec.within_deadline is False  # süre dışı da KAYDEDİLİR (işaretli)


def test_okul_degistirmede_suresinde_itiraz_uygulamayi_bekletir() -> None:
    case, sid = _committee_case()
    d = services.record_decision(
        case,
        student_id=sid,
        penalty_type=PenaltyType.SCHOOL_CHANGE,
        decision_date=date(2026, 5, 22),
    )
    d.is_enforced = True
    d.save(update_fields=["is_enforced"])
    services.notify_decision(d, notified_on=date(2026, 5, 22))
    services.file_appeal(d, filed_on=date(2026, 5, 25), filed_by_role="PARENT")
    d.refresh_from_db()
    assert d.is_enforced is False  # md. 172/2-ç


def test_itiraz_bozmasi_karari_kaldirir_ve_puan_iade_edilir() -> None:
    case, sid = _committee_case()
    d = services.record_decision(
        case, student_id=sid, penalty_type=PenaltyType.REPRIMAND, decision_date=date(2026, 5, 22)
    )
    services.notify_decision(d, notified_on=date(2026, 5, 22))
    appeal = services.file_appeal(d, filed_on=date(2026, 5, 25), filed_by_role="PARENT")
    assert selectors.behavior_point_for_student(sid) == 90  # kınama −10
    services.resolve_appeal(appeal, result=AppealResult.OVERTURNED, resulted_on=date(2026, 6, 5))
    d.refresh_from_db()
    assert d.approval_status == DecisionApprovalStatus.REJECTED
    assert d.is_enforced is False
    assert selectors.behavior_point_for_student(sid) == 100  # puan iadesi (md. 171)


# ---------------------------------------------------------------------------
# close_eligible + decision_is_final
# ---------------------------------------------------------------------------
def test_close_eligible_teblig_itiraz_tampon_zinciri() -> None:
    case, sid = _committee_case()
    d = services.record_decision(
        case, student_id=sid, penalty_type=PenaltyType.REPRIMAND, decision_date=date(2026, 5, 22)
    )
    # Tebliğsiz → uygun değil (tarihsiz bloke).
    assert selectors.close_eligible(case, today=date(2026, 6, 1)) == (False, None)
    services.notify_decision(d, notified_on=date(2026, 5, 22))
    # İtiraz son günü 29.05 + 5 iş günü tampon = 05.06.2026.
    eligible, eligible_on = selectors.close_eligible(case, today=date(2026, 6, 1))
    assert eligible is False
    assert eligible_on == date(2026, 6, 5)
    # Süre dolsa da e-Okul işlendi onayı olmadan dosya kapanmaz.
    assert selectors.close_eligible(case, today=date(2026, 6, 5)) == (False, None)
    services.confirm_e_school_entry(d, processed_on=date(2026, 6, 5))
    assert selectors.close_eligible(case, today=date(2026, 6, 5)) == (True, date(2026, 6, 5))


def test_close_eligible_bekleyen_itiraz_bloke_eder() -> None:
    case, sid = _committee_case()
    d = services.record_decision(
        case, student_id=sid, penalty_type=PenaltyType.REPRIMAND, decision_date=date(2026, 5, 22)
    )
    services.notify_decision(d, notified_on=date(2026, 5, 22))
    appeal = services.file_appeal(d, filed_on=date(2026, 5, 25), filed_by_role="PARENT")
    assert selectors.close_eligible(case, today=date(2026, 7, 1)) == (False, None)
    services.resolve_appeal(appeal, result=AppealResult.UPHELD, resulted_on=date(2026, 6, 10))
    assert selectors.close_eligible(case, today=date(2026, 6, 10))[0] is False
    services.confirm_e_school_entry(d, processed_on=date(2026, 6, 10))
    assert selectors.close_eligible(case, today=date(2026, 6, 10))[0] is True


def test_e_okul_onayi_yalniz_kesinlesen_cezaya_verilir() -> None:
    case, sid = _committee_case()
    d = services.record_decision(
        case, student_id=sid, penalty_type=PenaltyType.REPRIMAND, decision_date=date(2026, 5, 22)
    )
    with pytest.raises(ValueError, match="kesinleşmeden"):
        services.confirm_e_school_entry(d, processed_on=date(2026, 5, 23))
    services.notify_decision(d, notified_on=date(2026, 5, 22))
    services.confirm_e_school_entry(d, processed_on=date(2026, 6, 1))
    d.refresh_from_db()
    assert d.e_school_processed_on == date(2026, 6, 1)


def test_decision_is_final_kurallari() -> None:
    case, sid = _committee_case()
    d = services.record_decision(
        case, student_id=sid, penalty_type=PenaltyType.REPRIMAND, decision_date=date(2026, 5, 22)
    )
    final, reason = selectors.decision_is_final(d, today=date(2026, 6, 1))
    assert final is False and "tebliğ" in reason
    services.notify_decision(d, notified_on=date(2026, 5, 22))
    d.refresh_from_db()
    final, reason = selectors.decision_is_final(d, today=date(2026, 5, 27))
    assert final is False and "itiraz süresi" in reason
    final, _ = selectors.decision_is_final(d, today=date(2026, 5, 30))
    assert final is True  # itiraz süresi doldu, itiraz yok


def test_appeals_awaiting_forward() -> None:
    case, sid = _committee_case()
    d = services.record_decision(
        case, student_id=sid, penalty_type=PenaltyType.REPRIMAND, decision_date=date(2026, 5, 22)
    )
    services.notify_decision(d, notified_on=date(2026, 5, 22))
    services.file_appeal(d, filed_on=date(2026, 5, 25), filed_by_role="PARENT")
    # Sevk son günü: 25.05 + 5 iş günü = 01.06.2026.
    assert selectors.appeals_awaiting_forward(date(2026, 6, 1)).count() == 1
    assert selectors.appeals_awaiting_forward(date(2026, 5, 28)).count() == 0
