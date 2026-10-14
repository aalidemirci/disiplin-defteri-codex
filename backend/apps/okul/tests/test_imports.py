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

    def test_c_ve_c_cedilla_subeleri_ayri_kalir(self) -> None:
        """M6: "10/Ç" kayda "10/C" olarak geçmez; yeniden içe aktarma eski kaydı düzeltir."""
        Student.objects.create(
            tckn=str(TCKN_OGRENCI_1),
            first_name="A",
            last_name="B",
            class_level=10,
            class_section="C",
        )  # eski sürümün katladığı kayıt
        import_service.commit_students_file(file_bytes=make_xlsx([_yilmaz_row(sinif="10/Ç")]))
        assert Student.objects.get().class_section == "Ç"

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


# ---------------------------------------------------------------------------
# 14.10.2026 saha bildirimi (Gaziantep, MTAL) — şablonla öğrenci aktarımı
# ---------------------------------------------------------------------------
def _sablon_satiri(sinif: str, numara: object, ad: str, soyad: str, dogum: str) -> list[object]:
    return [sinif, numara, ad, soyad, dogum]


_SABLON_SATIRLARI: list[list[object]] = [
    _sablon_satiri("10/A", 220, "TUĞBANUR", "POLAT", "21.02.2012"),
    _sablon_satiri("10/A", 226, "ELİFNUR", "DEMİRPENÇE", "08.07.2011"),
    _sablon_satiri("10/A", 233, "FATMA GÜL", "ONAY", "21.02.2012"),
]


def _basliksiz_metin(rows: list[list[object]]) -> str:
    return "".join("\t".join(str(c) for c in r) + "\n" for r in rows)


@pytest.mark.django_db
class TestSablonSahaBildirimi:
    def test_veli_sutunsuz_sablonda_her_satira_veli_uyarisi_dusmez(self) -> None:
        """Şablonda veli sütunu yok; "Veli Kim boş" uyarısı her satıra düşüp
        578 satırlık başarılı önizlemeyi hata gibi gösteriyordu."""
        from apps.okul.services.templates import STUDENT_TEMPLATE_HEADERS

        report = import_service.preview_students_file(
            file_bytes=make_xlsx(_SABLON_SATIRLARI, header=list(STUDENT_TEMPLATE_HEADERS))
        )
        assert report.created_students == 3
        assert report.warnings == []
        assert report.skipped == []

    def test_veli_bilgisi_varken_veli_kim_bos_uyarisi_surer(self) -> None:
        row = _yilmaz_row()
        row[4] = ""
        report = import_service.preview_students_file(file_bytes=make_xlsx([row]))
        assert [w.field for w in report.warnings] == ["guardian"]

    def test_basliksiz_yapistirma_sablon_sirasiyla_okunur(self) -> None:
        """Kullanıcı yalnız veri satırlarını kopyalar (başlıksız) — sütunlar şablon
        sırasıyla okunur; satır numaraları yapıştırılan satırlarla aynı kalır."""
        report = import_service.commit_students_text(text=_basliksiz_metin(_SABLON_SATIRLARI))
        assert report.created_students == 3
        s = Student.objects.get(student_number="226")
        assert (s.first_name, s.last_name) == ("ELİFNUR", "DEMİRPENÇE")
        assert (s.class_level, s.class_section) == (10, "A")
        assert s.birth_date is not None and s.birth_date.isoformat() == "2011-07-08"
        assert Student.objects.get(student_number="233").first_name == "FATMA GÜL"
        assert [(w.row_number, w.field) for w in report.warnings] == [(1, "header")]
        assert "şablon sırasıyla" in report.warnings[0].issue

    def test_basliksiz_yapistirmada_satir_numarasi_kaymaz(self) -> None:
        rows = [*_SABLON_SATIRLARI, _sablon_satiri("8/A", 240, "AYŞENUR", "ERDOĞAN", "")]
        report = import_service.preview_students_text(text=_basliksiz_metin(rows))
        assert [(i.row_number, i.field) for i in report.skipped] == [(4, "class")]

    def test_basliksiz_dosya_da_sablon_sirasiyla_okunur(self) -> None:
        report = import_service.preview_students_file(
            file_bytes=make_xlsx(_SABLON_SATIRLARI[1:], header=_SABLON_SATIRLARI[0])
        )
        assert report.created_students == 3

    def test_veri_satirina_benzemeyen_basliksiz_metin_reddedilir(self) -> None:
        from apps.okul.excel_veli import ParserError

        with pytest.raises(ParserError, match="Sınıf"):
            import_service.preview_students_text(text="TUĞBANUR\tPOLAT\n")

    def test_eksik_sutun_iletisi_ic_alan_adi_degil_turkce(self) -> None:
        from apps.okul.excel_veli import ParserError

        with pytest.raises(ParserError) as exc:
            import_service.preview_students_text(text="Numa\tAdı Soyadı\n1\tALİ VELİ\n")
        message = str(exc.value)
        assert "Sınıf" in message and "başlık" in message
        assert "class" not in message and "student_" not in message

    def test_personel_eksik_sutun_iletisi_turkce(self) -> None:
        from apps.okul.excel_veli import ParserError

        with pytest.raises(ParserError) as exc:
            import_service.preview_personnel_text(text="Görevi\tBranşı\nÖğretmen\tFizik\n")
        assert "first_name" not in str(exc.value) and "Adı" in str(exc.value)

    def test_sablonun_ornek_satiri_aktarilmaz(self) -> None:
        from apps.okul.services.templates import student_template_xlsx

        report = import_service.commit_students_file(file_bytes=student_template_xlsx())
        assert Student.objects.count() == 0
        assert [(i.row_number, i.field) for i in report.skipped] == [(2, "row")]

    def test_personel_sablonunun_ornek_satiri_aktarilmaz(self) -> None:
        from apps.okul.services.templates import personnel_template_xlsx

        report = import_service.commit_personnel_file(file_bytes=personnel_template_xlsx())
        assert Personnel.objects.count() == 0
        assert [(i.row_number, i.field) for i in report.skipped] == [(2, "row")]


