"""Disiplin yasal süreleri saf mantık testleri (Tur 72, Faz 6).

`discipline_periods` ORM'siz olduğundan DB gerekmez. İş günü (hafta sonu hariç) +
mevzuat eşleme tabloları (md. 163/2, 169/3, 170) doğrulanır.
"""

from __future__ import annotations

from datetime import date

import pytest

from apps.disiplin import discipline_periods as dp
from apps.disiplin.models import ApprovalAuthority, PenaltyType

# 2026-06-01 Pazartesi, 2026-06-05 Cuma, 2026-06-06/07 hafta sonu, 2026-06-08 Pazartesi.
MON = date(2026, 6, 1)
FRI = date(2026, 6, 5)
NEXT_MON = date(2026, 6, 8)


def test_add_working_days_sifir() -> None:
    assert dp.add_working_days(MON, 0) == MON


def test_suspension_end_date_baslangic_dahil() -> None:
    # 3 gün uzaklaştırma, Pazartesi başlar → Pzt(1)/Sal(2)/Çar(3) = 2026-06-03.
    assert dp.suspension_end_date(MON, 3) == date(2026, 6, 3)
    # 1 gün → yalnız başlangıç günü.
    assert dp.suspension_end_date(MON, 1) == MON


def test_suspension_end_date_hafta_sonu_atlar() -> None:
    # Cuma başlar, 3 gün → Cuma(1)/Pzt(2)/Sal(3) = 2026-06-09 (Cmt/Pzr atlanır).
    assert dp.suspension_end_date(FRI, 3) == date(2026, 6, 9)


def test_suspension_end_date_aralik_disi() -> None:
    with pytest.raises(ValueError):
        dp.suspension_end_date(MON, 0)
    with pytest.raises(ValueError):
        dp.suspension_end_date(MON, 6)  # md. 164/2: en fazla 5 gün


def test_school_return_date_sonraki_is_gunu() -> None:
    # Bitiş Çarşamba → okula başlama Perşembe.
    assert dp.school_return_date(date(2026, 6, 3)) == date(2026, 6, 4)
    # Bitiş Cuma → okula başlama sonraki Pazartesi (hafta sonu atlanır).
    assert dp.school_return_date(FRI) == NEXT_MON


def test_suspension_dates_resmi_tatil_predicate() -> None:
    # 2026-06-02 Salı tatil → Pzt(1)/[Sal tatil]/Çar(2)/Per(3) = 2026-06-04.
    holiday = date(2026, 6, 2)
    pred = lambda d: d.weekday() < 5 and d != holiday  # noqa: E731
    assert dp.suspension_end_date(MON, 3, is_working_day=pred) == date(2026, 6, 4)


def test_add_working_days_hafta_ici() -> None:
    # Pazartesi + 4 iş günü = aynı haftanın Cuma'sı.
    assert dp.add_working_days(MON, 4) == FRI


def test_add_working_days_hafta_sonu_atlanir() -> None:
    # Pazartesi + 5 iş günü = sonraki Pazartesi (Cmt/Paz atlanır).
    assert dp.add_working_days(MON, 5) == NEXT_MON
    # Cuma + 1 iş günü = sonraki Pazartesi.
    assert dp.add_working_days(FRI, 1) == NEXT_MON


def test_add_working_days_negatif_reddedilir() -> None:
    with pytest.raises(ValueError):
        dp.add_working_days(MON, -1)


def test_add_working_days_sonuc_asla_hafta_sonu() -> None:
    for n in range(0, 30):
        assert dp.add_working_days(MON, n).weekday() < 5


def test_appeal_ve_forward_deadline_5_is_gunu() -> None:
    # md. 169/3 — tebliğ/başvuru + 5 iş günü.
    assert dp.appeal_deadline(MON) == NEXT_MON
    assert dp.forward_deadline(MON) == NEXT_MON


def test_deduction_for_md170() -> None:
    assert dp.deduction_for(PenaltyType.REPRIMAND) == 10
    assert dp.deduction_for(PenaltyType.SHORT_TERM_SUSPENSION) == 20
    assert dp.deduction_for(PenaltyType.SCHOOL_CHANGE) == 40
    assert dp.deduction_for(PenaltyType.EXPULSION) == 80
    assert dp.deduction_for("BILINMEYEN") == 0


def test_approval_authority_md163() -> None:
    assert dp.approval_authority_for(PenaltyType.REPRIMAND) == ApprovalAuthority.PRINCIPAL
    assert (
        dp.approval_authority_for(PenaltyType.SHORT_TERM_SUSPENSION) == ApprovalAuthority.PRINCIPAL
    )
    assert dp.approval_authority_for(PenaltyType.SCHOOL_CHANGE) == ApprovalAuthority.DISTRICT_BOARD
    assert dp.approval_authority_for(PenaltyType.EXPULSION) == ApprovalAuthority.PROVINCIAL_BOARD


