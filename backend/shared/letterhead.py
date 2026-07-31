"""Resmî evrak antedi (letterhead) — paylaşılan sunum yardımcısı.

OYS'nin (Okul Yönetim Sistemi) `shared/letterhead.py` dosyasından AYNEN alındı.
Disiplin PDF şablonları ortak bir resmî antet kullanır:

    T.C.
    <İLÇE> KAYMAKAMLIĞI
    <OKUL ADI>
    <BİRİM>

NOT (bu proje için): Aşağıdaki `settings.OYS_DISTRICT_NAME` / `settings.OYS_PRINCIPAL_NAME`
env fallback'leri OYS'den miras kalan ÖLÜ YOLdur — bu ayarlar `config/settings.py`'de
tanımlı değildir, dolayısıyla `getattr(..., "")` her zaman boş döner. Okul/ilçe/müdür
adı ileride `apps.okul` içindeki bir yapılandırma modelinden çözümlenip parametre
olarak (`district=`, `principal_name=`) geçirilecektir (OYS'deki `core.services.
get_letterhead_identity` örüntüsü). İlçe/müdür adı boşsa antette yer-tutucu görünür.
"""

from __future__ import annotations

from django.conf import settings


def letterhead_authority(district: str | None = None) -> str:
    """Antedin ikinci satırı: '<İLÇE> KAYMAKAMLIĞI' (ilçe yoksa yer-tutucu).

    `district` verilmezse ``settings.OYS_DISTRICT_NAME``'e düşer (geriye uyumlu;
    bkz. modül docstring'i — bu proje için ölü yol)."""
    name = district if district is not None else getattr(settings, "OYS_DISTRICT_NAME", "")
    name = (name or "").strip()
    return f"{name} KAYMAKAMLIĞI" if name else "…………… KAYMAKAMLIĞI"


def letterhead_context(
    *,
    school_name: str,
    unit: str = "",
    district: str | None = None,
    principal_name: str | None = None,
) -> dict[str, str]:
    """PDF şablonları için ortak antet bağlamı (T.C. + kaymakamlık + okul + birim +
    okul müdürü adı). `principal_name` UYGUNDUR/imza bloklarında kullanılır.

    `district`/`principal_name` verilmezse ``settings.OYS_*``'e düşer (bkz. modül
    docstring'i — bu proje için ölü yol)."""
    principal = (
        principal_name
        if principal_name is not None
        else getattr(settings, "OYS_PRINCIPAL_NAME", "")
    )
    return {
        "tc": "T.C.",
        "authority": letterhead_authority(district),
        "school_name": school_name,
        "unit": unit,
        "principal_name": (principal or "").strip(),
    }
