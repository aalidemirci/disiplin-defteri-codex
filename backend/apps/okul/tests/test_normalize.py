"""apps.okul.normalize — saf normalize edici testleri (DB gerektirmez)."""

from __future__ import annotations

from apps.okul import normalize


def valid_tckn(first9: str) -> str:
    """Test için checksum'ı geçerli TCKN üretir (ilk 9 hane verilir)."""
    d = [int(c) for c in first9]
    odd = d[0] + d[2] + d[4] + d[6] + d[8]
    even = d[1] + d[3] + d[5] + d[7]
    d.append((odd * 7 - even) % 10)
    d.append(sum(d[:10]) % 10)
    return "".join(str(x) for x in d)


# --- normalize_tckn ---


def test_tckn_gecerli() -> None:
    t = valid_tckn("100000001")
    assert normalize.normalize_tckn(t) == t


def test_tckn_float_metni_temizlenir() -> None:
    t = valid_tckn("234567890")
    assert normalize.normalize_tckn(f"{t}.0") == t


def test_tckn_bosluk_temizlenir() -> None:
    t = valid_tckn("345678901")
    assert normalize.normalize_tckn(f"  {t} ") == t


def test_tckn_checksum_gecersiz_none() -> None:
    t = valid_tckn("456789012")
    # Son haneyi boz.
    bozuk = t[:-1] + str((int(t[-1]) + 1) % 10)
    assert normalize.normalize_tckn(bozuk) is None


def test_tckn_on_hane_none() -> None:
    assert normalize.normalize_tckn("1234567890") is None


def test_tckn_oniki_hane_none() -> None:
    assert normalize.normalize_tckn("123456789012") is None


def test_tckn_ilk_hane_sifir_none() -> None:
    assert normalize.normalize_tckn("01234567890") is None


def test_tckn_bos_none() -> None:
    assert normalize.normalize_tckn("") is None
    assert normalize.normalize_tckn(None) is None


# --- normalize_phone ---


def test_phone_int_bastaki_sifir_eklenir() -> None:
    assert normalize.normalize_phone(5550000101) == "05550000101"


def test_phone_zaten_onbir_hane() -> None:
    assert normalize.normalize_phone("05550000101") == "05550000101"


def test_phone_ulke_kodu_artigi() -> None:
    assert normalize.normalize_phone("+90 555 000 0101") == "05550000101"
    assert normalize.normalize_phone("905550000101") == "05550000101"


def test_phone_ayraclar_temizlenir() -> None:
    assert normalize.normalize_phone("0555-000-01-01") == "05550000101"
    assert normalize.normalize_phone("(0555) 000 0101") == "05550000101"


def test_phone_float_metni() -> None:
    assert normalize.normalize_phone("5550000101.0") == "05550000101"


def test_phone_gecersiz_none() -> None:
    assert normalize.normalize_phone("530387055") is None  # 9 hane
    assert normalize.normalize_phone("") is None
    assert normalize.normalize_phone(None) is None


# --- normalize_class_section ---


def test_class_slash() -> None:
    assert normalize.normalize_class_section("10/A") == (10, "A")


def test_class_tire() -> None:
    assert normalize.normalize_class_section("10-A") == (10, "A")


def test_class_bosluk_ve_kucuk_harf() -> None:
    assert normalize.normalize_class_section("9 b") == (9, "B")


def test_class_turkce_sube_ascii() -> None:
    assert normalize.normalize_class_section("12/Ş") == (12, "S")


def test_class_seviye_disinda_none() -> None:
    assert normalize.normalize_class_section("13/A") is None
    assert normalize.normalize_class_section("8/A") is None


def test_class_ayristirilamaz_none() -> None:
    assert normalize.normalize_class_section("abc/X") is None
    assert normalize.normalize_class_section("") is None
    assert normalize.normalize_class_section(None) is None


# --- split_full_name ---


def test_split_iki_kelime() -> None:
    assert normalize.split_full_name("ALİ YILMAZ") == ("ALİ", "YILMAZ")


def test_split_uc_kelime_son_soyad() -> None:
    assert normalize.split_full_name("EMRE CAN YILMAZ") == ("EMRE CAN", "YILMAZ")


def test_split_dort_kelime() -> None:
    assert normalize.split_full_name("ZEYNEP NUR ÇELİK OĞLU") == (
        "ZEYNEP NUR ÇELİK",
        "OĞLU",
    )


def test_split_tek_kelime() -> None:
    assert normalize.split_full_name("VELI") == ("VELI", "")


def test_split_bos() -> None:
    assert normalize.split_full_name("") == ("", "")
    assert normalize.split_full_name(None) == ("", "")


# --- normalize_gender ---


def test_gender_erkek() -> None:
    assert normalize.normalize_gender("E") == "E"
    assert normalize.normalize_gender("ERKEK") == "E"
    assert normalize.normalize_gender("male") == "E"


def test_gender_kiz() -> None:
    assert normalize.normalize_gender("K") == "K"
    assert normalize.normalize_gender("KIZ") == "K"


def test_gender_bos_veya_bilinmeyen() -> None:
    assert normalize.normalize_gender("") == ""
    assert normalize.normalize_gender(None) == ""
    assert normalize.normalize_gender("xyz") == ""


# --- normalize_excel_date (Tur 531, ADR-0034) ---


def test_excel_date_datetime_ve_date_hucre() -> None:
    from datetime import date, datetime

    assert normalize.normalize_excel_date(datetime(2010, 3, 12, 0, 0)) == date(2010, 3, 12)
    assert normalize.normalize_excel_date(date(2010, 3, 12)) == date(2010, 3, 12)


def test_excel_date_metin_bicimleri() -> None:
    from datetime import date

    assert normalize.normalize_excel_date("12.03.2010") == date(2010, 3, 12)
    assert normalize.normalize_excel_date("12/03/2010") == date(2010, 3, 12)
    assert normalize.normalize_excel_date("2010-03-12") == date(2010, 3, 12)
    # Excel bazen zaman kuyruğu ekler.
    assert normalize.normalize_excel_date("12.03.2010 00:00:00") == date(2010, 3, 12)


def test_excel_date_gecersiz_degerler() -> None:
    assert normalize.normalize_excel_date(None) is None
    assert normalize.normalize_excel_date("") is None
    assert normalize.normalize_excel_date("saçma") is None
    assert normalize.normalize_excel_date("31.02.2010") is None  # geçersiz gün
    assert normalize.normalize_excel_date("12.03.1850") is None  # yıl < 1900


def test_excel_date_gelecek_dogum_reddedilir() -> None:
    from datetime import date, timedelta

    tomorrow = date.today() + timedelta(days=1)
    assert normalize.normalize_excel_date(tomorrow.strftime("%d.%m.%Y")) is None


def test_excel_date_gelecek_ise_baslama_kabul() -> None:
    """İşe başlama meşru olarak gelecekte olabilir (allow_future=True; ADR-0034)."""
    from datetime import date, timedelta

    tomorrow = date.today() + timedelta(days=1)
    assert (
        normalize.normalize_excel_date(tomorrow.strftime("%d.%m.%Y"), allow_future=True) == tomorrow
    )
    # Ama +2 yıldan ilerisi yazım hatası sayılır.
    far = date.today() + timedelta(days=800)
    assert normalize.normalize_excel_date(far.strftime("%d.%m.%Y"), allow_future=True) is None