@pytest.mark.django_db
class TestBasliksizSekilDenetimi:
    """Başlıksız okuma yalnız şablon sırasındaki veriye uygulanır; başka düzen
    yanlış alanlara yazılacağına reddedilir (TCKN okul numarasına düşmesin)."""

    def _reddedilir(self, rows: list[list[object]]) -> None:
        from apps.okul.excel_veli import ParserError

        with pytest.raises(ParserError, match="şablon sırasında"):
            import_service.commit_students_text(text=_basliksiz_metin(rows))
        assert Student.objects.count() == 0

    def test_eokul_veli_iletisim_duzeni_reddedilir(self) -> None:
        self._reddedilir([_yilmaz_row()])

    def test_tckn_okul_numarasi_yerinde_reddedilir(self) -> None:
        self._reddedilir([["10/A", TCKN_OGRENCI_1, "TUĞBANUR", "POLAT", "21.02.2012"]])

    def test_ad_soyad_tek_sutunda_reddedilir(self) -> None:
        self._reddedilir([["10/A", 220, "TUĞBANUR POLAT", "21.02.2012", "K"]])

    def test_ad_yerinde_tckn_reddedilir(self) -> None:
        self._reddedilir([["10/A", 220, TCKN_OGRENCI_1, "TUĞBANUR", "POLAT"]])

    def test_soyad_yerinde_cinsiyet_reddedilir(self) -> None:
        self._reddedilir([["10/A", 220, "TUĞBANUR POLAT", "K"]])
        self._reddedilir([["10/A", 220, "TUĞBANUR POLAT", "Kız"]])

    def test_cok_sozcuklu_ad_soyad_kabul(self) -> None:
        rows = [["10/A", 220, "AYŞE NUR", "KAYA YILMAZ"], ["10/A", 221, "M. ALİ", "O'NEİL"]]
        report = import_service.preview_students_text(text=_basliksiz_metin(rows))
        assert report.created_students == 2

    def test_fazladan_sutun_reddedilir(self) -> None:
        self._reddedilir([[*_SABLON_SATIRLARI[0], "K"]])

    def test_ilk_on_satirda_baska_duzen_kaniti_satir_numarasiyla_reddedilir(self) -> None:
        from apps.okul.excel_veli import ParserError

        rows = [*_SABLON_SATIRLARI, ["10/A", TCKN_OGRENCI_2, "ALİ", "VELİ", ""]]
        with pytest.raises(ParserError, match="4. satır şablon sırasına uymuyor: Okul Numarası"):
            import_service.commit_students_text(text=_basliksiz_metin(rows))
        assert Student.objects.count() == 0

    def test_tek_bos_hucre_listeyi_reddettirmez_satir_atlanir(self) -> None:
        """İlk 10 satırdan birinde boş hücre başka düzenin kanıtı değildir."""
        rows: list[list[object]] = [
            *_SABLON_SATIRLARI,
            ["10/A", "", "ELİF", "DEMİR", ""],
            ["", 240, "AYŞE", "AK", ""],
        ]
        report = import_service.preview_students_text(text=_basliksiz_metin(rows))
        assert report.created_students == 3
        assert [(i.row_number, i.field) for i in report.skipped] == [(4, "number"), (5, "class")]

    def test_ad_sutununda_her_satir_ad_soyad_ise_reddedilir(self) -> None:
        """Birleşik "Ad Soyad | Baba Adı" düzeni: baba adı soyad olarak yazılmasın.

        Boş ad hücreli dipnot/toplam satırı kuralı boşa çıkarmaz."""
        self._reddedilir(
            [
                ["10/A", 220 + i, f"{ad} {soyad}", baba]
                for i, (ad, soyad, baba) in enumerate(
                    [
                        ("TUĞBANUR", "POLAT", "HASAN"),
                        ("ELİF", "KAYA", "MEHMET"),
                        ("ZEYNEP", "AK", "ALİ"),
                        ("ESMA", "TOK", "AHMET"),
                        ("SEDA", "UZ", "MUSTAFA"),
                        ("NUR", "SU", "OSMAN"),
                    ]
                )
            ]
            + [["Toplam: 6 öğrenci", "", "", ""]]
        )

    def test_dort_iki_isimli_ogrenci_reddedilmez(self) -> None:
        rows: list[list[object]] = [
            ["10/A", 220 + i, ad, soyad]
            for i, (ad, soyad) in enumerate(
                [
                    ("AYŞE NUR", "YILMAZ"),
                    ("ELİF NAZ", "KAYA"),
                    ("ZEYNEP SU", "AK"),
                    ("FATMA NUR", "TOK"),
                ]
            )
        ]
        report = import_service.preview_students_text(text=_basliksiz_metin(rows))
        assert report.created_students == 4

    def test_baslik_ilk_satirda_degilse_de_tanimadigi_soylenir(self) -> None:
        from apps.okul.excel_veli import ParserError

        rows: list[list[object]] = [
            ["2026-2027 10/A SINIF LİSTESİ"],
            ["Sınıf", "No", "Adı", "Soyadı", "D.Tarihi"],
            *_SABLON_SATIRLARI,
        ]
        with pytest.raises(ParserError, match="2. satır başlık satırı gibi görünüyor"):
            import_service.preview_students_text(text=_basliksiz_metin(rows))

    def test_uc_iki_isimli_ogrenci_kabul_ve_okunus_gosterilir(self) -> None:
        """Kısa yapıştırmada şekil yetmez: yanlış ret yerine önizlemede okunuş gösterilir."""
        rows: list[list[object]] = [
            ["10/A", 220, "AYŞE NUR", "YILMAZ"],
            ["10/A", 221, "ELİF NAZ", "KAYA"],
            ["10/A", 222, "ZEYNEP SU", "AK"],
        ]
        report = import_service.preview_students_text(text=_basliksiz_metin(rows))
        assert report.created_students == 3
        okunus = "1. satır şöyle okundu: Sınıf 10/A · Okul No 220 · Ad AYŞE NUR · Soyad YILMAZ"
        assert okunus in report.warnings[0].issue

    def test_ad_ve_soyad_her_satirda_cok_sozcuklu_ise_reddedilir(self) -> None:
        """ "Ad Soyad | Alan adı" düzeni: alan adı soyad olarak yazılmasın (2 satır yeter)."""
        self._reddedilir(
            [
                ["10/A", 220, "TUĞBANUR POLAT", "Çocuk Gelişimi ve Eğitimi"],
                ["10/A", 221, "ELİF KAYA", "Çocuk Gelişimi ve Eğitimi"],
            ]
        )

    def test_dogum_tarihi_yerinde_metin_reddedilir(self) -> None:
        """ "Ad Soyad | Baba | Anne" düzeni: anne adı doğum tarihi sütununa düşer."""
        self._reddedilir([["10/A", 220, "TUĞBANUR POLAT", "MEHMET", "AYŞE"]])

    def test_veli_adi_ogrencinin_soyadini_tasiyorsa_tek_satirda_reddedilir(self) -> None:
        self._reddedilir([["10/A", 220, "TUĞBANUR POLAT", "AYŞE POLAT"]])

    def test_ad_soyad_yaninda_baba_tek_satirda_reddedilir(self) -> None:
        self._reddedilir([["10/A", 220, "TUĞBANUR POLAT", "BABA", "21.02.2012"]])

    def test_soyad_yerinde_anne_reddedilir(self) -> None:
        self._reddedilir([["10/A", 220, "TUĞBANUR POLAT", "ANNE", "21.02.2012"]])

    def test_tek_veli_adli_ogrenci_kabul_coklu_baba_reddedilir(self) -> None:
        rows: list[list[object]] = [[*_SABLON_SATIRLARI[0]], ["10/B", 301, "VELİ", "KARA", ""]]
        report = import_service.preview_students_text(text=_basliksiz_metin(rows))
        assert report.created_students == 2
        self._reddedilir(
            [["10/A", 220, "TUĞBANUR POLAT", "BABA"], ["10/A", 221, "ELİF KAYA", "BABA"]]
        )

    def test_ilk_satirda_bos_hucre_satir_atlanir(self) -> None:
        rows = [_sablon_satiri("10/A", "", "ELİF", "DEMİR", ""), *_SABLON_SATIRLARI]
        report = import_service.preview_students_text(text=_basliksiz_metin(rows))
        assert report.created_students == 3
        assert [(i.row_number, i.field) for i in report.skipped] == [(1, "number")]

    def test_ilk_satirda_hatali_sinif_satir_numarasiyla_reddedilir(self) -> None:
        from apps.okul.excel_veli import ParserError

        rows = [_sablon_satiri("10", 219, "ELİF", "DEMİR", ""), *_SABLON_SATIRLARI]
        with pytest.raises(ParserError, match="1. satır şablon sırasına uymuyor: Sınıf"):
            import_service.preview_students_text(text=_basliksiz_metin(rows))

    def test_taninmayan_baslik_satiri_soylenir(self) -> None:
        from apps.okul.excel_veli import ParserError

        rows: list[list[object]] = [["Sınıf", "No", "Adı", "Soyadı"], *_SABLON_SATIRLARI]
        with pytest.raises(ParserError, match="1. satır başlık satırı gibi görünüyor"):
            import_service.preview_students_text(text=_basliksiz_metin(rows))

    def test_ad_ya_da_soyad_bos_satir_atlanir(self) -> None:
        rows = [*_SABLON_SATIRLARI, _sablon_satiri("10/A", 240, "AYŞE", "", "")]
        report = import_service.commit_students_text(text=_basliksiz_metin(rows))
        assert report.created_students == 3
        assert [(i.row_number, i.field) for i in report.skipped] == [(4, "full_name")]

    def test_kaymis_satir_baslikli_dosyada_da_atlanir(self) -> None:
        """Başlıklı dosyada kaymış satır: harfli okul no ya da rakamlı soyad yazılmaz."""
        from apps.okul.services.templates import STUDENT_TEMPLATE_HEADERS

        rows: list[list[object]] = [
            ["10/A", "AYŞE", "KAYA", "201", ""],
            ["10/A", 202, "ELİF", "01.01.2010", ""],
            *_SABLON_SATIRLARI,
        ]
        report = import_service.commit_students_file(
            file_bytes=make_xlsx(rows, header=list(STUDENT_TEMPLATE_HEADERS))
        )
        assert report.created_students == 3
        assert [(i.row_number, i.field) for i in report.skipped] == [
            (2, "number"),
            (3, "full_name"),
        ]

    def test_okul_numarasi_yerine_tckn_kaydedilmez(self) -> None:
        """Örneklem sonrası (11. satırdan sonra) okul no yerine TCKN: satır atlanır, maskeli."""
        rows = [_sablon_satiri("10/A", 300 + i, "AYŞE", "KAYA", "") for i in range(11)]
        rows.append(["10/A", TCKN_OGRENCI_1, "ELİF", "DEMİR", ""])
        report = import_service.commit_students_text(text=_basliksiz_metin(rows))
        assert report.created_students == 11
        [skip] = report.skipped
        assert (skip.row_number, skip.field) == (12, "number")
        assert skip.raw_value != str(TCKN_OGRENCI_1)
        assert not Student.objects.filter(student_number=str(TCKN_OGRENCI_1)).exists()

    def test_dogum_tarihsiz_dort_sutun_kabul(self) -> None:
        rows = [r[:4] for r in _SABLON_SATIRLARI]
        report = import_service.preview_students_text(text=_basliksiz_metin(rows))
        assert report.created_students == 3


