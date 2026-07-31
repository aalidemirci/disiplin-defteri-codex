"""`apps.okul.services.imports` — içe aktarma servisleri (F1-T5).

OYS `core.services.imports`'tan DÜZLEŞTİRİLMİŞ hedefe uyarlama (tasarım §4.7):
- Enrollment/NameHistory/Parent/Link YOK → Student satır içi alanlar.
- Sorumlu veli (Veli Kim) → guardian_* alanları; DİĞER veli telefonu → phone2.
- xlsx ve pano yapıştırması AYNI boru hattı (rows matrisi).
- Idempotency UYARIDIR, engel değil: aynı hash yeniden commit edilebilir
  (mevcut COMPLETED ImportRun satırı güncellenir — koşullu unique bozulmaz).
- Önizleme (dry-run) gerçek ingest + rollback (%100 parite) + PREVIEWED izi.
"""

from __future__ import annotations

import pytest

from apps.okul.models import (
    ClassResponsibility,
    ImportRun,
    ImportSourceType,
    ImportStatus,
    Personnel,
    SchoolYear,
    Student,
)
from apps.okul.services import imports as import_service
from apps.okul.tests._fixtures import AILE_KAYA, AILE_YILMAZ, TCKN_OGRENCI_1, TCKN_OGRENCI_2
from apps.okul.tests.test_excel_veli_parser import make_xlsx


def _yilmaz_row(sinif: str = "10/A", numara: int = 2612) -> list[object]:
    return [
        sinif,
        TCKN_OGRENCI_1,
        numara,
        AILE_YILMAZ["ogrenci_ad_soyad"],
        "ANNE",
        AILE_YILMAZ["anne_ad_soyad"],
        AILE_YILMAZ["anne_tel"],
        AILE_YILMAZ["baba_ad_soyad"],
        AILE_YILMAZ["baba_tel"],
    ]


