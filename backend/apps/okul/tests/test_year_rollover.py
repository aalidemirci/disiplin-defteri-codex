"""Yıl devri sihirbazı testleri (F5-D3; tasarım §4.6).

Kapsam:
- Yeni yıl aktifleşince eskisinin pasifleşmesi (tek-aktif kuralı devrin içinde).
- `case_no` ön ekinin yeni yıla geçmesi ve ESKİ numaraların BOZULMAMASI (regresyon).
- Yeni yılın tatillerinin seed edilmesi (dini bayram tahmini bayrağı korunur).
- Toplu sınıf yükseltmenin kaydırmasız çalışması (9→10 olan öğrenci 11 OLMAZ),
  12'lerin "Ayrıldı" işaretlenmesi, önizlemenin hiçbir şey yazmaması.
- Kapanmamış eski-yıl dosyalarının devri ENGELLEMEMESİ (yalnız uyarıdır).

`apps.disiplin` yalnız TESTTE import edilir: devrin disiplin tarafındaki
sonucunu (dosya no ön eki) doğrulamak modüller arası sözleşmenin regresyonudur;
üretim kodunda `apps.okul` → `apps.disiplin` bağı YOKTUR (bkz. year_rollover.py
modül başlığı).
"""

from __future__ import annotations

from datetime import date

import pytest
from rest_framework.test import APIClient

from apps.okul.models import Holiday, SchoolYear, Student, StudentStatus
from apps.okul.services import year_rollover


@pytest.fixture
def client() -> APIClient:
    return APIClient()


@pytest.fixture
def eski_yil() -> SchoolYear:
    year: SchoolYear = SchoolYear.objects.create(
        name="2025-2026",
        start_date=date(2025, 9, 8),
        end_date=date(2026, 6, 26),
        is_active=True,
    )
    return year


def _ogrenci(*, level: int | None, no: str, status: str = StudentStatus.ACTIVE) -> Student:
    student: Student = Student.objects.create(
        first_name="EMRE",
        last_name=f"YILMAZ{no}",
        student_number=no,
        class_level=level,
        class_section="A",
        status=status,
    )
    return student


# ---------------------------------------------------------------------------
# 1. Sonraki yıl önerisi
# ---------------------------------------------------------------------------
class TestSuggestNextYear:
    def test_aktif_yildan_bir_yil_ileri_onerir(self) -> None:
        onceki = SchoolYear(
            name="2025-2026", start_date=date(2025, 9, 8), end_date=date(2026, 6, 26)
        )
        oneri = year_rollover.suggest_next_year(onceki)
        assert oneri.name == "2026-2027"
        assert oneri.start_date == date(2026, 9, 8)
        assert oneri.end_date == date(2027, 6, 26)

    def test_artik_gun_29_subat_28ine_kayar(self) -> None:
        onceki = SchoolYear(
            name="2023-2024", start_date=date(2024, 2, 29), end_date=date(2024, 6, 26)
        )
        oneri = year_rollover.suggest_next_year(onceki)
        assert oneri.start_date == date(2025, 2, 28)

    def test_onceki_yil_yoksa_bugunden_turetir(self) -> None:
        oneri = year_rollover.suggest_next_year(None, today=date(2026, 7, 24))
        assert oneri.name == "2026-2027"
        assert oneri.start_date.year == 2026
        assert oneri.end_date.year == 2027

    def test_onceki_yil_yoksa_yil_basinda_bir_onceki_eylulu_esas_alir(self) -> None:
        oneri = year_rollover.suggest_next_year(None, today=date(2027, 3, 1))
        assert oneri.name == "2026-2027"


