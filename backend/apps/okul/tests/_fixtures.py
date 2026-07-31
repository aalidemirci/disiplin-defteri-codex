"""Anonim test verisi sabitleri (OYS `apps/core/tests/_fixtures.py`'den kırpılmış kopya).

Gerçek kişi/aile temsili YOKTUR — Türkçe karakter + isim havuzu test
gerçekçiliğini koruyacak şekilde elle kuruldu. Yeni test yazarken aynı aileyi
tekrar kullanın; gerekirse aynı desene yeni `AILE_*` ekleyin.
"""

from __future__ import annotations

from typing import Final

# Sahte TCKN'ler — parser/Excel testlerinde 11-hane formatı sınamak için.
# Checksum GEÇERLİ tutuldu (standalone import upsert'i TCKN checksum'una bakar);
# 10000000\d{3} whitelist deseniyle uyumlu.
TCKN_OGRENCI_1: Final = 10000000146
TCKN_OGRENCI_2: Final = 10000000214

# Aile 1 — anne sorumlu veli (genel "Veli Kim: ANNE" akışı)
AILE_YILMAZ: Final = {
    "ogrenci_ad_soyad": "EMRE CAN YILMAZ",
    "ogrenci_first": "EMRE CAN",
    "ogrenci_last": "YILMAZ",
    "anne_ad_soyad": "AYŞE YILMAZ",
    "anne_first": "AYŞE",
    "anne_last": "YILMAZ",
    "anne_tel": 5550000101,
    "baba_ad_soyad": "MEHMET YILMAZ",
    "baba_first": "MEHMET",
    "baba_last": "YILMAZ",
    "baba_tel": 5550000102,
}

# Aile 2 — tek veli (sadece anne) — "baba alanı boş" testleri için
AILE_KAYA: Final = {
    "ogrenci_ad_soyad": "ZEYNEP KAYA",
    "ogrenci_first": "ZEYNEP",
    "ogrenci_last": "KAYA",
    "anne_ad_soyad": "FATMA KAYA",
    "anne_first": "FATMA",
    "anne_last": "KAYA",
    "anne_tel": 5550000103,
}
