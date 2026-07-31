"""`shared.working_days.add_working_days` saf mantık testleri.

OYS'nin `apps/ogrenci_isleri/tests/test_discipline_periods.py` dosyasındaki saf
`add_working_days` vakalarından uyarlandı (ORM'siz, DB gerekmez — ilgili modül
bu depoda yok, bu yüzden testler doğrudan `shared.working_days`'e karşı yazıldı).
Mevcut davranış SABİTLENİR, değiştirilmez: hafta sonu atlama, predicate
enjeksiyonu (resmî tatil), 0 gün, negatif değer reddi.
"""

from __future__ import annotations

from datetime import date

import pytest

from shared.working_days import add_working_days

# 2026-06-01 Pazartesi, 2026-06-05 Cuma, 2026-06-06/07 hafta sonu, 2026-06-08 Pazartesi.
MON = date(2026, 6, 1)
FRI = date(2026, 6, 5)
NEXT_MON = date(2026, 6, 8)


def test_add_working_days_sifir_gun() -> None:
    """0 gün → başlangıç tarihinin kendisi."""
    assert add_working_days(MON, 0) == MON


def test_add_working_days_hafta_ici() -> None:
    """Pazartesi + 4 iş günü = aynı haftanın Cuma'sı."""
    assert add_working_days(MON, 4) == FRI


def test_add_working_days_hafta_sonu_atlanir() -> None:
    """Pazartesi + 5 iş günü = sonraki Pazartesi (Cmt/Pzr atlanır)."""
    assert add_working_days(MON, 5) == NEXT_MON
    # Cuma + 1 iş günü = sonraki Pazartesi.
    assert add_working_days(FRI, 1) == NEXT_MON


def test_add_working_days_negatif_reddedilir() -> None:
    """Negatif gün sayısı desteklenmez → ValueError."""
    with pytest.raises(ValueError):
        add_working_days(MON, -1)


def test_add_working_days_sonuc_asla_hafta_sonu() -> None:
    """Varsayılan yüklemle üretilen her sonuç hafta içi bir gündür."""
    for n in range(30):
        assert add_working_days(MON, n).weekday() < 5


def test_add_working_days_predicate_enjeksiyonu_resmi_tatil() -> None:
    """`is_working_day` yüklemi verilirse ek bir gün (resmî tatil) de atlanır."""
    holiday = date(2026, 6, 3)  # Çarşamba

    def is_working_day(day: date) -> bool:
        return day.weekday() < 5 and day != holiday

    # Tatilsiz MON + 4 iş günü = FRI (06-05); 06-03 tatille bir gün kayar → 06-08.
    assert add_working_days(MON, 4, is_working_day=is_working_day) == date(2026, 6, 8)
    # Yüklem verilmezse varsayılan (yalnız hafta sonu) — değişmez.
    assert add_working_days(MON, 4) == FRI