# ---------------------------------------------------------------------------
# 2. Yeni ders yılı + tek-aktif kuralı + tatil seed'i
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestCreateNextSchoolYear:
    def test_yeni_yil_aktiflesir_eski_yil_pasiflesir(self, eski_yil: SchoolYear) -> None:
        sonuc = year_rollover.create_next_school_year(
            name="2026-2027", start_date=date(2026, 9, 14), end_date=date(2027, 6, 19)
        )
        eski_yil.refresh_from_db()
        assert sonuc.school_year.is_active is True
        assert eski_yil.is_active is False
        assert sonuc.previous_school_year_name == "2025-2026"
        assert SchoolYear.objects.filter(is_active=True).count() == 1

    def test_yeni_yilin_tatilleri_seed_edilir(self, eski_yil: SchoolYear) -> None:
        sonuc = year_rollover.create_next_school_year(
            name="2027-2028", start_date=date(2027, 9, 13), end_date=date(2028, 6, 19)
        )
        assert sonuc.holidays_created > 0
        assert Holiday.objects.filter(name="Cumhuriyet Bayramı", start_date=date(2027, 10, 29))
        # Dini bayram tahmini bayrağı seed sırasında korunur (Diyanet ilanı öncesi).
        ramazan = Holiday.objects.filter(name="Ramazan Bayramı", start_date=date(2028, 2, 26))
        assert ramazan.exists()
        assert ramazan.first() is not None and ramazan.first().is_estimated is True  # type: ignore[union-attr]

    def test_tatil_seed_kapatilabilir(self, eski_yil: SchoolYear) -> None:
        sonuc = year_rollover.create_next_school_year(
            name="2026-2027",
            start_date=date(2026, 9, 14),
            end_date=date(2027, 6, 19),
            seed_holidays=False,
        )
        assert sonuc.holidays_created == 0
        assert Holiday.objects.count() == 0

    def test_ayni_adli_yil_reddedilir(self, eski_yil: SchoolYear) -> None:
        with pytest.raises(ValueError, match="zaten"):
            year_rollover.create_next_school_year(
                name="2025-2026", start_date=date(2026, 9, 14), end_date=date(2027, 6, 19)
            )

    def test_bitis_baslangictan_once_reddedilir(self, eski_yil: SchoolYear) -> None:
        with pytest.raises(ValueError, match="Bitiş"):
            year_rollover.create_next_school_year(
                name="2026-2027", start_date=date(2027, 6, 19), end_date=date(2026, 9, 14)
            )

    def test_geriye_donuk_yil_reddedilir(self, eski_yil: SchoolYear) -> None:
        """Devir İLERİ yönlüdür: yeni yıl aktif yıldan önce başlayamaz."""
        with pytest.raises(ValueError, match="sonra başlamalıdır"):
            year_rollover.create_next_school_year(
                name="2024-2025", start_date=date(2024, 9, 9), end_date=date(2025, 6, 20)
            )

    def test_bos_ad_reddedilir(self, eski_yil: SchoolYear) -> None:
        with pytest.raises(ValueError, match="adı"):
            year_rollover.create_next_school_year(
                name="   ", start_date=date(2026, 9, 14), end_date=date(2027, 6, 19)
            )

    def test_ilk_yil_yoksa_devir_yine_calisir(self) -> None:
        sonuc = year_rollover.create_next_school_year(
            name="2026-2027", start_date=date(2026, 9, 14), end_date=date(2027, 6, 19)
        )
        assert sonuc.previous_school_year_name == ""
        assert sonuc.school_year.is_active is True


# ---------------------------------------------------------------------------
# 3. case_no regresyonu (modüller arası sözleşme)
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestCaseNoAfterRollover:
    def test_yeni_yilda_numara_1den_baslar_eskiler_bozulmaz(self, eski_yil: SchoolYear) -> None:
        from apps.disiplin.services import cases as case_services

        ogrenci = _ogrenci(level=10, no="1001")
        eski_dosya = case_services.create_case(
            petition_date=date(2026, 5, 20),
            petitioner_name="İdare",
            petitioner_role="IDARE",
            summary="Eski yıl olayı.",
            student_ids=[ogrenci.id],
        )
        assert eski_dosya.case_no == "2025-2026-0001"

        year_rollover.create_next_school_year(
            name="2026-2027", start_date=date(2026, 9, 14), end_date=date(2027, 6, 19)
        )

        yeni_dosya = case_services.create_case(
            petition_date=date(2026, 10, 2),
            petitioner_name="İdare",
            petitioner_role="IDARE",
            summary="Yeni yıl olayı.",
            student_ids=[ogrenci.id],
        )
        assert yeni_dosya.case_no == "2026-2027-0001"

        eski_dosya.refresh_from_db()
        assert eski_dosya.case_no == "2025-2026-0001"

    def test_kapanmamis_eski_dosya_devri_engellemez(self, eski_yil: SchoolYear) -> None:
        from apps.disiplin.services import cases as case_services

        ogrenci = _ogrenci(level=11, no="1002")
        acik_dosya = case_services.create_case(
            petition_date=date(2026, 5, 20),
            petitioner_name="İdare",
            petitioner_role="IDARE",
            summary="Süreci yıl aşan olay.",
            student_ids=[ogrenci.id],
        )
        assert acik_dosya.closed_at is None

        sonuc = year_rollover.create_next_school_year(
            name="2026-2027", start_date=date(2026, 9, 14), end_date=date(2027, 6, 19)
        )
        assert sonuc.school_year.is_active is True

        acik_dosya.refresh_from_db()
        assert acik_dosya.closed_at is None
        assert acik_dosya.case_no == "2025-2026-0001"


