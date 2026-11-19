"""`shared.letterhead` saf fonksiyon testleri (OYS'den AYNEN alınan mantık).

19.11.2026 (kullanıcı kararı): ilçe adı antette TÜRKÇE büyük harfle basılır.
"""

from __future__ import annotations

from shared.letterhead import letterhead_authority, letterhead_context
from shared.text import tr_upper


def test_letterhead_authority_ilce_verilirse() -> None:
    assert letterhead_authority("Kadıköy") == "KADIKÖY KAYMAKAMLIĞI"


def test_letterhead_authority_ilce_bosluklu_kirpilir() -> None:
    assert letterhead_authority("  Üsküdar  ") == "ÜSKÜDAR KAYMAKAMLIĞI"


def test_letterhead_authority_turkce_buyuk_harf_i_noktali() -> None:
    """Çıplak .upper() "i" → "I" yapardı; antette "SİLİVRİ" basılmalı (CLAUDE.md §7.2)."""
    assert letterhead_authority("Silivri") == "SİLİVRİ KAYMAKAMLIĞI"
    assert letterhead_authority("Ağrı Merkez") == "AĞRI MERKEZ KAYMAKAMLIĞI"
    assert letterhead_authority("Şişli") == "ŞİŞLİ KAYMAKAMLIĞI"


def test_letterhead_authority_buyuk_harfli_ilce_degismez() -> None:
    """Zaten büyük harfle girilmiş ilçede çıktı OYS ile aynıdır."""
    assert letterhead_authority("SANCAKTEPE") == "SANCAKTEPE KAYMAKAMLIĞI"


def test_letterhead_authority_ilce_yoksa_yer_tutucu() -> None:
    assert letterhead_authority(None) == "…………… KAYMAKAMLIĞI"
    assert letterhead_authority("") == "…………… KAYMAKAMLIĞI"
    assert letterhead_authority("   ") == "…………… KAYMAKAMLIĞI"


def test_tr_upper() -> None:
    assert tr_upper("iğneada ılgaz çeşme ödemiş") == "İĞNEADA ILGAZ ÇEŞME ÖDEMİŞ"
    assert tr_upper("") == ""


def test_letterhead_context_tum_alanlar() -> None:
    context = letterhead_context(
        school_name="Örnek Anadolu Lisesi",
        unit="Disiplin Kurulu",
        district="Kadıköy",
        principal_name="  Ayşe Yılmaz  ",
    )

    assert context == {
        "tc": "T.C.",
        "authority": "KADIKÖY KAYMAKAMLIĞI",
        "school_name": "Örnek Anadolu Lisesi",
        "unit": "Disiplin Kurulu",
        "principal_name": "Ayşe Yılmaz",
    }


def test_letterhead_context_opsiyonel_alanlar_bossa() -> None:
    context = letterhead_context(school_name="Test Lisesi")

    assert context["school_name"] == "Test Lisesi"
    assert context["unit"] == ""
    assert context["authority"] == "…………… KAYMAKAMLIĞI"
    assert context["principal_name"] == ""
