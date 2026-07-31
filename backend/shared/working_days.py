"""İş günü (working day) aritmetiği — ORM'siz, modüller-arası paylaşılan saf mantık.

`ogrenci_isleri` (disiplin yasal süreleri) ve `rehberlik` (sevk termini/SLA) bu saf
fonksiyonu ortak kullanır — modül sınırı (CLAUDE.md §4.1) ihlal edilmeden, çünkü
`shared` bir modül değil tabandır. İş günü tanımı `is_working_day` yüklemiyle
belirlenir; üretimde çağıran katman `core.services.is_working_day`'i (CalendarEvent
resmî/idari tatilleri gören) enjekte eder, böylece bu modül Django/ORM'siz kalır
(ADR-0009, Tur 90). Tur 189: disiplin-içi konumdan `shared`'a terfi (rehberlik de kullanır).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta

# Bir tarihin iş günü olup olmadığını söyleyen yüklem. Üretimde
# `core.services.is_working_day` (resmî/idari tatil + hafta sonu); test'te lambda.
WorkingDayPredicate = Callable[[date], bool]


def is_weekday(day: date) -> bool:
    """Varsayılan iş günü yüklemi: yalnız hafta sonu (Cmt/Pzr) tatildir."""
    return day.weekday() < 5  # 0=Pazartesi .. 4=Cuma


def add_working_days(
    start: date,
    days: int,
    *,
    is_working_day: WorkingDayPredicate | None = None,
) -> date:
    """`start` tarihinden `days` iş günü sonrasının tarihi.

    `days=0` → `start`. Negatif `days` desteklenmez (ValueError).

    İş günü tanımı `is_working_day` yüklemiyle belirlenir:
    - **None (varsayılan):** yalnız hafta sonu (Cmt/Pzr) atlanır — saf/geriye uyumlu.
    - **Verildiyse:** üretimde `core.services.is_working_day` geçilir → resmî/idari
      tatiller (CalendarEvent) de iş günü sayılmaz (ADR-0009, Tur 90). Yüklem her
      ADAY GÜN için çağrılır (başlangıç günü hariç).
    """
    if days < 0:
        raise ValueError("İş günü sayısı negatif olamaz.")
    predicate = is_working_day or is_weekday
    current = start
    remaining = days
    while remaining > 0:
        current += timedelta(days=1)
        if predicate(current):
            remaining -= 1
    return current