# ---------------------------------------------------------------------------
# 4. Toplu sınıf yükseltme
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestPromoteStudents:
    def test_yukseltme_kaydirmasizdir(self) -> None:
        """9→10, 10→11, 11→12 TEK adımdır; 9. sınıf öğrencisi 11 OLMAZ."""
        dokuz = _ogrenci(level=9, no="2001")
        on = _ogrenci(level=10, no="2002")
        onbir = _ogrenci(level=11, no="2003")

        rapor = year_rollover.promote_students(apply=True)

        dokuz.refresh_from_db()
        on.refresh_from_db()
        onbir.refresh_from_db()
        assert dokuz.class_level == 10
        assert on.class_level == 11
        assert onbir.class_level == 12
        assert onbir.status == StudentStatus.ACTIVE
        assert rapor.promoted == 3
        assert rapor.applied is True

    def test_12ler_ayrildi_isaretlenir_kayit_silinmez(self) -> None:
        oniki = _ogrenci(level=12, no="2004")
        rapor = year_rollover.promote_students(graduate_final_level=True, apply=True)

        oniki.refresh_from_db()
        assert oniki.status == StudentStatus.LEFT
        # Mezun olduğu sınıf geçmiş kaydı olarak KORUNUR (12'de kalır).
        assert oniki.class_level == 12
        assert rapor.graduated == 1
        assert Student.objects.filter(pk=oniki.pk).exists()

    def test_yeni_12ler_ayni_kosuda_mezun_edilmez(self) -> None:
        """Sıra tuzağı: 11→12 yükselen öğrenci AYNI koşuda mezun sayılmamalı."""
        onbir = _ogrenci(level=11, no="2005")
        oniki = _ogrenci(level=12, no="2006")

        year_rollover.promote_students(graduate_final_level=True, apply=True)

        onbir.refresh_from_db()
        oniki.refresh_from_db()
        assert onbir.class_level == 12
        assert onbir.status == StudentStatus.ACTIVE
        assert oniki.status == StudentStatus.LEFT

    def test_12ler_secenekle_dokunulmaz_kalir(self) -> None:
        oniki = _ogrenci(level=12, no="2007")
        rapor = year_rollover.promote_students(graduate_final_level=False, apply=True)

        oniki.refresh_from_db()
        assert oniki.status == StudentStatus.ACTIVE
        assert oniki.class_level == 12
        assert rapor.graduated == 0
        assert rapor.final_level_kept == 1

    def test_pasif_ogrenci_yukseltilmez(self) -> None:
        ayrilmis = _ogrenci(level=10, no="2008", status=StudentStatus.LEFT)
        rapor = year_rollover.promote_students(apply=True)

        ayrilmis.refresh_from_db()
        assert ayrilmis.class_level == 10
        assert rapor.promoted == 0
        assert rapor.skipped_inactive == 1

    def test_sinifsiz_ogrenci_atlanir(self) -> None:
        sinifsiz = _ogrenci(level=None, no="2009")
        rapor = year_rollover.promote_students(apply=True)

        sinifsiz.refresh_from_db()
        assert sinifsiz.class_level is None
        assert rapor.skipped_no_level == 1

    def test_onizleme_hicbir_sey_yazmaz(self) -> None:
        dokuz = _ogrenci(level=9, no="2010")
        oniki = _ogrenci(level=12, no="2011")

        rapor = year_rollover.promote_students(apply=False)

        dokuz.refresh_from_db()
        oniki.refresh_from_db()
        assert dokuz.class_level == 9
        assert oniki.status == StudentStatus.ACTIVE
        assert rapor.applied is False
        assert rapor.promoted == 1
        assert rapor.graduated == 1

    def test_seviye_dokumu_raporda_gorunur(self) -> None:
        _ogrenci(level=9, no="2012")
        _ogrenci(level=9, no="2013")
        _ogrenci(level=11, no="2014")

        rapor = year_rollover.promote_students(apply=False)
        dokum = {m.from_level: m.count for m in rapor.moves}
        assert dokum == {9: 2, 10: 0, 11: 1}
        assert rapor.to_dict()["promoted"] == 3

    def test_aralik_disi_seviye_yukseltilmez(self) -> None:
        """9-12 dışı (bozuk/eski veri) seviye SESSİZCE kaydırılmaz, raporlanır."""
        garip = _ogrenci(level=5, no="2015")
        rapor = year_rollover.promote_students(apply=True)

        garip.refresh_from_db()
        assert garip.class_level == 5
        assert rapor.skipped_out_of_range == 1


