"""apps.okul.excel_veli — başlık tespiti, fuzzy sütun eşleme, satır ayrıştırma."""

from __future__ import annotations

from io import BytesIO

import pytest
from openpyxl import Workbook

from apps.okul import excel_veli
from apps.okul.excel_veli import ParserError
from apps.okul.tests._fixtures import (
    AILE_KAYA,
    AILE_YILMAZ,
    TCKN_OGRENCI_1,
    TCKN_OGRENCI_2,
)

STANDARD_HEADER = [
    "Sınıf",
    "TCKN",
    "Numa",
    "Adı Soyadı",
    "Veli Kim",
    "Anne Adı SOYADI",
    "AnneTel",
    "Baba Adı SOYADI",
    "BabaTel",
]


def make_xlsx(
    rows: list[list[object]],
    header: list[object] | None = None,
    preamble: list[list[object]] | None = None,
) -> bytes:
    """Bellekte bir .xlsx üretir (header + satırlar)."""
    wb = Workbook()
    ws = wb.active
    for pre in preamble or []:
        ws.append(pre)
    ws.append(header if header is not None else STANDARD_HEADER)
    for r in rows:
        ws.append(r)
    bio = BytesIO()
    wb.save(bio)
    return bio.getvalue()


def test_standart_basliklar_eslenir() -> None:
    grid = excel_veli.read_sheet(make_xlsx([]))
    mapping = excel_veli.detect_columns(grid)
    assert mapping.is_usable
    for fld in (
        "class",
        "tckn",
        "number",
        "student_name",
        "guardian",
        "mother_name",
        "mother_phone",
        "father_name",
        "father_phone",
    ):
        assert fld in mapping.fields, fld


def test_fuzzy_baslik_varyasyonlari() -> None:
    header: list[object] = [
        "Sınıf/Şube",
        "T.C. Kimlik No",
        "Okul No",
        "Öğrenci Adı Soyadı",
        "Sorumlu Veli",
        "Anne",
        "Anne Telefon",
        "Baba",
        "Baba Telefon",
    ]
    grid = excel_veli.read_sheet(make_xlsx([], header=header))
    mapping = excel_veli.detect_columns(grid)
    assert mapping.is_usable
    assert mapping.fields["mother_name"] == 5
    assert mapping.fields["mother_phone"] == 6
    assert mapping.fields["father_name"] == 7
    assert mapping.fields["father_phone"] == 8


def test_anne_tel_isimle_karismaz() -> None:
    """'AnneTel' telefon alanına, 'Anne Adı SOYADI' isim alanına gitmeli."""
    grid = excel_veli.read_sheet(make_xlsx([]))
    mapping = excel_veli.detect_columns(grid)
    assert mapping.fields["mother_phone"] != mapping.fields["mother_name"]
    assert mapping.fields["father_phone"] != mapping.fields["father_name"]


def test_baslik_onunde_preamble_atlanir() -> None:
    preamble: list[list[object]] = [
        ["ÖZDEN CENGİZ ANADOLU LİSESİ"],
        [],
        ["Rapor Tarihi: 26.05.2026"],
    ]
    grid = excel_veli.read_sheet(make_xlsx([], preamble=preamble))
    mapping = excel_veli.detect_columns(grid)
    assert mapping.header_row == 3
    assert mapping.is_usable


def test_kritik_sutun_eksik_parser_error() -> None:
    # Ne okul numarası ne TCKN var.
    header: list[object] = ["Sınıf", "Adı Soyadı", "Veli Kim"]
    data = make_xlsx([["10/A", "ALI VELI", "ANNE"]], header=header)
    with pytest.raises(ParserError, match="number veya tckn"):
        excel_veli.parse_workbook(data)


def test_yeni_sablon_ayri_ad_soyad_ve_tcknsiz_okunur() -> None:
    header: list[object] = [
        "Sınıf",
        "Okul Numarası",
        "Öğrenci Adı",
        "Öğrenci Soyadı",
        "Öğrenci Doğum Tarihi",
    ]
    data = make_xlsx([["9/A", 1001, "ALİ CAN", "YILMAZ", "01.01.2011"]], header=header)
    _mapping, rows = excel_veli.parse_workbook(data)
    assert rows[0].tckn is None
    assert rows[0].student_first == "ALİ CAN"
    assert rows[0].student_last == "YILMAZ"
    assert rows[0].birth_date is not None


def test_satir_tip_donusumleri() -> None:
    rows: list[list[object]] = [
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
    _mapping, parsed = excel_veli.parse_workbook(make_xlsx(rows))
    assert len(parsed) == 1
    row = parsed[0]
    assert row.class_level == 10 and row.class_section == "A"
    assert row.student_number == "2612"
    assert row.student_first == AILE_YILMAZ["ogrenci_first"]
    assert row.student_last == AILE_YILMAZ["ogrenci_last"]
    assert row.guardian == "ANNE"
    # int telefon → '0' önekli 11 hane.
    assert row.mother.phone == f"0{AILE_YILMAZ['anne_tel']}"
    assert row.father.phone == f"0{AILE_YILMAZ['baba_tel']}"
    assert row.mother.first_name == AILE_YILMAZ["anne_first"]
    assert row.mother.last_name == AILE_YILMAZ["anne_last"]


def test_eksik_baba_parsed_parent_bos() -> None:
    rows = [
        [
            "10/A",
            TCKN_OGRENCI_2,
            2543,
            AILE_KAYA["ogrenci_ad_soyad"],
            "ANNE",
            AILE_KAYA["anne_ad_soyad"],
            AILE_KAYA["anne_tel"],
            None,
            None,
        ]
    ]
    _mapping, parsed = excel_veli.parse_workbook(make_xlsx(rows))
    row = parsed[0]
    assert row.mother.has_any_data is True
    assert row.father.has_any_data is False


def test_bos_satir_atlanir() -> None:
    rows: list[list[object]] = [
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
        ],
        [None, None, None, None, None, None, None, None, None],
    ]
    _mapping, parsed = excel_veli.parse_workbook(make_xlsx(rows))
    assert len(parsed) == 1