@pytest.mark.django_db
class TestDosyaIciYinelenenOgrenci:
    def test_yinelenen_okul_numarasi_ilk_kaydi_ezmez(self) -> None:
        rows = [*_SABLON_SATIRLARI, _sablon_satiri("11/B", 220, "ZEYNEP", "KAYA", "")]
        report = import_service.commit_students_text(text=_basliksiz_metin(rows))
        assert report.created_students == 3 and report.updated_students == 0
        assert Student.objects.get(student_number="220").first_name == "TUĞBANUR"
        [skip] = report.skipped
        assert (skip.row_number, skip.field, skip.raw_value) == (4, "number", "220")
        assert "1. satırda" in skip.issue

    def test_ayni_numarali_farkli_tcknli_ogrenciler_birbirini_ezmez(self) -> None:
        first = _yilmaz_row(numara=500)
        second = [*_yilmaz_row(sinif="11/B", numara=500)]
        second[1] = TCKN_OGRENCI_2
        second[3] = AILE_KAYA["ogrenci_ad_soyad"]
        report = import_service.commit_students_file(file_bytes=make_xlsx([first, second]))
        assert report.created_students == 2 and report.skipped == []
        assert {s.tckn for s in Student.objects.all()} == {
            str(TCKN_OGRENCI_1),
            str(TCKN_OGRENCI_2),
        }

    def test_tcknli_ve_tckn_siz_ayni_numara_ikinci_satir_atlanir(self) -> None:
        """Satırlardan biri TCKN'sizse aynı numara aynı öğrencidir: kopya açılmaz."""
        with_tckn = _yilmaz_row(numara=500)
        without = [*_yilmaz_row(numara=500)]
        without[1] = ""
        report = import_service.commit_students_file(file_bytes=make_xlsx([with_tckn, without]))
        assert Student.objects.count() == 1
        assert [(i.row_number, i.field) for i in report.skipped] == [(3, "number")]
        again = import_service.commit_students_file(file_bytes=make_xlsx([without, with_tckn]))
        assert Student.objects.count() == 1 and again.created_students == 0

    def test_ayni_numarali_baska_ogrenci_ezilmez(self) -> None:
        """DB'de aynı numaralı iki öğrenci (farklı TCKN) varken TCKN'li + TCKN'siz satır:
        TCKN'siz satır diğer öğrenciyi EZMEZ, atlanır."""
        first = _yilmaz_row(numara=500)
        other = [*_yilmaz_row(sinif="11/B", numara=500)]
        other[1] = TCKN_OGRENCI_2
        other[3] = AILE_KAYA["ogrenci_ad_soyad"]
        import_service.commit_students_file(file_bytes=make_xlsx([first, other]))
        assert Student.objects.count() == 2
        without = [*_yilmaz_row(numara=500)]
        without[1] = ""
        import_service.commit_students_file(file_bytes=make_xlsx([first, without]))
        kaya = next(s for s in Student.objects.all() if s.tckn == str(TCKN_OGRENCI_2))
        assert (kaya.class_level, kaya.class_section) == (11, "B")

    def test_bir_ogrenci_bir_kosuda_iki_kez_yazilmaz(self) -> None:
        import_service.commit_students_file(file_bytes=make_xlsx([_yilmaz_row(numara=500)]))
        by_number = [*_yilmaz_row(sinif="10/B", numara=500)]
        by_number[1] = ""
        by_tckn = _yilmaz_row(sinif="10/C", numara=501)
        report = import_service.commit_students_file(file_bytes=make_xlsx([by_number, by_tckn]))
        assert [(i.row_number, i.field) for i in report.skipped] == [(3, "row")]
        assert Student.objects.get().class_section == "B"

    def test_numarayla_eslesen_tckn_siz_kayda_tckn_eklenir(self) -> None:
        sablon = _sablon_satiri("10/A", 2612, "EMRE CAN", "YILMAZ", "")
        import_service.commit_students_text(text=_basliksiz_metin([sablon]))
        report = import_service.commit_students_file(file_bytes=make_xlsx([_yilmaz_row()]))
        assert report.updated_students == 1 and report.created_students == 0
        assert Student.objects.get().tckn == str(TCKN_OGRENCI_1)

    def test_yalniz_numarayla_eslesen_farkli_adli_kayit_ezilmez(self) -> None:
        """Numara başka öğrenciye verilmişse (ör. nakil sonrası) ad/TCKN üzerine yazılmaz."""
        import_service.commit_students_text(text=_basliksiz_metin([_SABLON_SATIRLARI[0]]))
        row = _yilmaz_row(numara=220)  # 220 = TUĞBANUR POLAT; satır EMRE CAN YILMAZ
        report = import_service.commit_students_file(file_bytes=make_xlsx([row]))
        assert [(i.row_number, i.field) for i in report.skipped] == [(2, "number")]
        s = Student.objects.get()
        assert (s.first_name, s.last_name, s.tckn) == ("TUĞBANUR", "POLAT", "")

    def test_ayni_adli_tckn_siz_kayit_varken_yeni_tcknli_kayit_uyarilir(self) -> None:
        """Şablonda numarası yanlış girilmiş öğrenci e-Okul listesiyle ikinci kez açılırsa
        önizleme uyarır (veriye dokunulmaz)."""
        sablon = _sablon_satiri("10/A", 220, "EMRE CAN", "YILMAZ", "")
        import_service.commit_students_text(text=_basliksiz_metin([sablon]))
        report = import_service.preview_students_file(
            file_bytes=make_xlsx([_yilmaz_row(numara=202)])
        )
        assert report.created_students == 1
        assert [(w.field, w.raw_value) for w in report.warnings if w.field == "full_name"] == [
            ("full_name", "202")
        ]
        assert "okul no 220" in report.warnings[-1].issue

    def test_numarasi_degisen_ogrenci_ikinci_kez_acilmaz(self) -> None:
        import_service.commit_students_file(file_bytes=make_xlsx([_yilmaz_row(numara=220)]))
        new_number = _yilmaz_row(sinif="10/B", numara=305)
        old_number = [*_yilmaz_row(numara=220)]
        old_number[1] = ""
        report = import_service.commit_students_file(file_bytes=make_xlsx([new_number, old_number]))
        assert Student.objects.count() == 1
        assert [(i.row_number, i.field) for i in report.skipped] == [(3, "number")]

    def test_yinelenen_tckn_maskeli_raporlanir(self) -> None:
        first = _yilmaz_row(numara=2612)
        second = _yilmaz_row(sinif="11/B", numara=2613)
        report = import_service.commit_students_file(file_bytes=make_xlsx([first, second]))
        assert Student.objects.count() == 1
        [skip] = report.skipped
        assert skip.field == "tckn" and skip.raw_value != str(TCKN_OGRENCI_1)
        assert Student.objects.get().student_number == "2612"


@pytest.mark.django_db
class TestVeliUyarisiSutunDuzeyinde:
    def test_veli_sutunlu_dosyada_velisiz_satir_uyarilir(self) -> None:
        row = _yilmaz_row()
        row[4:9] = ["", "", "", "", ""]
        report = import_service.preview_students_file(file_bytes=make_xlsx([row]))
        assert [(w.field, w.issue) for w in report.warnings] == [
            ("guardian", "Anne/baba bilgisi okunamadı; veli alanları güncellenmedi.")
        ]

    def test_yalniz_anne_bilgisi_varsa_uyari_anne_der(self) -> None:
        row = _yilmaz_row()
        row[4] = ""
        row[7:9] = ["", ""]
        report = import_service.commit_students_file(file_bytes=make_xlsx([row]))
        assert Student.objects.get().guardian_kinship == "ANNE"
        assert [w.issue for w in report.warnings] == ["Veli Kim 'boş' belirsiz; ANNE varsayıldı."]
