"""Metin yardımcıları — OYS `shared/text.py`'den gereken kadarı (mask_tckn AYNEN).

Rapor/log çıktılarına ham TCKN yazılmaz; maskeleme satırı yine ayırt edilebilir
kılar (KVKK — OYS D23 kararı bu projede de geçerli ilke).
"""

from __future__ import annotations

# Türkçe büyük harf için yalnız i/ı özel: çıplak str.upper() "i" → "I" yapar (doğrusu "İ").
_TR_I_MAP = str.maketrans({"i": "İ", "ı": "I"})


def tr_upper(value: str) -> str:
    """Metni TÜRKÇE büyük harfe çevirir ("i" → "İ", "ı" → "I", "ş" → "Ş").

    Evraka basılacak metin içindir; ASCII'ye KATLAMAZ (karşılaştırma anahtarı değildir —
    o iş `apps.okul.normalize` içindeki `_TR_UPPER_MAP` çevirisinin, CLAUDE.md §7.2).
    """
    return value.translate(_TR_I_MAP).upper()


def mask_tckn(raw: str) -> str:
    """TCKN'yi rapor/log için maskeler: ilk 3 + yıldızlar + son 2 (`123******45`).

    Girdi geçersiz TCKN de olabilir (boş, harfli, kısa) — savunmacı davranır:
    7 karakterden kısa her şey tümden `***` olur ki hiçbir kişisel iz kalmasın.
    """
    value = (raw or "").strip()
    if len(value) < 7:
        return "***" if value else ""
    return f"{value[:3]}{'*' * (len(value) - 5)}{value[-2:]}"