def test_appeal_authority_md169() -> None:
    assert dp.appeal_authority_for(PenaltyType.REPRIMAND) == ApprovalAuthority.DISTRICT_BOARD
    assert dp.appeal_authority_for(PenaltyType.SCHOOL_CHANGE) == ApprovalAuthority.PROVINCIAL_BOARD
    assert dp.appeal_authority_for(PenaltyType.EXPULSION) == ApprovalAuthority.UPPER_BOARD


# =============================================================================
# Kurul süresi + tedbir saf mantık (Tur 75, Faz B) — md. 175, 192/3
# =============================================================================


def test_committee_decision_deadline_10_is_gunu() -> None:
    # md. 192/3: kurula geliş + 10 iş günü. MON + 10 iş günü = 2 hafta sonra Pazartesi.
    assert dp.committee_decision_deadline(MON) == date(2026, 6, 15)
    assert dp.COMMITTEE_DECISION_WORKING_DAYS == 10
    assert dp.COMMITTEE_EXTENSION_MAX_COUNT == 1


def test_precaution_process_start_deadline_3_is_gunu() -> None:
    # md. 175/2: tedbiri izleyen en geç 3 iş günü.
    assert dp.precaution_process_start_deadline(MON) == date(2026, 6, 4)  # MON + 3 = Perşembe


def test_precaution_end_date_baslangic_dahil() -> None:
    # 1 iş günü = yalnız başlangıç günü.
    assert dp.precaution_end_date(MON, 1) == MON
    # 5 iş günü = aynı haftanın Cuma'sı (MON..FRI dahil).
    assert dp.precaution_end_date(MON, 5) == FRI
    # 10 iş günü (md. 175/1 üst sınır) = 2 hafta sonra Cuma.
    assert dp.precaution_end_date(MON, 10) == date(2026, 6, 12)


def test_precaution_end_date_sinir_disi_reddedilir() -> None:
    with pytest.raises(ValueError):
        dp.precaution_end_date(MON, 0)
    with pytest.raises(ValueError):
        dp.precaution_end_date(MON, 11)  # md. 175/1 "on iş gününü geçmemek"
    assert dp.PRECAUTION_MAX_WORKING_DAYS == 10
    assert dp.PRECAUTION_PROCESS_START_WORKING_DAYS == 3
    assert dp.PRECAUTION_EXTENSION_MAX_COUNT == 2


# =============================================================================
# Resmî tatil yüklemi (predicate) — Tur 90, Faz 5 (ADR-0009 açık soru kapatıldı)
# =============================================================================
# 2026-06-03 Çarşamba'yı "resmî tatil" sayan bir yüklem; üretimde bu rolü
# core.services.is_working_day (CalendarEvent tatilleri) üstlenir.
_WED_HOLIDAY = date(2026, 6, 3)


def _is_wd_skip_wed(day: date) -> bool:
    """Hafta içi VE 2026-06-03 (Çarşamba) değil → iş günü."""
    return day.weekday() < 5 and day != _WED_HOLIDAY


def test_add_working_days_resmi_tatil_atlanir() -> None:
    # MON + 4 iş günü: tatilsiz Cuma (06-05); arada 06-03 tatil → bir gün kayar.
    assert dp.add_working_days(MON, 4, is_working_day=_is_wd_skip_wed) == date(2026, 6, 8)
    # Yüklem verilmezse varsayılan (yalnız hafta sonu) — değişmez.
    assert dp.add_working_days(MON, 4) == FRI


def test_appeal_deadline_resmi_tatil_kaydirir() -> None:
    # md. 169/3 tebliğ + 5 iş günü: tatilsiz NEXT_MON (06-08); 06-03 tatille +1 → 06-09.
    assert dp.appeal_deadline(MON, is_working_day=_is_wd_skip_wed) == date(2026, 6, 9)
    assert dp.appeal_deadline(MON) == NEXT_MON  # yüklemsiz değişmez


def test_committee_decision_deadline_resmi_tatil_kaydirir() -> None:
    # md. 192/3 kurula geliş + 10 iş günü: tatilsiz 06-15; 06-03 tatille +1 → 06-16.
    assert dp.committee_decision_deadline(MON, is_working_day=_is_wd_skip_wed) == date(2026, 6, 16)
    assert dp.committee_decision_deadline(MON) == date(2026, 6, 15)


def test_precaution_end_date_resmi_tatil_kaydirir() -> None:
    # md. 175/1 — 5 iş günü tedbir: tatilsiz MON..FRI; 06-03 tatille bitiş 06-08'e kayar.
    assert dp.precaution_end_date(MON, 5, is_working_day=_is_wd_skip_wed) == date(2026, 6, 8)
    assert dp.precaution_end_date(MON, 5) == FRI


def test_precaution_process_start_deadline_resmi_tatil_kaydirir() -> None:
    # md. 175/2 — tedbir + 3 iş günü: tatilsiz 06-04 (Perşembe); 06-03 tatille +1 → 06-05.
    assert dp.precaution_process_start_deadline(MON, is_working_day=_is_wd_skip_wed) == date(
        2026, 6, 5
    )
    assert dp.precaution_process_start_deadline(MON) == date(2026, 6, 4)