@pytest.mark.django_db
class TestStudentCommit:
    def test_yeni_ogrenci_ve_veli_duzlestirmesi(self) -> None:
        report = import_service.commit_students_file(
            file_bytes=make_xlsx([_yilmaz_row()]), file_name="veli.xlsx"
        )
        assert report.created_students == 1
        s = Student.objects.get()
        assert s.tckn == str(TCKN_OGRENCI_1)
        assert s.first_name == AILE_YILMAZ["ogrenci_first"]
        assert s.class_level == 10 and s.class_section == "A"
        assert s.student_number == "2612"
        # Veli Kim: ANNE → sorumlu veli anne; diğer velinin telefonu phone2.
        assert s.guardian_name == AILE_YILMAZ["anne_ad_soyad"]
        assert s.guardian_kinship == "ANNE"
        assert s.guardian_phone == f"0{AILE_YILMAZ['anne_tel']}"
        assert s.guardian_phone2 == f"0{AILE_YILMAZ['baba_tel']}"

    def test_tckn_upsert_ikinci_kayit_acilmaz(self) -> None:
        import_service.commit_students_file(file_bytes=make_xlsx([_yilmaz_row()]))
        report = import_service.commit_students_file(
            file_bytes=make_xlsx([_yilmaz_row(sinif="11/B", numara=999)])
        )
        assert report.created_students == 0
        assert report.updated_students == 1
        s = Student.objects.get()
        assert s.class_level == 11 and s.class_section == "B"
        assert s.student_number == "999"

    def test_ayni_veri_unchanged_sayilir(self) -> None:
        import_service.commit_students_file(file_bytes=make_xlsx([_yilmaz_row()]))
        report = import_service.commit_students_file(file_bytes=make_xlsx([_yilmaz_row()]))
        assert report.updated_students == 0
        assert report.unchanged_students == 1

    def test_gecersiz_tckn_satiri_atlanir_maskeli(self) -> None:
        row = _yilmaz_row()
        row[1] = "12345"  # geçersiz TCKN
        report = import_service.commit_students_file(file_bytes=make_xlsx([row]))
        assert report.created_students == 0
        assert len(report.skipped) == 1
        # Ham TCKN rapora maskesiz düşmez.
        assert "12345" not in report.skipped[0].raw_value

    def test_sinif_cozulemezse_atlanir(self) -> None:
        row = _yilmaz_row(sinif="13/A")  # 9-12 dışı
        report = import_service.commit_students_file(file_bytes=make_xlsx([row]))
        assert report.created_students == 0
        assert len(report.skipped) == 1

    def test_ayni_dosya_yeniden_commit_uyari_ama_islenir(self) -> None:
        data = make_xlsx([_yilmaz_row()])
        first = import_service.commit_students_file(file_bytes=data)
        assert first.already_imported is False
        second = import_service.commit_students_file(file_bytes=data)
        assert second.already_imported is True
        assert second.processed == 1  # yine işlendi (güncelleme meşru)
        # Koşullu unique bozulmadı: tek COMPLETED satırı (güncellenmiş) var.
        assert (
            ImportRun.objects.filter(
                source_type=ImportSourceType.STUDENTS, status=ImportStatus.COMPLETED
            ).count()
            == 1
        )

    def test_tcknsiz_yeni_sablon_okul_numarasiyla_upsert_ve_sinif_uretir(self) -> None:
        SchoolYear.objects.create(
            name="2025-2026",
            start_date="2025-09-08",
            end_date="2026-06-26",
            is_active=True,
        )
        header = "Sınıf\tOkul Numarası\tÖğrenci Adı\tÖğrenci Soyadı\tÖğrenci Doğum Tarihi\n"
        first = import_service.commit_students_text(
            text=header + "9/A\t1001\tALİ CAN\tYILMAZ\t01.01.2011\n"
        )
        second = import_service.commit_students_text(
            text=header + "10/B\t1001\tALİ CAN\tYILMAZ\t01.01.2011\n"
        )
        assert first.created_students == 1
        assert second.updated_students == 1
        assert Student.objects.count() == 1
        assert Student.objects.get().class_label == "10/B"
        assert ClassResponsibility.objects.filter(class_level=9, class_section="A").exists()
        assert ClassResponsibility.objects.filter(class_level=10, class_section="B").exists()


@pytest.mark.django_db
class TestStudentPreview:
    def test_onizleme_yazmaz_ama_rapor_uretir(self) -> None:
        report = import_service.preview_students_file(file_bytes=make_xlsx([_yilmaz_row()]))
        assert report.dry_run is True
        assert report.created_students == 1  # simülasyon sonucu
        assert Student.objects.count() == 0  # domain yazımı YOK
        run = ImportRun.objects.get()
        assert run.status == ImportStatus.PREVIEWED

    def test_onizleme_tekrarlanabilir(self) -> None:
        data = make_xlsx([_yilmaz_row()])
        import_service.preview_students_file(file_bytes=data)
        import_service.preview_students_file(file_bytes=data)
        assert ImportRun.objects.filter(status=ImportStatus.PREVIEWED).count() == 2


@pytest.mark.django_db
class TestStudentPaste:
    def test_yapistirma_ayni_boru_hatti(self) -> None:
        text = (
            "Sınıf\tTCKN\tNuma\tAdı Soyadı\tVeli Kim\tAnne Adı SOYADI\tAnneTel\t"
            "Baba Adı SOYADI\tBabaTel\n"
            f"9/B\t{TCKN_OGRENCI_2}\t101\t{AILE_KAYA['ogrenci_ad_soyad']}\tANNE\t"
            f"{AILE_KAYA['anne_ad_soyad']}\t0{AILE_KAYA['anne_tel']}\t\t\n"
        )
        report = import_service.commit_students_text(text=text)
        assert report.created_students == 1
        s = Student.objects.get()
        assert s.tckn == str(TCKN_OGRENCI_2)
        assert s.guardian_phone == f"0{AILE_KAYA['anne_tel']}"
        assert s.guardian_phone2 == ""  # baba bilgisi yok

    def test_ayni_metin_ayni_hash(self) -> None:
        text = (
            "Sınıf\tTCKN\tNuma\tAdı Soyadı\tVeli Kim\tAnne Adı SOYADI\tAnneTel\t"
            "Baba Adı SOYADI\tBabaTel\n"
            f"9/B\t{TCKN_OGRENCI_2}\t101\t{AILE_KAYA['ogrenci_ad_soyad']}\tANNE\t"
            f"{AILE_KAYA['anne_ad_soyad']}\t0{AILE_KAYA['anne_tel']}\t\t\n"
        )
        import_service.commit_students_text(text=text)
        second = import_service.commit_students_text(text=text)
        assert second.already_imported is True


