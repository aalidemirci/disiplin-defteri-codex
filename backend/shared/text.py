"""Metin yardımcıları — OYS `shared/text.py`'den gereken kadarı (mask_tckn AYNEN).

Rapor/log çıktılarına ham TCKN yazılmaz; maskeleme satırı yine ayırt edilebilir
kılar (KVKK — OYS D23 kararı bu projede de geçerli ilke).
"""

from __future__ import annotations


def mask_tckn(raw: str) -> str:
    """TCKN'yi rapor/log için maskeler: ilk 3 + yıldızlar + son 2 (`123******45`).

    Girdi geçersiz TCKN de olabilir (boş, harfli, kısa) — savunmacı davranır:
    7 karakterden kısa her şey tümden `***` olur ki hiçbir kişisel iz kalmasın.
    """
    value = (raw or "").strip()
    if len(value) < 7:
        return "***" if value else ""
    return f"{value[:3]}{'*' * (len(value) - 5)}{value[-2:]}"
