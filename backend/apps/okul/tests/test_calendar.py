"""`apps.okul.services.calendar` — iş günü + tatil seed testleri (F1-T2).

İş günü tanımı OYS `core.services.is_working_day` ile davranış paritesindedir:
hafta içi VE o tarihi kapsayan canlı tatil kaydı yok. Ara tatil/yarıyıl tatili
Holiday tablosuna hiç girilmez (memur çalışır — yasal süreler işler).
Tüm testler SABİT tarihlerle koşar (gece yarısı tuzağı yok).
"""

from __future__ import annotations

from datetime import date

import pytest

from apps.okul.models import Holiday, HolidayKind, SchoolYear
from apps.okul.services import calendar as calendar_service


@pytest.mark.django_db
class TestIsWorkingDay:
    def test_hafta_sonu_is_gunu_degil(self) -> None:
        assert calendar_service.is_working_day(date(2026, 7, 25)) is False  # Cumartesi
        assert calendar_service.is_working_day(date(2026, 7, 26)) is False  # Pazar

    def test_tatilsiz_hafta_ici_is_gunu(self) -> None:
        assert calendar_service.is_working_day(date(2026, 7, 27)) is True  # Pazartesi

    def test_tatil_kapsamindaki_gun_is_gunu_degil(self) -> None:
        Holiday.objects.create(
            name="Kurban Bayramı",
            start_date=date(2026, 5, 27),
            end_date=date(2026, 5, 30),
            kind=HolidayKind.RELIGIOUS,
        )
        assert calendar_service.is_working_day(date(2026, 5, 28)) is False  # Perşembe, bayram içi

    def test_tatil_araliginin_disi_is_gunu(self) -> None:
        Holiday.objects.create(
            name="Kurban Bayramı", start_date=date(2026, 5, 27), end_date=date(2026, 5, 30)
        )
        assert calendar_service.is_working_day(date(2026, 6, 1)) is True  # sonraki Pazartesi

    def test_soft_delete_edilmis_tatil_sayilmaz(self) -> None:
        tatil = Holiday.objects.create(
            name="İdari İzin", start_date=date(2026, 7, 27), end_date=date(2026, 7, 27)
        )
        tatil.delete()  # soft delete
        assert calendar_service.is_working_day(date(2026, 7, 27)) is True


@pytest.mark.django_db
class TestSeedOfficialHolidays:
    def _year(self) -> SchoolYear:
        year: SchoolYear = SchoolYear.objects.create(
            name="2026-2027", start_date=date(2026, 9, 1), end_date=date(2027, 6, 19)
        )
        return year

    def test_yil_araligindaki_sabit_tatiller_eklenir(self) -> None:
        year = self._year()
        created, skipped = calendar_service.seed_official_holidays(year)
        # 2026-09-01..2027-06-19 aralığına düşen sabit tatiller:
        # 29 Ekim 2026, 1 Ocak 2027, 23 Nisan 2027, 1 Mayıs 2027, 19 Mayıs 2027.
        assert created == 5
        assert skipped == 0
        names = set(Holiday.objects.values_list("name", flat=True))
        assert "Cumhuriyet Bayramı" in names
        assert "Yılbaşı" in names
        # Yaz tatilleri (15 Temmuz, 30 Ağustos) ders yılı dışı — eklenmez.
        assert "Zafer Bayramı" not in names

    def test_ikinci_kosut_idempotent(self) -> None:
        year = self._year()
        calendar_service.seed_official_holidays(year)
        created, skipped = calendar_service.seed_official_holidays(year)
        assert created == 0
        assert skipped == 5

    def test_sabit_tatil_kind_official(self) -> None:
        calendar_service.seed_official_holidays(self._year())
        assert set(Holiday.objects.values_list("kind", flat=True)) == {HolidayKind.OFFICIAL}


@pytest.mark.django_db
class TestSeedReligiousHolidays:
    def test_diyanet_teyitli_2026_bayramlari(self) -> None:
        """2025-2026 yılı: Ramazan (20-22 Mart 2026) + Kurban (27-30 Mayıs 2026) TEYİTLİ."""
        year = SchoolYear.objects.create(
            name="2025-2026", start_date=date(2025, 9, 8), end_date=date(2026, 6, 26)
        )
        created, _skipped = calendar_service.seed_religious_holidays(year)
        assert created == 2
        ramazan = Holiday.objects.get(name__contains="Ramazan")
        assert ramazan.start_date == date(2026, 3, 20)
        assert ramazan.end_date == date(2026, 3, 22)
        assert ramazan.is_estimated is False
        assert ramazan.kind == HolidayKind.RELIGIOUS

    def test_sonraki_yillar_tahmini_bayrakli(self) -> None:
        year = SchoolYear.objects.create(
            name="2026-2027", start_date=date(2026, 9, 1), end_date=date(2027, 6, 19)
        )
        created, _skipped = calendar_service.seed_religious_holidays(year)
        assert created == 2  # Ramazan Mart 2027 + Kurban Mayıs 2027
        assert set(Holiday.objects.values_list("is_estimated", flat=True)) == {True}

    def test_idempotent(self) -> None:
        year = SchoolYear.objects.create(
            name="2025-2026", start_date=date(2025, 9, 8), end_date=date(2026, 6, 26)
        )
        calendar_service.seed_religious_holidays(year)
        created, skipped = calendar_service.seed_religious_holidays(year)
        assert created == 0
        assert skipped == 2

    def test_tablo_disi_yil_sessiz_sifir(self) -> None:
        """Gömülü tablonun kapsamadığı yıl: hata yok, (0, 0) döner (bulgu #17)."""
        year = SchoolYear.objects.create(
            name="2031-2032", start_date=date(2031, 9, 1), end_date=date(2032, 6, 18)
        )
        assert calendar_service.seed_religious_holidays(year) == (0, 0)

    def test_kesisim_siniri_bayram_baslangic_gunu(self) -> None:
        """Yıl tam bayramın ilk günü bitiyorsa bayram DAHİL (kesişim, kapsama değil)."""
        year = SchoolYear.objects.create(
            name="kesisim", start_date=date(2026, 9, 1), end_date=date(2027, 3, 9)
        )
        created, _ = calendar_service.seed_religious_holidays(year)
        assert created == 1
        assert Holiday.objects.get().start_date == date(2027, 3, 9)


@pytest.mark.django_db
class TestSeedHolidaysBilesik:
    def test_toplam_ve_turler(self) -> None:
        year = SchoolYear.objects.create(
            name="2026-2027", start_date=date(2026, 9, 1), end_date=date(2027, 6, 19)
        )
        created, skipped = calendar_service.seed_holidays(year)
        assert created == 7  # 5 sabit resmî + Ramazan/Kurban 2027
        assert skipped == 0
        assert set(Holiday.objects.values_list("kind", flat=True)) == {
            HolidayKind.OFFICIAL,
            HolidayKind.RELIGIOUS,
        }


@pytest.mark.django_db
class TestWorkingDayIntegration:
    def test_shared_add_working_days_tatili_atlar(self) -> None:
        """`shared.working_days.add_working_days` + yerel yüklem uçtan uca çalışır."""
        from shared.working_days import add_working_days

        Holiday.objects.create(
            name="Cumhuriyet Bayramı", start_date=date(2026, 10, 29), end_date=date(2026, 10, 29)
        )
        # 28 Ekim 2026 Çarşamba + 2 iş günü: 29 (tatil) ve hafta sonu atlanır → 2 Kasım Pazartesi.
        result = add_working_days(
            date(2026, 10, 28), 2, is_working_day=calendar_service.is_working_day
        )
        assert result == date(2026, 11, 2)