def test_fixture_dosyasi_ayristirilir() -> None:
    """Anonimleştirilmiş gerçek fixture parse edilebilmeli.

    Fixture .xlsx KVKK gereği git'e komitelenmez (*.xlsx .gitignore'da); yerelde
    varsa çalışır, CI gibi dosyanın bulunmadığı ortamlarda atlanır. Parser'ın
    biçim davranışı zaten yukarıdaki bellek-içi (make_xlsx) testlerle kapsanır.
    """
    from pathlib import Path

    fixture = Path(__file__).parent / "fixtures" / "veli_iletisim_ornek.xlsx"
    if not fixture.exists():
        pytest.skip("Anonim fixture .xlsx yok (gitignore; yalnız yerel).")
    mapping, parsed = excel_veli.parse_workbook(fixture.read_bytes())
    assert mapping.is_usable
    assert len(parsed) == 30
    assert all(r.tckn is not None for r in parsed)  # fixture TCKN'leri geçerli


# --------------------------------------------------------------- standart OYS şablonu (Tur 531)

OYS_TEMPLATE_HEADER: list[object] = [
    "Sınıf/Şube",
    "Okul No",
    "T.C. Kimlik No",
    "Adı Soyadı",
    "Doğum Tarihi",
    "Cinsiyet",
    "Anne Adı Soyadı",
    "Anne Telefon",
    "Baba Adı Soyadı",
    "Baba Telefon",
    "Sorumlu Veli",
]


def test_oys_sablonu_yeni_alanlar_parse_edilir() -> None:
    """Standart şablon başlıkları + doğum tarihi (datetime hücre) + cinsiyet çözülür."""
    from datetime import date, datetime

    data = make_xlsx(
        [
            [
                "10/A",
                2612,
                TCKN_OGRENCI_1,
                AILE_YILMAZ["ogrenci_ad_soyad"],
                datetime(2010, 3, 12),
                "K",
                AILE_YILMAZ["anne_ad_soyad"],
                AILE_YILMAZ["anne_tel"],
                AILE_YILMAZ["baba_ad_soyad"],
                AILE_YILMAZ["baba_tel"],
                "ANNE",
            ]
        ],
        header=OYS_TEMPLATE_HEADER,
    )
    mapping, rows = excel_veli.parse_workbook(data)
    assert mapping.is_usable
    assert "birth_date" in mapping.fields and "gender" in mapping.fields
    row = rows[0]
    assert row.birth_date == date(2010, 3, 12)
    assert row.gender == "K"
    assert row.guardian == "ANNE"
    # Öğrenci adı anne/baba adına KAÇMADI (öncelik sırası korunuyor).
    assert row.raw_student_name == AILE_YILMAZ["ogrenci_ad_soyad"]


def test_oys_sablonu_metin_tarih_de_calisir() -> None:
    from datetime import date

    data = make_xlsx(
        [
            [
                "9/B",
                101,
                TCKN_OGRENCI_2,
                AILE_KAYA["ogrenci_ad_soyad"],
                "05.11.2011",
                "Erkek",
                AILE_KAYA["anne_ad_soyad"],
                AILE_KAYA["anne_tel"],
                "",
                "",
                "BABA",
            ]
        ],
        header=OYS_TEMPLATE_HEADER,
    )
    _mapping, rows = excel_veli.parse_workbook(data)
    assert rows[0].birth_date == date(2011, 11, 5)
    assert rows[0].gender == "E"


def test_eokul_basliklarinda_yeni_alanlar_bos_kalir() -> None:
    """REGRESYON: e-Okul başlık setinde birth_date/gender sütunu yok → alanlar boş."""
    data = make_xlsx(
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
    mapping, rows = excel_veli.parse_workbook(data)
    assert "birth_date" not in mapping.fields and "gender" not in mapping.fields
    row = rows[0]
    assert row.birth_date is None and row.raw_birth_date == ""
    assert row.gender == "" and row.raw_gender == ""


def test_oys_sablonu_gecersiz_cinsiyet_bos() -> None:
    data = make_xlsx(
        [
            [
                "10/A",
                2612,
                TCKN_OGRENCI_1,
                AILE_YILMAZ["ogrenci_ad_soyad"],
                "",
                "X",
                "",
                "",
                "",
                "",
                "",
            ]
        ],
        header=OYS_TEMPLATE_HEADER,
    )
    _mapping, rows = excel_veli.parse_workbook(data)
    assert rows[0].gender == "" and rows[0].raw_gender == "X"
    assert rows[0].birth_date is None and rows[0].raw_birth_date == ""
