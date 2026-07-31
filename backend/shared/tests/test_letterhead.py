"""`shared.letterhead` saf fonksiyon testleri (OYS'den AYNEN alınan mantık)."""

from __future__ import annotations

from shared.letterhead import letterhead_authority, letterhead_context


def test_letterhead_authority_ilce_verilirse() -> None:
    assert letterhead_authority("Kadıköy") == "Kadıköy KAYMAKAMLIĞI"


def test_letterhead_authority_ilce_bosluklu_kirpilir() -> None:
    assert letterhead_authority("  Üsküdar  ") == "Üsküdar KAYMAKAMLIĞI"


def test_letterhead_authority_ilce_yoksa_yer_tutucu() -> None:
    assert letterhead_authority(None) == "…………… KAYMAKAMLIĞI"
    assert letterhead_authority("") == "…………… KAYMAKAMLIĞI"


def test_letterhead_context_tum_alanlar() -> None:
    context = letterhead_context(
        school_name="Örnek Anadolu Lisesi",
        unit="Disiplin Kurulu",
        district="Kadıköy",
        principal_name="  Ayşe Yılmaz  ",
    )

    assert context == {
        "tc": "T.C.",
        "authority": "Kadıköy KAYMAKAMLIĞI",
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
