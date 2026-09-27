from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from apps.disiplin import selectors, services
from apps.disiplin.models import (
    AppealResult,
    CaseStage,
    DisciplineCase,
    PenaltyType,
    PrincipalDecision,
)
from apps.disiplin.tests.factories import SchoolYearFactory, StudentFactory, approve

pytestmark = pytest.mark.django_db


def _committee_case(referred: date = date(2026, 5, 19)) -> tuple[DisciplineCase, int]:
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
        referred,
        override=True,
        override_reason="Rehberlik atlandı.",
        principal_decisions=[PrincipalDecision.DISCIPLINE_COMMITTEE],
    )
    return case, s.pk


def test_T1_itiraz_sonucu_kesinlesen_ceza_onay_ucundan_degistirilebiliyor() -> None:
    case, sid = _committee_case()
    d = services.record_decision(
        case, student_id=sid, penalty_type=PenaltyType.SCHOOL_CHANGE,
        decision_date=date(2026, 5, 22),
    )
    approve(d)  # ilçe kurulu onayı
    services.notify_decision(d, notified_on=date(2026, 5, 25))
    appeal = services.file_appeal(d, filed_on=date(2026, 5, 26), filed_by_role="PARENT")
    services.resolve_appeal(
        appeal, result=AppealResult.REDUCED, resulted_on=date(2026, 6, 5),
        new_penalty_type=PenaltyType.SHORT_TERM_SUSPENSION, new_suspension_days=3,
    )
    # md. 169/4: itiraz sonucu kesin. Onay ucu cezayı yine de değiştirmemeli.
    with pytest.raises(ValueError):
        services.set_decision_approval(
            d, approval_status="APPROVED", approved_on=date(2026, 6, 10),
            modified_penalty_type=PenaltyType.REPRIMAND,
        )


def test_T1b_tebligden_sonra_ceza_onay_ucundan_degistirilebiliyor() -> None:
    case, sid = _committee_case()
    d = services.record_decision(
        case, student_id=sid, penalty_type=PenaltyType.SCHOOL_CHANGE,
        decision_date=date(2026, 5, 22),
    )
    approve(d)
    services.notify_decision(d, notified_on=date(2026, 5, 25))
    with pytest.raises(ValueError):
        services.set_decision_approval(
            d, approval_status="APPROVED", approved_on=date(2026, 5, 22),
            modified_penalty_type=PenaltyType.REPRIMAND,
        )


def test_T2_teblig_sonrasi_onay_tarihi_teblig_sonrasina_tasinabiliyor() -> None:
    case, sid = _committee_case()
    d = services.record_decision(
        case, student_id=sid, penalty_type=PenaltyType.REPRIMAND,
        decision_date=date(2026, 5, 22),
    )
    approve(d)
    services.notify_decision(d, notified_on=date(2026, 5, 25))
    with pytest.raises(ValueError):
        services.set_decision_approval(
            d, approval_status="APPROVED", approved_on=date(2026, 6, 15)
        )


def test_T3_update_decision_sevkten_onceki_karar_tarihini_kabul_ediyor() -> None:
    case, sid = _committee_case()
    d = services.record_decision(
        case, student_id=sid, penalty_type=PenaltyType.REPRIMAND,
        decision_date=date(2026, 5, 22),
    )
    with pytest.raises(ValueError):
        services.update_decision(
            d, penalty_type=PenaltyType.REPRIMAND, decision_date=date(2026, 5, 1)
        )


def test_T4_imha_onizleme_kapanis_gunu_utc_kaymasi() -> None:
    from apps.disiplin.selectors.purge import case_purge_item

    SchoolYearFactory()
    s = StudentFactory()
    case = services.create_case(
        petition_date=date(2026, 5, 18), petitioner_name="A", petitioner_role="IDARE",
        summary="x", student_ids=[s.pk],
    )
    ist = ZoneInfo("Europe/Istanbul")
    case.closed_at = datetime(2026, 6, 20, 1, 30, tzinfo=ist)  # yerel 20.06 01:30
    case.current_stage = CaseStage.CLOSED
    case.save(update_fields=["closed_at", "current_stage"])
    case.refresh_from_db()
    assert case_purge_item(case).closed_on == date(2026, 6, 20)


def test_T5_geri_alinan_yazili_uyari_kalici_uyari_sayiliyor() -> None:
    SchoolYearFactory()
    s = StudentFactory()
    case = services.create_case(
        petition_date=date(2026, 5, 18), petitioner_name="A", petitioner_role="IDARE",
        summary="x", student_ids=[s.pk],
    )
    services.add_event(
        case, CaseStage.DECIDED, date(2026, 5, 19), override=True,
        override_reason="r", principal_decisions=[PrincipalDecision.WRITTEN_WARNING],
    )
    case.refresh_from_db()
    assert case.current_stage == CaseStage.CLOSED
    # Yanlış girildi: geri alınıp kurula sevk ediliyor.
    services.revert_stage(case, target_stage=CaseStage.PETITION, reason="yanlış giriş")
    services.add_event(
        case, CaseStage.DECIDED, date(2026, 5, 20), override=True,
        override_reason="r", principal_decisions=[PrincipalDecision.DISCIPLINE_COMMITTEE],
    )
    # Öğrencinin hiç uyarısı/cezası yok; başka dosyada ilk kez triaj.
    assert selectors.student_discipline_history(s.pk).warning_count == 0