@pytest.mark.django_db
class TestGuardianFallback:
    def test_sorumlu_anne_ama_anne_bilgisi_yok_baba_varsayilir(self) -> None:
        row: list[object] = [
            "10/A",
            TCKN_OGRENCI_1,
            2612,
            AILE_YILMAZ["ogrenci_ad_soyad"],
            "ANNE",
            "",  # anne adı yok
            "",  # anne tel yok
            AILE_YILMAZ["baba_ad_soyad"],
            AILE_YILMAZ["baba_tel"],
        ]
        report = import_service.commit_students_file(file_bytes=make_xlsx([row]))
        s = Student.objects.get()
        assert s.guardian_kinship == "BABA"
        assert s.guardian_name == AILE_YILMAZ["baba_ad_soyad"]
        assert any(w.field == "guardian" for w in report.warnings)

    def test_veli_kim_bos_baba_varsayilir_uyarili(self) -> None:
        row = _yilmaz_row()
        row[4] = ""
        report = import_service.commit_students_file(file_bytes=make_xlsx([row]))
        s = Student.objects.get()
        assert s.guardian_kinship == "BABA"
        assert any(w.field == "guardian" for w in report.warnings)


@pytest.mark.django_db
class TestPersonnelImport:
    HEADER = "Ad Soyad\tUnvan\tBranş\n"

    def test_commit_yeni_personel(self) -> None:
        text = self.HEADER + "ALİ ÖRNEK\tMüdür\tCoğrafya\nAYŞE ÖĞRETMEN\t\tMatematik\n"
        report = import_service.commit_personnel_text(text=text)
        assert report.created_personnel == 2
        p = Personnel.objects.get(last_name="ÖRNEK")
        assert p.title == "Müdür" and p.branch == "Coğrafya"

    def test_ada_gore_upsert(self) -> None:
        import_service.commit_personnel_text(text=self.HEADER + "AYŞE ÖĞRETMEN\t\tMatematik\n")
        report = import_service.commit_personnel_text(
            text=self.HEADER + "Ayşe ÖĞRETMEN\tMüdür Yardımcısı\tMatematik\n"
        )
        assert report.created_personnel == 0
        assert report.updated_personnel == 1
        assert Personnel.objects.count() == 1
        assert Personnel.objects.get().title == "Müdür Yardımcısı"

    def test_bos_ad_atlanir(self) -> None:
        report = import_service.commit_personnel_text(text=self.HEADER + "\tMüdür\tTarih\n")
        assert report.created_personnel == 0
        assert len(report.skipped) == 1

    def test_onizleme_yazmaz(self) -> None:
        report = import_service.preview_personnel_text(
            text=self.HEADER + "ALİ ÖRNEK\tMüdür\tCoğrafya\n"
        )
        assert report.dry_run is True
        assert report.created_personnel == 1
        assert Personnel.objects.count() == 0
        assert ImportRun.objects.get().status == ImportStatus.PREVIEWED

    def test_xlsx_dosya_yolu_calisiyor(self) -> None:
        """Personel importunun DOSYA yolu (pano değil) uçtan uca — inceleme bulgusu #12."""
        from apps.okul.tests.test_excel_personel_parser import make_xlsx as make_personel_xlsx

        data = make_personel_xlsx([["ALİ ÖRNEK", "Müdür", "Coğrafya"]])
        report = import_service.commit_personnel_file(file_bytes=data, file_name="personel.xlsx")
        assert report.created_personnel == 1
        assert Personnel.objects.count() == 1


