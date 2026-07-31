"""`apps.okul` modelleri — şema davranış testleri (F1-T1).

SQLite üzerinde koşullu UniqueConstraint'lerin (partial index) GERÇEKTEN
çalıştığı burada İLK KEZ doğrulanır (tasarım §4.2 — OYS'de bu kısıtlar yalnız
PostgreSQL'de koşuyordu; Django docs kısıtlamayı yalnız MySQL/Oracle için verir).
"""

from __future__ import annotations

from datetime import date

import pytest
from django.db import IntegrityError, transaction

from apps.okul.models import (
    ClassResponsibility,
    Holiday,
    HolidayKind,
    ImportRun,
    ImportSourceType,
    ImportStatus,
    Personnel,
    SchoolConfig,
    SchoolYear,
    Student,
)


# ---------------------------------------------------------------------------
# SchoolConfig — singleton
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestSchoolConfig:
    def test_load_kayit_yokken_kaydedilmemis_varsayilan_doner(self) -> None:
        """Okuma yolu DB'ye yazmaz: satır yoksa pk'sız/kaydedilmemiş nesne döner."""
        config = SchoolConfig.load()
        assert config.setup_completed is False
        assert SchoolConfig.objects.count() == 0

    def test_load_kayitli_satiri_doner(self) -> None:
        SchoolConfig.objects.create(pk=SchoolConfig.SINGLETON_PK, school_name="Deneme Lisesi")
        config = SchoolConfig.load()
        assert config.pk == SchoolConfig.SINGLETON_PK
        assert config.school_name == "Deneme Lisesi"


# ---------------------------------------------------------------------------
# SchoolYear — koşullu unique'ler (SQLite regresyonu)
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestSchoolYear:
    def test_ayni_ad_canli_iki_kayit_engellenir(self) -> None:
        SchoolYear.objects.create(
            name="2026-2027", start_date=date(2026, 9, 1), end_date=date(2027, 6, 19)
        )
        with pytest.raises(IntegrityError), transaction.atomic():
            SchoolYear.objects.create(
                name="2026-2027", start_date=date(2026, 9, 1), end_date=date(2027, 6, 19)
            )

    def test_soft_delete_sonrasi_ad_yeniden_kullanilir(self) -> None:
        """Koşullu unique yalnız CANLI satırları kapsar — SQLite partial index provası."""
        year = SchoolYear.objects.create(
            name="2026-2027", start_date=date(2026, 9, 1), end_date=date(2027, 6, 19)
        )
        year.delete()  # soft delete
        again = SchoolYear.objects.create(
            name="2026-2027", start_date=date(2026, 9, 1), end_date=date(2027, 6, 19)
        )
        assert again.pk != year.pk

    def test_ikinci_aktif_yil_engellenir(self) -> None:
        SchoolYear.objects.create(
            name="2025-2026",
            start_date=date(2025, 9, 8),
            end_date=date(2026, 6, 26),
            is_active=True,
        )
        with pytest.raises(IntegrityError), transaction.atomic():
            SchoolYear.objects.create(
                name="2026-2027",
                start_date=date(2026, 9, 1),
                end_date=date(2027, 6, 19),
                is_active=True,
            )

    def test_pasif_yillar_sinirsiz(self) -> None:
        SchoolYear.objects.create(
            name="2024-2025", start_date=date(2024, 9, 9), end_date=date(2025, 6, 20)
        )
        SchoolYear.objects.create(
            name="2025-2026", start_date=date(2025, 9, 8), end_date=date(2026, 6, 26)
        )
        assert SchoolYear.objects.filter(is_active=False).count() == 2


# ---------------------------------------------------------------------------
# ClassResponsibility
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestClassResponsibility:
    def test_ayni_yil_sinif_sube_canli_iki_kayit_engellenir(self) -> None:
        year = SchoolYear.objects.create(
            name="2026-2027",
            start_date=date(2026, 9, 1),
            end_date=date(2027, 6, 19),
        )
        ClassResponsibility.objects.create(school_year=year, class_level=10, class_section="A")
        with pytest.raises(IntegrityError), transaction.atomic():
            ClassResponsibility.objects.create(school_year=year, class_level=10, class_section="A")

    def test_sorumlular_opsiyoneldir_ve_sinif_etiketi_uretilir(self) -> None:
        year = SchoolYear.objects.create(
            name="2026-2027",
            start_date=date(2026, 9, 1),
            end_date=date(2027, 6, 19),
        )
        row = ClassResponsibility.objects.create(
            school_year=year, class_level=12, class_section="C"
        )
        assert row.class_label == "12/C"
        assert row.guidance_teacher is None


