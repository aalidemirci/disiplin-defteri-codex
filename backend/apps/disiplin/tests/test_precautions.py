"""Kurul süresi uzatma + tedbir testleri (F2) — md. 175, 192/3."""

from __future__ import annotations

from datetime import date

import pytest

from apps.disiplin import selectors, services
from apps.disiplin.models import CaseStage, DisciplineCase, PrecautionStatus, PrincipalDecision
from apps.disiplin.tests.factories import SchoolYearFactory, StudentFactory

pytestmark = pytest.mark.django_db


def _committee_case() -> tuple[DisciplineCase, int]:
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
        date(2026, 5, 19),  # Salı — kurula geliş
        override=True,
        override_reason="Rehberlik atlandı.",
        principal_decisions=[PrincipalDecision.DISCIPLINE_COMMITTEE],
    )
    return case, s.pk


# ---------------------------------------------------------------------------
# Kurul karar süresi + uzatma (md. 192/3)
# ---------------------------------------------------------------------------
def test_kurul_karar_son_gunu_10_is_gunu() -> None:
    case, _sid = _committee_case()
    # Salı 19.05 + 10 iş günü → Salı 02.06.2026 (hafta sonları atlanır).
    assert selectors.committee_decision_deadline(case) == date(2026, 6, 2)


def test_sevksiz_dosyada_uzatma_hata() -> None:
    SchoolYearFactory()
    s = StudentFactory()
    case = services.create_case(
        petition_date=date(2026, 5, 18),
        petitioner_name="A",
        petitioner_role="IDARE",
        summary="x",
        student_ids=[s.pk],
    )
    with pytest.raises(ValueError, match="sevk edilmemiş"):
        services.create_extension(
            case, requested_days=5, reason="gecikme", decided_on=date(2026, 5, 20)
        )


def test_uzatma_ancak_bir_kez() -> None:
    case, _sid = _committee_case()
    ext = services.create_extension(
        case, requested_days=5, reason="İfade gecikmesi", decided_on=date(2026, 5, 25)
    )
    assert ext.original_deadline == date(2026, 6, 2)
    assert ext.new_deadline == date(2026, 6, 9)  # +5 iş günü
    with pytest.raises(ValueError, match="bir kez"):
        services.create_extension(
            case, requested_days=3, reason="ikinci", decided_on=date(2026, 5, 26)
        )


def test_onaylanmis_uzatma_son_gunu_degistirir() -> None:
    case, _sid = _committee_case()
    ext = services.create_extension(
        case, requested_days=5, reason="İfade gecikmesi", decided_on=date(2026, 5, 25)
    )
    # Onaysız uzatma son günü DEĞİŞTİRMEZ (md. 192/3 müdür onayı şartı).
    assert selectors.committee_decision_deadline(case) == date(2026, 6, 2)
    services.approve_extension(ext, approved_on=date(2026, 5, 26))
    assert selectors.committee_decision_deadline(case) == date(2026, 6, 9)


def test_cases_awaiting_committee_decision() -> None:
    case, _sid = _committee_case()
    result = selectors.cases_awaiting_committee_decision(date(2026, 6, 2))
    assert [(c.pk, d) for c, d in result] == [(case.pk, date(2026, 6, 2))]
    assert selectors.cases_awaiting_committee_decision(date(2026, 5, 29)) == []


# ---------------------------------------------------------------------------
# Tedbir (md. 175)
# ---------------------------------------------------------------------------
def test_tedbir_snapshot_tarihleri() -> None:
    case, sid = _committee_case()
    p = services.create_precaution(
        case, student_id=sid, start_date=date(2026, 5, 20), requested_days=5
    )
    # Çarşamba 20.05 + 5 iş günü (başlangıç dahil) → Salı 26.05.2026.
    assert p.end_date == date(2026, 5, 26)
    # İşleme başlama: 20.05 + 3 iş günü → Pazartesi 25.05.2026.
    assert p.process_start_deadline == date(2026, 5, 25)
    assert p.status == PrecautionStatus.ACTIVE


def test_tedbir_dahil_olmayan_ogrenci_hata() -> None:
    case, _sid = _committee_case()
    disaridan = StudentFactory()
    with pytest.raises(ValueError, match="dahil değil"):
        services.create_precaution(
            case, student_id=disaridan.pk, start_date=date(2026, 5, 20), requested_days=5
        )


def test_ayni_ogrenciye_ikinci_aktif_tedbir_hata() -> None:
    case, sid = _committee_case()
    services.create_precaution(case, student_id=sid, start_date=date(2026, 5, 20), requested_days=5)
    with pytest.raises(ValueError, match="yürürlükte"):
        services.create_precaution(
            case, student_id=sid, start_date=date(2026, 5, 21), requested_days=3
        )


def test_tedbir_kaldirma_ve_uzatma_kurallari() -> None:
    case, sid = _committee_case()
    p = services.create_precaution(
        case, student_id=sid, start_date=date(2026, 5, 20), requested_days=5
    )
    services.extend_precaution(p, additional_days=3)
    p.refresh_from_db()
    assert p.requested_days == 8
    assert p.extension_count == 1
    # Toplam 10'u aşamaz.
    with pytest.raises(ValueError, match="10 iş günü"):
        services.extend_precaution(p, additional_days=5)
    services.extend_precaution(p, additional_days=2)
    # Üçüncü uzatma yasak (md. 175/2 en fazla iki).
    with pytest.raises(ValueError, match="iki kez"):
        services.extend_precaution(p, additional_days=1)

    services.lift_precaution(p, lifted_on=date(2026, 5, 27))
    p.refresh_from_db()
    assert p.status == PrecautionStatus.LIFTED
    with pytest.raises(ValueError, match="yürürlükteki"):
        services.lift_precaution(p, lifted_on=date(2026, 5, 28))


def test_precautions_awaiting_deadline() -> None:
    case, sid = _committee_case()
    services.create_precaution(case, student_id=sid, start_date=date(2026, 5, 20), requested_days=5)
    # process_start_deadline 25.05 → o eşiğe kadar tarama yakalar.
    assert selectors.precautions_awaiting_deadline(date(2026, 5, 25)).count() == 1
    assert selectors.precautions_awaiting_deadline(date(2026, 5, 22)).count() == 0