# ---------------------------------------------------------------------------
# 5. Devir durumu özeti
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestRolloverStatus:
    def test_ozet_aktif_yil_ve_oneri_dondurur(self, eski_yil: SchoolYear) -> None:
        _ogrenci(level=9, no="3001")
        _ogrenci(level=12, no="3002")
        _ogrenci(level=None, no="3003")

        durum = year_rollover.rollover_status()
        assert durum.active_school_year is not None
        assert durum.active_school_year.name == "2025-2026"
        assert durum.suggestion.name == "2026-2027"
        assert durum.active_student_count == 3
        assert durum.students_without_level == 1
        # Döküm YÜKSELTME değil, mevcut dağılımdır (12'nin "hedef seviyesi" yoktur).
        assert [(lc.level, lc.count) for lc in durum.level_counts] == [(9, 1), (12, 1)]


# ---------------------------------------------------------------------------
# 6. API uçları
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestYearRolloverApi:
    def test_durum_ucu(self, client: APIClient, eski_yil: SchoolYear) -> None:
        resp = client.get("/api/v1/year-rollover/status/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["active_school_year"]["name"] == "2025-2026"
        assert data["suggested_year"]["name"] == "2026-2027"
        assert data["students_without_level"] == 0
        assert data["level_counts"] == []

    def test_yeni_yil_ucu(self, client: APIClient, eski_yil: SchoolYear) -> None:
        resp = client.post(
            "/api/v1/year-rollover/school-year/",
            {"name": "2026-2027", "start_date": "2026-09-14", "end_date": "2027-06-19"},
            format="json",
        )
        assert resp.status_code == 201, resp.content
        data = resp.json()
        assert data["school_year"]["name"] == "2026-2027"
        assert data["school_year"]["is_active"] is True
        assert data["previous_school_year_name"] == "2025-2026"
        assert data["holidays_created"] > 0
        eski_yil.refresh_from_db()
        assert eski_yil.is_active is False

    def test_yeni_yil_ucu_servis_hatasini_400e_cevirir(
        self, client: APIClient, eski_yil: SchoolYear
    ) -> None:
        resp = client.post(
            "/api/v1/year-rollover/school-year/",
            {"name": "2025-2026", "start_date": "2026-09-14", "end_date": "2027-06-19"},
            format="json",
        )
        assert resp.status_code == 400
        assert resp.json()["code"] == "validation_error"

    def test_yukseltme_ucu_onizleme_yazmaz(self, client: APIClient) -> None:
        dokuz = _ogrenci(level=9, no="4001")
        resp = client.post(
            "/api/v1/year-rollover/promote-students/",
            {"apply": False},
            format="json",
        )
        assert resp.status_code == 200
        assert resp.json()["applied"] is False
        assert resp.json()["promoted"] == 1
        dokuz.refresh_from_db()
        assert dokuz.class_level == 9

    def test_yukseltme_ucu_uygular(self, client: APIClient) -> None:
        dokuz = _ogrenci(level=9, no="4002")
        oniki = _ogrenci(level=12, no="4003")
        resp = client.post(
            "/api/v1/year-rollover/promote-students/",
            {"apply": True, "graduate_final_level": True},
            format="json",
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["applied"] is True
        assert body["promoted"] == 1
        assert body["graduated"] == 1
        dokuz.refresh_from_db()
        oniki.refresh_from_db()
        assert dokuz.class_level == 10
        assert oniki.status == StudentStatus.LEFT