# ---------------------------------------------------------------------------
# Holiday
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestHoliday:
    def test_varsayilanlar(self) -> None:
        tatil = Holiday.objects.create(
            name="Cumhuriyet Bayramı", start_date=date(2026, 10, 29), end_date=date(2026, 10, 29)
        )
        assert tatil.kind == HolidayKind.OFFICIAL
        assert tatil.is_estimated is False

    def test_ayni_baslangic_ve_ad_canli_iki_kayit_engellenir(self) -> None:
        """Seed idempotency dayanağı: aynı (ad, başlangıç) canlı satır tekildir."""
        Holiday.objects.create(
            name="Yılbaşı", start_date=date(2027, 1, 1), end_date=date(2027, 1, 1)
        )
        with pytest.raises(IntegrityError), transaction.atomic():
            Holiday.objects.create(
                name="Yılbaşı", start_date=date(2027, 1, 1), end_date=date(2027, 1, 1)
            )


# ---------------------------------------------------------------------------
# Personnel / Student — görüntü yardımcıları
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestPersonnel:
    def test_full_name(self) -> None:
        p = Personnel.objects.create(first_name="ALİ", last_name="ÖRNEK", title="Müdür")
        assert p.full_name == "ALİ ÖRNEK"


@pytest.mark.django_db
class TestStudent:
    def test_full_name_ve_class_label(self) -> None:
        s = Student.objects.create(
            first_name="EMRE CAN",
            last_name="YILMAZ",
            class_level=10,
            class_section="A",
            student_number="2612",
        )
        assert s.full_name == "EMRE CAN YILMAZ"
        assert s.class_label == "10/A"

    def test_class_label_sinifsiz_bos(self) -> None:
        s = Student.objects.create(first_name="EMRE", last_name="YILMAZ")
        assert s.class_label == ""

    def test_ayni_tckn_canli_iki_kayit_engellenir(self) -> None:
        Student.objects.create(first_name="A", last_name="B", tckn="10000000146")
        with pytest.raises(IntegrityError), transaction.atomic():
            Student.objects.create(first_name="C", last_name="D", tckn="10000000146")

    def test_bos_tckn_coklu_kayda_izin_verir(self) -> None:
        """TCKN'siz elle eklenen öğrenciler kısıta takılmaz (koşul ~Q(tckn=''))."""
        Student.objects.create(first_name="A", last_name="B")
        Student.objects.create(first_name="C", last_name="D")
        assert Student.objects.count() == 2

    def test_soft_delete_tckn_serbest_birakir(self) -> None:
        s = Student.objects.create(first_name="A", last_name="B", tckn="10000000146")
        s.delete()
        Student.objects.create(first_name="C", last_name="D", tckn="10000000146")
        assert Student.objects.count() == 1
        assert Student.all_objects.count() == 2


# ---------------------------------------------------------------------------
# ImportRun — hash bazlı koşullu unique
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestImportRun:
    def test_ayni_hash_iki_completed_engellenir(self) -> None:
        ImportRun.objects.create(
            source_type=ImportSourceType.STUDENTS,
            file_hash="a" * 64,
            status=ImportStatus.COMPLETED,
        )
        with pytest.raises(IntegrityError), transaction.atomic():
            ImportRun.objects.create(
                source_type=ImportSourceType.STUDENTS,
                file_hash="a" * 64,
                status=ImportStatus.COMPLETED,
            )

    def test_ayni_hash_farkli_tur_serbest(self) -> None:
        ImportRun.objects.create(
            source_type=ImportSourceType.STUDENTS,
            file_hash="a" * 64,
            status=ImportStatus.COMPLETED,
        )
        ImportRun.objects.create(
            source_type=ImportSourceType.PERSONNEL,
            file_hash="a" * 64,
            status=ImportStatus.COMPLETED,
        )
        assert ImportRun.objects.count() == 2

    def test_ayni_hash_onizleme_sinirsiz(self) -> None:
        """PREVIEWED koşuları kısıt dışıdır — aynı dosya çok kez önizlenebilir."""
        for _ in range(2):
            ImportRun.objects.create(
                source_type=ImportSourceType.STUDENTS,
                file_hash="b" * 64,
                status=ImportStatus.PREVIEWED,
            )
        assert ImportRun.objects.count() == 2