# ---------------------------------------------------------------------------
# "İmport silmez" ilkesi — inceleme bulguları #1/#10 (kritik)
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestImportSilmezIlkesi:
    def _tam_import(self) -> Student:
        import_service.commit_students_file(file_bytes=make_xlsx([_yilmaz_row()]))
        student: Student = Student.objects.get()
        return student

    def test_kismi_kolonlu_yeniden_import_veli_verisini_silmez(self) -> None:
        """Yalnız kritik kolonlu (Sınıf/TCKN/Ad) pano yapıştırması veli/no alanlarını EZMEZ."""
        self._tam_import()
        text = (
            "Sınıf\tTCKN\tAdı Soyadı\n"
            f"11/B\t{TCKN_OGRENCI_1}\t{AILE_YILMAZ['ogrenci_ad_soyad']}\n"
        )
        import_service.commit_students_text(text=text)
        s = Student.objects.get()
        assert s.class_level == 11 and s.class_section == "B"  # sınıf güncellendi
        # Veli + okul no alanları KORUNDU (dosyada veri yoktu):
        assert s.guardian_name == AILE_YILMAZ["anne_ad_soyad"]
        assert s.guardian_kinship == "ANNE"
        assert s.guardian_phone == f"0{AILE_YILMAZ['anne_tel']}"
        assert s.guardian_phone2 == f"0{AILE_YILMAZ['baba_tel']}"
        assert s.student_number == "2612"

    def test_gecersiz_telefon_mevcut_telefonu_silmez(self) -> None:
        self._tam_import()
        row = _yilmaz_row()
        row[6] = "555123"  # çözülemeyen anne telefonu
        report = import_service.commit_students_file(file_bytes=make_xlsx([row]))
        s = Student.objects.get()
        assert s.guardian_phone == f"0{AILE_YILMAZ['anne_tel']}"  # eski değer korunur
        assert any(w.field == "phone" for w in report.warnings)

    def test_bos_okul_no_mevcut_numarayi_silmez(self) -> None:
        self._tam_import()
        row = _yilmaz_row()
        row[2] = ""  # okul no hücresi boş
        import_service.commit_students_file(file_bytes=make_xlsx([row]))
        assert Student.objects.get().student_number == "2612"


# ---------------------------------------------------------------------------
# Hata yolları — FAILED izi + bozuk dosya (inceleme bulguları #2/#4/#11)
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestImportHataYollari:
    def test_parser_hatasi_failed_izi_birakir(self) -> None:
        """Kritik sütun eksikliği ParserError + kalıcı FAILED ImportRun kaydı üretir."""
        from apps.okul.excel_veli import ParserError

        text = "Numa\tAdı Soyadı\n1\tALİ VELİ\n"
        with pytest.raises(ParserError):
            import_service.commit_students_text(text=text)
        run = ImportRun.objects.get()
        assert run.status == ImportStatus.FAILED
        assert "sütun" in str(run.report.get("error", "")).lower()

    def test_bozuk_dosya_parser_error_ve_failed_izi(self) -> None:
        """xlsx olmayan baytlar (eski .xls/CSV) 500 değil ParserError üretir."""
        from apps.okul.excel_veli import ParserError

        with pytest.raises(ParserError, match="xlsx"):
            import_service.commit_students_file(file_bytes=b"bu bir xlsx degil", file_name="a.xls")
        assert ImportRun.objects.get().status == ImportStatus.FAILED

    def test_onizleme_hatasi_da_failed_izi_birakir(self) -> None:
        from apps.okul.excel_veli import ParserError

        with pytest.raises(ParserError):
            import_service.preview_students_text(text="Numa\tAdı Soyadı\n1\tALİ VELİ\n")
        assert ImportRun.objects.get().status == ImportStatus.FAILED
