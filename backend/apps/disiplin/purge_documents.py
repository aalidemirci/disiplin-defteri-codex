"""md. 157/7 imha tutanağı üretimi (F5-D2, tasarım §4.6).

`honor_documents.py` deseninin birebir kardeşi: disiplin evrak motorunun
(`documents.render_pdf` + `documents/base.html` + `shared.letterhead`) case'e
bağlı OLMAYAN yeniden kullanımı.

Fark: bu belge "no-trace" DEĞİL, tam tersi — **kalıcı tek izdir**. İmha edilen
kayıtlar (uyarılar, uyarı yazısı kütük satırları, Dal A dosyaları) geri dönüşsüz
silindiğinden geriye yalnız bu PDF kalır. Bu yüzden indirilmesinin yanı sıra
`MEDIA_ROOT/imha/` altına da yazılır (`store_purge_record`).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from django.conf import settings
from django.utils import timezone

from apps.disiplin.documents import render_pdf
from shared.letterhead import letterhead_context

PURGE_RECORD_TEMPLATE = "disiplin/documents/purge_record.html"

# İmha müdür işlemidir (kurul değil) — antet alt satırı Okul Müdürlüğü'dür.
_UNIT = "Okul Müdürlüğü"

# Tutanakların kalıcı klasörü (MEDIA_ROOT altında göreli).
PURGE_RECORD_DIR = "imha"


@dataclass(frozen=True)
class PurgeRecordRow:
    """Tutanak tablosunun bir satırı — öğrenci + dosya no + tarih + kayıt dökümü."""

    student_name: str
    case_no: str
    record_date: date
    detail: str


def render_purge_record(
    *,
    rows: list[PurgeRecordRow],
    totals: dict[str, int],
    purge_date: date,
    scope_label: str,
    transfer_date: date | None = None,
    purge_deadline: date | None = None,
) -> bytes:
    """İmha tutanağı PDF'i üretir (md. 157/7-d).

    `scope_label` insan-okunur kapsam ("Ders yılı sonu toplu imhası" / "Nakil —
    <öğrenci>"); `transfer_date`/`purge_deadline` yalnız nakil senaryosunda
    doldurulur (tutanakta "+5 iş günü" son günü basılır).
    """
    from apps.okul.services import setup as okul_setup

    identity = okul_setup.get_letterhead_identity()
    ctx: dict[str, Any] = {
        **letterhead_context(
            school_name=identity["school_name"],
            unit=_UNIT,
            district=identity["district"],
            principal_name=identity["principal_name"],
        ),
        "generated_at": timezone.now(),
        "purge_date": purge_date,
        "scope_label": scope_label,
        "transfer_date": transfer_date,
        "purge_deadline": purge_deadline,
        "rows": rows,
        "totals": totals,
    }
    return render_pdf(PURGE_RECORD_TEMPLATE, ctx)


def record_filename(purge_date: date, *, now: datetime | None = None) -> str:
    """Tutanak dosya adı — imha tarihi + üretim saati (aynı gün birden çok imha)."""
    stamp = (now or timezone.localtime()).strftime("%H%M%S")
    return f"imha-tutanagi-{purge_date:%Y%m%d}-{stamp}.pdf"


def store_purge_record(pdf_bytes: bytes, *, filename: str) -> str:
    """Tutanağı `MEDIA_ROOT/imha/` altına yazar; MEDIA_ROOT'a göreli yolu döner.

    Kayıtlar silindikten sonra geriye kalan TEK iz budur — kullanıcı indirmeyi
    unutsa bile program veri dizininde durur (yedeklemeye de dahil olur).
    """
    target_dir = Path(settings.MEDIA_ROOT) / PURGE_RECORD_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    try:
        # KVKK: klasör diğer OS kullanıcılarının erişimine kapalı (file_storage deseni).
        os.chmod(target_dir, 0o750)  # noqa: S103
    except OSError:
        # Bazı dosya sistemleri (örn. Windows) chmod desteklemez — yok say.
        pass

    target = target_dir / filename
    target.write_bytes(pdf_bytes)
    try:
        os.chmod(target, 0o640)
    except OSError:
        pass
    return str(Path(PURGE_RECORD_DIR) / filename)
