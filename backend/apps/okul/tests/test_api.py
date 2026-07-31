"""`apps.okul` API uçları (F1-T6) — sihirbaz + listeler + import + şablonlar.

Authsuz tek kullanıcılı program: izin katmanı yok (AllowAny), yine de View →
Service → Model disiplini korunur. Hata gövdesi `{code, message, fields}`
sözleşmesindedir (FE `lib/api.ts` bunu bekler — tasarım §4.3).
"""

from __future__ import annotations

from datetime import date
from io import BytesIO
from typing import Any, cast

import pytest
from rest_framework.test import APIClient

from apps.okul.models import ClassResponsibility, Holiday, Personnel, SchoolYear, Student
from apps.okul.tests._fixtures import AILE_YILMAZ, TCKN_OGRENCI_1
from apps.okul.tests.test_excel_veli_parser import make_xlsx


@pytest.fixture
def client() -> APIClient:
    return APIClient()


# ---------------------------------------------------------------------------
# Kurulum sihirbazı
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestSetupApi:
    def test_durum_baslangicta_kurulmamis(self, client: APIClient) -> None:
        resp = client.get("/api/v1/setup/status/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["setup_completed"] is False
        assert data["has_active_school_year"] is False
        assert data["student_count"] == 0
        assert data["personnel_count"] == 0

    def test_okul_bilgileri_guncelle_ve_tamamla(self, client: APIClient) -> None:
        resp = client.put(
            "/api/v1/setup/school-config/",
            {
                "school_name": "Deneme Anadolu Lisesi",
                "province": "Muğla",
                "district": "Menteşe",
                "principal_name": "ALİ ÖRNEK",
            },
            format="json",
        )
        assert resp.status_code == 200
        assert resp.json()["school_name"] == "Deneme Anadolu Lisesi"

        resp = client.post("/api/v1/setup/complete/")
        assert resp.status_code == 200
        assert client.get("/api/v1/setup/status/").json()["setup_completed"] is True

    def test_kismi_govde_merge_semantigi(self, client: APIClient) -> None:
        """PUT kısmi gövde: verilmeyen alanlar SİLİNMEZ, korunur (bulgu #16)."""
        client.put(
            "/api/v1/setup/school-config/",
            {"school_name": "Deneme Anadolu Lisesi", "district": "Menteşe"},
            format="json",
        )
        resp = client.put(
            "/api/v1/setup/school-config/", {"principal_name": "YENİ MÜDÜR"}, format="json"
        )
        assert resp.status_code == 200
        body = client.get("/api/v1/setup/school-config/").json()
        assert body["principal_name"] == "YENİ MÜDÜR"
        assert body["school_name"] == "Deneme Anadolu Lisesi"  # korunur
        assert body["district"] == "Menteşe"

    def test_hata_sozlesmesi_alan_hatalari(self, client: APIClient) -> None:
        """Doğrulama hatası `{code, message, fields}` biçiminde döner."""
        resp = client.post(
            "/api/v1/school-years/",
            {"name": "", "start_date": "boş", "end_date": "2027-06-19"},
            format="json",
        )
        assert resp.status_code == 400
        data = resp.json()
        assert data["code"] == "validation_error"
        assert "message" in data
        assert "start_date" in data["fields"]


# ---------------------------------------------------------------------------
# Ders yılları
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestSchoolYearApi:
    def test_olustur_ve_listele(self, client: APIClient) -> None:
        resp = client.post(
            "/api/v1/school-years/",
            {"name": "2026-2027", "start_date": "2026-09-01", "end_date": "2027-06-19"},
            format="json",
        )
        assert resp.status_code == 201
        data = client.get("/api/v1/school-years/").json()
        assert data["count"] == 1
        assert data["results"][0]["name"] == "2026-2027"

    def test_bitis_baslangictan_once_reddedilir(self, client: APIClient) -> None:
        resp = client.post(
            "/api/v1/school-years/",
            {"name": "2026-2027", "start_date": "2027-06-19", "end_date": "2026-09-01"},
            format="json",
        )
        assert resp.status_code == 400

    def test_iki_donem_birlikte_yapilandirilir(self, client: APIClient) -> None:
        year = SchoolYear.objects.create(
            name="2026-2027",
            start_date=date(2026, 9, 1),
            end_date=date(2027, 6, 30),
        )
        response = client.put(
            f"/api/v1/school-years/{year.pk}/terms/",
            {
                "first_term_end": "2027-01-16",
                "second_term_start": "2027-02-02",
            },
            format="json",
        )
        assert response.status_code == 200
        assert [row["sequence"] for row in response.json()] == [1, 2]
        assert response.json()[0]["start_date"] == "2026-09-01"
        assert response.json()[1]["end_date"] == "2027-06-30"

    def test_aktiflestir_tek_aktif_kurali(self, client: APIClient) -> None:
        y1 = SchoolYear.objects.create(
            name="2025-2026",
            start_date=date(2025, 9, 8),
            end_date=date(2026, 6, 26),
            is_active=True,
        )
        y2 = SchoolYear.objects.create(
            name="2026-2027", start_date=date(2026, 9, 1), end_date=date(2027, 6, 19)
        )
        resp = client.post(f"/api/v1/school-years/{y2.pk}/activate/")
        assert resp.status_code == 200
        y1.refresh_from_db()
        y2.refresh_from_db()
        assert y1.is_active is False
        assert y2.is_active is True


# ---------------------------------------------------------------------------
# Sınıf sorumlulukları
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestClassResponsibilityApi:
    def test_aktif_yilin_eslestirmesini_olusturur_ve_listeler(self, client: APIClient) -> None:
        year = SchoolYear.objects.create(
            name="2026-2027",
            start_date=date(2026, 9, 1),
            end_date=date(2027, 6, 19),
            is_active=True,
        )
        rehber = Personnel.objects.create(
            first_name="Örnek", last_name="Rehber", title="Rehber Öğretmen"
        )

        created = client.post(
            "/api/v1/class-responsibilities/",
            {
                "school_year": year.pk,
                "class_level": 10,
                "class_section": "ş",
                "guidance_teacher": rehber.pk,
            },
            format="json",
        )

        assert created.status_code == 201
        assert created.json()["class_label"] == "10/S"
        assert created.json()["guidance_teacher_detail"]["full_name"] == "Örnek Rehber"
        listed = client.get("/api/v1/class-responsibilities/").json()
        assert listed["count"] == 1
        assert listed["results"][0]["id"] == created.json()["id"]

    def test_ayni_yil_ve_sube_ikinci_kez_reddedilir(self, client: APIClient) -> None:
        year = SchoolYear.objects.create(
            name="2026-2027",
            start_date=date(2026, 9, 1),
            end_date=date(2027, 6, 19),
            is_active=True,
        )
        body = {"school_year": year.pk, "class_level": 10, "class_section": "A"}
        assert (
            client.post("/api/v1/class-responsibilities/", body, format="json").status_code == 201
        )
        duplicate = client.post("/api/v1/class-responsibilities/", body, format="json")
        assert duplicate.status_code == 400
        assert "class_section" in duplicate.json()["fields"]

    def test_personel_unvanina_gore_aranabilir(self, client: APIClient) -> None:
        Personnel.objects.create(first_name="Örnek", last_name="Kişi", title="Rehber Öğretmen")
        response = client.get("/api/v1/personnel/?search=rehber")
        assert response.status_code == 200
        assert response.json()["count"] == 1

    def test_eslestirme_guncellenir_ve_silinir(self, client: APIClient) -> None:
        year = SchoolYear.objects.create(
            name="2026-2027",
            start_date=date(2026, 9, 1),
            end_date=date(2027, 6, 19),
            is_active=True,
        )
        row = ClassResponsibility.objects.create(
            school_year=year, class_level=11, class_section="B"
        )
        rehber = Personnel.objects.create(first_name="Yeni", last_name="Rehber")

        updated = client.patch(
            f"/api/v1/class-responsibilities/{row.pk}/",
            {"guidance_teacher": rehber.pk},
            format="json",
        )
        assert updated.status_code == 200
        assert updated.json()["guidance_teacher"] == rehber.pk
        assert client.delete(f"/api/v1/class-responsibilities/{row.pk}/").status_code == 204
        assert ClassResponsibility.objects.count() == 0


# ---------------------------------------------------------------------------
# Tatiller
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestHolidayApi:
    def test_seed_aktif_yila(self, client: APIClient) -> None:
        SchoolYear.objects.create(
            name="2026-2027",
            start_date=date(2026, 9, 1),
            end_date=date(2027, 6, 19),
            is_active=True,
        )
        resp = client.post("/api/v1/holidays/seed/", {}, format="json")
        assert resp.status_code == 200
        body = resp.json()
        assert body["created"] > 0
        # Sabit resmî (5) + dini bayramlar (Ramazan/Kurban 2027) eklendi.
        assert Holiday.objects.count() == body["created"]

    def test_seed_aktif_yil_yoksa_400(self, client: APIClient) -> None:
        resp = client.post("/api/v1/holidays/seed/", {}, format="json")
        assert resp.status_code == 400
        assert resp.json()["code"] == "validation_error"

    def test_seed_belirli_yil_idsiyle(self, client: APIClient) -> None:
        """Aktif olmayan yıla açık id ile seed — yanlış-yıla-seed hatasına pin (bulgu #15)."""
        SchoolYear.objects.create(
            name="2025-2026",
            start_date=date(2025, 9, 8),
            end_date=date(2026, 6, 26),
            is_active=True,
        )
        hedef = SchoolYear.objects.create(
            name="2026-2027", start_date=date(2026, 9, 1), end_date=date(2027, 6, 19)
        )
        resp = client.post("/api/v1/holidays/seed/", {"school_year": hedef.pk}, format="json")
        assert resp.status_code == 200
        # Hedef yılın Cumhuriyet Bayramı (2026) eklendi; aktif yılınki (2025) EKLENMEDİ.
        starts = set(Holiday.objects.values_list("start_date", flat=True))
        assert date(2026, 10, 29) in starts
        assert date(2025, 10, 29) not in starts

    def test_elle_ekle_ve_sil(self, client: APIClient) -> None:
        resp = client.post(
            "/api/v1/holidays/",
            {"name": "İdari İzin", "start_date": "2026-11-02", "end_date": "2026-11-02"},
            format="json",
        )
        assert resp.status_code == 201
        holiday_id = resp.json()["id"]
        assert client.delete(f"/api/v1/holidays/{holiday_id}/").status_code == 204
        # Soft delete: canlı listede yok, tabloda duruyor.
        assert Holiday.objects.count() == 0
        assert Holiday.all_objects.count() == 1


# ---------------------------------------------------------------------------
# Öğrenci / Personel listeleri + elle ekleme
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestStudentApi:
    def test_bos_liste_sayfalama_zarfi(self, client: APIClient) -> None:
        data = client.get("/api/v1/students/").json()
        assert data == {"count": 0, "next": None, "previous": None, "results": []}

    def test_elle_ekle_tckn_normalize(self, client: APIClient) -> None:
        resp = client.post(
            "/api/v1/students/",
            {
                "first_name": "EMRE CAN",
                "last_name": "YILMAZ",
                "tckn": f" {TCKN_OGRENCI_1} ",
                "class_level": 10,
                "class_section": "a",
                "guardian_phone": "5550000101",
            },
            format="json",
        )
        assert resp.status_code == 201
        s = Student.objects.get()
        assert s.tckn == str(TCKN_OGRENCI_1)
        assert s.class_section == "A"
        assert s.guardian_phone == "05550000101"

    def test_gecersiz_tckn_reddedilir(self, client: APIClient) -> None:
        resp = client.post(
            "/api/v1/students/",
            {"first_name": "A", "last_name": "B", "tckn": "12345678901"},
            format="json",
        )
        assert resp.status_code == 400
        assert "tckn" in resp.json()["fields"]

    def test_sinif_filtresi(self, client: APIClient) -> None:
        Student.objects.create(first_name="A", last_name="B", class_level=10, class_section="A")
        Student.objects.create(first_name="C", last_name="D", class_level=11, class_section="B")
        data = client.get("/api/v1/students/", {"class_level": 10}).json()
        assert data["count"] == 1
        assert data["results"][0]["class_label"] == "10/A"

    def test_arama_ad_soyad(self, client: APIClient) -> None:
        Student.objects.create(first_name="EMRE CAN", last_name="YILMAZ")
        Student.objects.create(first_name="ZEYNEP", last_name="KAYA")
        data = client.get("/api/v1/students/", {"search": "yılmaz"}).json()
        assert data["count"] == 1

    def test_detay_guncelle(self, client: APIClient) -> None:
        s = Student.objects.create(first_name="EMRE", last_name="YILMAZ")
        resp = client.patch(
            f"/api/v1/students/{s.pk}/", {"guardian_address": "Menteşe/Muğla"}, format="json"
        )
        assert resp.status_code == 200
        s.refresh_from_db()
        assert s.guardian_address == "Menteşe/Muğla"

    def test_sinif_filtresi_gecersiz_deger_400(self, client: APIClient) -> None:
        """'abc' sessizce yutulmaz, '²' 500 vermez — ikisi de sözleşmeli 400 (bulgu #3)."""
        Student.objects.create(first_name="A", last_name="B", class_level=10, class_section="A")
        for bozuk in ("abc", "²"):
            resp = client.get("/api/v1/students/", {"class_level": bozuk})
            assert resp.status_code == 400, bozuk
            assert resp.json()["code"] == "validation_error"

    def test_class_level_13_reddedilir(self, client: APIClient) -> None:
        resp = client.post(
            "/api/v1/students/",
            {"first_name": "A", "last_name": "B", "class_level": 13},
            format="json",
        )
        assert resp.status_code == 400
        assert "class_level" in resp.json()["fields"]

    def test_sayfalama_gercek_dilimleme(self, client: APIClient) -> None:
        """limit/offset gerçekten dilimler; varsayılan sayfa 25 kayıt (bulgu #13)."""
        for i in range(30):
            Student.objects.create(
                first_name=f"AD{i:02d}",
                last_name="SOYAD",
                class_level=9,
                class_section="A",
                student_number=str(1000 + i),
            )
        default_page = client.get("/api/v1/students/").json()
        assert default_page["count"] == 30
        assert len(default_page["results"]) == 25
        son_dilim = client.get("/api/v1/students/", {"limit": 5, "offset": 25}).json()
        assert son_dilim["count"] == 30
        assert len(son_dilim["results"]) == 5
        assert son_dilim["next"] is None

    def test_turkce_sube_filtresi(self, client: APIClient) -> None:
        """Şube 'Ş' ASCII'ye katlanarak saklanır; filtre de aynı katlamadan geçer (bulgu #5)."""
        resp = client.post(
            "/api/v1/students/",
            {"first_name": "A", "last_name": "B", "class_level": 12, "class_section": "ş"},
            format="json",
        )
        assert resp.status_code == 201
        assert Student.objects.get().class_section == "S"
        data = client.get("/api/v1/students/", {"class_section": "ş"}).json()
        assert data["count"] == 1

    def test_only_active_suzgeci_ayrilan_ogrenciyi_eler(self, client: APIClient) -> None:
        """`only_active=true` yalnız aktif öğrenciyi döner; parametresiz liste HEPSİNİ (bulgu #10).

        Seçici (autocomplete) çağrıları süzgeci açar — ayrılmış öğrenciye yeni
        dosya açılamasın; Kişiler sayfası süzgeçsiz çağırır — sicil tam görünür.
        """
        Student.objects.create(first_name="AKTIF", last_name="YILMAZ", status="ACTIVE")
        Student.objects.create(first_name="AYRILAN", last_name="YILMAZ", status="LEFT")

        hepsi = client.get("/api/v1/students/").json()
        assert hepsi["count"] == 2

        aktif = client.get("/api/v1/students/", {"only_active": "true"}).json()
        assert aktif["count"] == 1
        assert aktif["results"][0]["first_name"] == "AKTIF"

    def test_only_active_arama_ile_birlikte(self, client: APIClient) -> None:
        """Süzgeç aramayla birleşir (arama Python tarafında katlanır — bulgu #10)."""
        Student.objects.create(first_name="EMRE CAN", last_name="YILMAZ", status="ACTIVE")
        Student.objects.create(first_name="ZEYNEP", last_name="YILMAZ", status="LEFT")
        data = client.get("/api/v1/students/", {"search": "yılmaz", "only_active": "true"}).json()
        assert data["count"] == 1
        assert data["results"][0]["first_name"] == "EMRE CAN"

    def test_only_active_kapali_degerler_suzmez(self, client: APIClient) -> None:
        """Yalnız 'true'/'1' süzgeci açar; diğer değerler varsayılan davranışı bozmaz."""
        Student.objects.create(first_name="AKTIF", last_name="A", status="ACTIVE")
        Student.objects.create(first_name="AYRILAN", last_name="B", status="LEFT")
        for kapali in ("", "false", "0", "hayir"):
            data = client.get("/api/v1/students/", {"only_active": kapali}).json()
            assert data["count"] == 2, kapali
        assert client.get("/api/v1/students/", {"only_active": "1"}).json()["count"] == 1


@pytest.mark.django_db
class TestPersonnelApi:
    def test_ekle_ve_listele(self, client: APIClient) -> None:
        resp = client.post(
            "/api/v1/personnel/",
            {"first_name": "ALİ", "last_name": "ÖRNEK", "title": "Müdür"},
            format="json",
        )
        assert resp.status_code == 201
        data = client.get("/api/v1/personnel/").json()
        assert data["count"] == 1
        assert data["results"][0]["full_name"] == "ALİ ÖRNEK"

    def test_sil_soft_delete(self, client: APIClient) -> None:
        p = Personnel.objects.create(first_name="A", last_name="B")
        assert client.delete(f"/api/v1/personnel/{p.pk}/").status_code == 204
        assert Personnel.objects.count() == 0
        assert Personnel.all_objects.count() == 1


# ---------------------------------------------------------------------------
# İçe aktarma uçları
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestImportApi:
    def _xlsx_upload(self) -> BytesIO:
        data = BytesIO(
            make_xlsx(
                [
                    [
                        "10/A",
                        TCKN_OGRENCI_1,
                        2612,
                        AILE_YILMAZ["ogrenci_ad_soyad"],
                        "ANNE",
                        AILE_YILMAZ["anne_ad_soyad"],
                        AILE_YILMAZ["anne_tel"],
                        AILE_YILMAZ["baba_ad_soyad"],
                        AILE_YILMAZ["baba_tel"],
                    ]
                ]
            )
        )
        data.name = "veli.xlsx"
        return data

    def test_dosya_onizleme_yazmaz(self, client: APIClient) -> None:
        resp = client.post(
            "/api/v1/imports/students/preview/",
            {"file": self._xlsx_upload()},
            format="multipart",
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["dry_run"] is True
        assert body["created_students"] == 1
        assert Student.objects.count() == 0

    def test_dosya_commit_yazar(self, client: APIClient) -> None:
        resp = client.post(
            "/api/v1/imports/students/commit/",
            {"file": self._xlsx_upload()},
            format="multipart",
        )
        assert resp.status_code == 200
        assert Student.objects.count() == 1

    def test_metin_yapistirma_commit(self, client: APIClient) -> None:
        text = "Ad Soyad\tUnvan\tBranş\n" "ALİ ÖRNEK\tMüdür\tCoğrafya\n"
        resp = client.post("/api/v1/imports/personnel/commit/", {"text": text}, format="json")
        assert resp.status_code == 200
        assert Personnel.objects.count() == 1

    def test_dosya_veya_metin_zorunlu(self, client: APIClient) -> None:
        resp = client.post("/api/v1/imports/students/preview/", {}, format="json")
        assert resp.status_code == 400
        assert resp.json()["code"] == "validation_error"

    def test_kritik_sutun_eksik_400(self, client: APIClient) -> None:
        resp = client.post(
            "/api/v1/imports/students/preview/",
            {"text": "Numa\tAdı Soyadı\n1\tALİ VELİ\n"},
            format="json",
        )
        assert resp.status_code == 400
        assert "sütun" in resp.json()["message"].lower()

    def test_bozuk_dosya_400_sozlesmeli(self, client: APIClient) -> None:
        """xlsx olmayan yükleme 500 değil `{code,message,fields}` 400 döner (bulgu #2)."""
        sahte = BytesIO(b"bu bir xlsx dosyasi degil")
        sahte.name = "liste.xls"
        resp = client.post("/api/v1/imports/students/commit/", {"file": sahte}, format="multipart")
        assert resp.status_code == 400
        body = resp.json()
        assert body["code"] == "validation_error"
        assert "xlsx" in body["message"]

    def test_personel_xlsx_dosya_api(self, client: APIClient) -> None:
        from apps.okul.tests.test_excel_personel_parser import make_xlsx as make_personel_xlsx

        data = BytesIO(make_personel_xlsx([["ALİ ÖRNEK", "Müdür", "Coğrafya"]]))
        data.name = "personel.xlsx"
        resp = client.post("/api/v1/imports/personnel/commit/", {"file": data}, format="multipart")
        assert resp.status_code == 200
        assert Personnel.objects.count() == 1


# ---------------------------------------------------------------------------
# Şablon indirme
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestTemplateApi:
    def test_ogrenci_sablonu_parser_ile_uyumlu(self, client: APIClient) -> None:
        resp = client.get("/api/v1/templates/students/")
        assert resp.status_code == 200
        assert "spreadsheet" in resp["Content-Type"]
        from apps.okul import excel_veli

        grid = excel_veli.read_sheet(b"".join(cast(Any, resp).streaming_content))
        mapping = excel_veli.detect_columns(grid)
        assert mapping.is_usable
        assert list(grid[0]) == [
            "Sınıf",
            "Okul Numarası",
            "Öğrenci Adı",
            "Öğrenci Soyadı",
            "Öğrenci Doğum Tarihi",
        ]

    def test_personel_sablonu_parser_ile_uyumlu(self, client: APIClient) -> None:
        resp = client.get("/api/v1/templates/personnel/")
        assert resp.status_code == 200
        from apps.okul import excel_personel

        grid = excel_personel.read_sheet(b"".join(cast(Any, resp).streaming_content))
        mapping = excel_personel.detect_columns(grid)
        assert mapping.is_usable
        assert list(grid[0]) == ["Adı", "Soyadı", "Görevi", "Branşı"]


# ---------------------------------------------------------------------------
# Öğrenim seviyeleri (UI seçicileri — onur kurulu üye seviyesi, md. 183)
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestGradeLevelsApi:
    """`GET /grade-levels/` — seçilebilir seviyeler ÖĞRENCİ SİCİLİNDEN türetilir.

    OYS'de kaynak `SchoolConfig.prep_class_enabled` bayrağıydı; burada öyle bir
    alan yok. Dürüst kaynak fiilen kayıtlı öğrencilerin sınıf seviyeleridir;
    sicil boşken (kurulum öncesi) form çalışsın diye lise varsayılanı döner.
    Program 9-12 değişmezi taşır (import + serializer kapıları) — uç bu yüzden
    serializer'ın reddedeceği bir seviye ÖNERMEZ.
    """

    def test_sicilden_turetilir_ve_siralanir(self, client: APIClient) -> None:
        Student.objects.create(first_name="A", last_name="B", class_level=11)
        Student.objects.create(first_name="C", last_name="D", class_level=9)
        Student.objects.create(first_name="E", last_name="F", class_level=11)  # tekrar → tek satır
        data = client.get("/api/v1/grade-levels/").json()
        assert data["levels"] == [{"value": 9, "label": "9"}, {"value": 11, "label": "11"}]
        assert data["prep_enabled"] is False

    def test_onerilen_seviye_serializer_tarafindan_kabul_edilir(self, client: APIClient) -> None:
        """Uç ile elle-giriş kapısı ÇELİŞMEZ: önerilen her seviye kayıt kabul eder.

        Aksi hâlde form kullanıcıya seçtirir, kayıt 400 döner. 9-12 değişmezi
        her iki tarafta da geçerli olduğu sürece bu test yeşil kalır.
        """
        Student.objects.create(first_name="A", last_name="B", class_level=9)
        levels = [lvl["value"] for lvl in client.get("/api/v1/grade-levels/").json()["levels"]]
        for level in levels:
            resp = client.post(
                "/api/v1/students/",
                {"first_name": "DENEME", "last_name": f"SEVIYE{level}", "class_level": level},
                format="json",
            )
            assert resp.status_code == 201, (level, resp.content)

    def test_hazirlik_desteklenmez_prep_enabled_daima_false(self, client: APIClient) -> None:
        """Hazırlık (0) yazma kapılarından geçemez → uç da onu asla önermez."""
        assert (
            client.post(
                "/api/v1/students/",
                {"first_name": "A", "last_name": "B", "class_level": 0},
                format="json",
            ).status_code
            == 400
        )
        data = client.get("/api/v1/grade-levels/").json()
        assert data["prep_enabled"] is False
        assert 0 not in [lvl["value"] for lvl in data["levels"]]

    def test_sicil_bossa_lise_varsayilani(self, client: APIClient) -> None:
        data = client.get("/api/v1/grade-levels/").json()
        assert [lvl["value"] for lvl in data["levels"]] == [9, 10, 11, 12]
        assert data["prep_enabled"] is False

    def test_sinifsiz_ogrenci_listeyi_kirletmez(self, client: APIClient) -> None:
        Student.objects.create(first_name="A", last_name="B", class_level=None)
        Student.objects.create(first_name="C", last_name="D", class_level=10)
        data = client.get("/api/v1/grade-levels/").json()
        assert data["levels"] == [{"value": 10, "label": "10"}]
