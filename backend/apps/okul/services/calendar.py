"""İş günü mantığı + tatil takvimi seed'i (F1-T2; tasarım §3.4/§7).

OYS ikamesi: `core.services.is_working_day` CalendarEvent yerine yerel `Holiday`
tablosuna bakar; davranış paritesi (hafta içi + kapsayan canlı tatil yok) korunur.
Disiplin süre motoru (F2 `discipline_periods`) bu yüklemi `shared.working_days`
üzerinden enjekte eder.

Dini bayram verisi (tasarım §7): `holidays` pip paketi RET — hicri hesap Diyanet
ilanından ±1 gün sapabilir. Bunun yerine gömülü statik tablo: Diyanet takviminde
yayınlanmış yıllar TEYİTLİ (`is_estimated=False`), sonrası TAHMİNİ bayraklı ve
takvim ekranından kullanıcı-düzenlenebilir.
"""

from __future__ import annotations

from datetime import date

from django.db import transaction

from apps.okul.models import Holiday, HolidayKind, SchoolYear

# 2429 sayılı kanunun SABİT tarihli tatilleri (OYS `FIXED_OFFICIAL_HOLIDAYS` AYNEN).
# Dini bayramlar hicri takvime göre kaydığından ayrı tabloda (aşağıda).
FIXED_OFFICIAL_HOLIDAYS: tuple[tuple[int, int, str], ...] = (
    (1, 1, "Yılbaşı"),
    (4, 23, "Ulusal Egemenlik ve Çocuk Bayramı"),
    (5, 1, "Emek ve Dayanışma Günü"),
    (5, 19, "Atatürk'ü Anma, Gençlik ve Spor Bayramı"),
    (7, 15, "Demokrasi ve Millî Birlik Günü"),
    (8, 30, "Zafer Bayramı"),
    (10, 29, "Cumhuriyet Bayramı"),
)

# Dini bayramlar: (ad, başlangıç, bitiş, tahmini_mi).
# 2026 tarihleri Diyanet takviminde yayınlı → TEYİTLİ. 2027+ astronomik hesapla
# TAHMİNİ — Diyanet ilanı çıktıkça kullanıcı takvim ekranından düzeltir (arife
# yarım günleri İŞ GÜNÜ sayılır; gün bazlı yasal süre hesabına dahil edilmez).
RELIGIOUS_HOLIDAYS: tuple[tuple[str, date, date, bool], ...] = (
    ("Ramazan Bayramı", date(2026, 3, 20), date(2026, 3, 22), False),
    ("Kurban Bayramı", date(2026, 5, 27), date(2026, 5, 30), False),
    ("Ramazan Bayramı", date(2027, 3, 9), date(2027, 3, 11), True),
    ("Kurban Bayramı", date(2027, 5, 16), date(2027, 5, 19), True),
    ("Ramazan Bayramı", date(2028, 2, 26), date(2028, 2, 28), True),
    ("Kurban Bayramı", date(2028, 5, 5), date(2028, 5, 8), True),
    ("Ramazan Bayramı", date(2029, 2, 14), date(2029, 2, 16), True),
    ("Kurban Bayramı", date(2029, 4, 24), date(2029, 4, 27), True),
)


def is_working_day(day: date) -> bool:
    """Verilen tarih bir iş günü mü? (MEVZUAT kavramı — disiplin yasal süreleri.)

    İş günü = hafta içi (Pzt-Cum) VE o tarihi kapsayan canlı tatil kaydı yok.
    DİKKAT: Ara tatil / yarıyıl tatili İŞ GÜNÜDÜR (memur çalışır) — bu yüzden
    Holiday tablosuna hiç girilmez (model docstring'i + sihirbaz uyarısı).
    """
    if day.weekday() >= 5:  # 5=Cumartesi, 6=Pazar
        return False
    return not Holiday.objects.filter(start_date__lte=day, end_date__gte=day).exists()


def _add_holiday_if_missing(
    *, name: str, start: date, end: date, kind: str, is_estimated: bool
) -> bool:
    """Aynı (ad, başlangıç) canlı kayıt yoksa ekler → eklendi mi?"""
    if Holiday.objects.filter(name=name, start_date=start).exists():
        return False
    Holiday.objects.create(
        name=name, start_date=start, end_date=end, kind=kind, is_estimated=is_estimated
    )
    return True


@transaction.atomic
def seed_official_holidays(school_year: SchoolYear) -> tuple[int, int]:
    """Yıl aralığına düşen sabit resmî tatilleri ekler → (eklenen, zaten_var).

    İdempotent: aynı (ad, başlangıç) canlı kayıt varsa atlar. Ders yılı dışına
    düşen tatiller (yaz: 15 Temmuz, 30 Ağustos) yazılmaz — OYS davranış paritesi.
    """
    created = 0
    skipped = 0
    for cal_year in sorted({school_year.start_date.year, school_year.end_date.year}):
        for month, day, name in FIXED_OFFICIAL_HOLIDAYS:
            holiday = date(cal_year, month, day)
            if not (school_year.start_date <= holiday <= school_year.end_date):
                continue
            if _add_holiday_if_missing(
                name=name,
                start=holiday,
                end=holiday,
                kind=HolidayKind.OFFICIAL,
                is_estimated=False,
            ):
                created += 1
            else:
                skipped += 1
    return created, skipped


@transaction.atomic
def seed_religious_holidays(school_year: SchoolYear) -> tuple[int, int]:
    """Yıl aralığıyla kesişen dini bayramları gömülü tablodan ekler → (eklenen, zaten_var)."""
    created = 0
    skipped = 0
    for name, start, end, is_estimated in RELIGIOUS_HOLIDAYS:
        if end < school_year.start_date or start > school_year.end_date:
            continue
        if _add_holiday_if_missing(
            name=name,
            start=start,
            end=end,
            kind=HolidayKind.RELIGIOUS,
            is_estimated=is_estimated,
        ):
            created += 1
        else:
            skipped += 1
    return created, skipped


@transaction.atomic
def seed_holidays(school_year: SchoolYear) -> tuple[int, int]:
    """Sihirbaz kısayolu: sabit resmî + dini bayramları birlikte ekler."""
    c1, s1 = seed_official_holidays(school_year)
    c2, s2 = seed_religious_holidays(school_year)
    return c1 + c2, s1 + s2


@transaction.atomic
def create_holiday(
    *,
    name: str,
    start_date: date,
    end_date: date,
    kind: str = HolidayKind.OFFICIAL,
    is_estimated: bool = False,
) -> Holiday:
    """Elle tatil ekler (takvim ekranı; ör. yerel idari izin)."""
    holiday: Holiday = Holiday.objects.create(
        name=name.strip(),
        start_date=start_date,
        end_date=end_date,
        kind=kind,
        is_estimated=is_estimated,
    )
    return holiday


@transaction.atomic
def delete_holiday(holiday: Holiday) -> None:
    holiday.delete()  # soft delete (BaseModel)
