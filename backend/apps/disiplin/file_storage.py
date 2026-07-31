"""Disiplin dosya eki depolama — doğrulama + UUID adlı diske yazım.

OYS `ogrenci_isleri/file_storage.py`'den uyarlama: MIME tespiti `python-magic`
(libmagic) yerine saf-Python `filetype` ile (tasarım §5 — sistem paketi
bağımlılığı yok); devamsızlık mektubu staging bölümleri ALINMADI (kapsam dışı).
Dosya, veri dizini altındaki media klasöründe `discipline/case_<id>/<uuid>.<ext>`
yolunda saklanır; orijinal ad DB'de tutulur.
"""

from __future__ import annotations

import hashlib
import os
import uuid
from dataclasses import dataclass
from pathlib import Path

import filetype
from django.conf import settings

# İzin verilen MIME türleri → tercih edilen uzantı.
ALLOWED_MIME_TYPES: dict[str, str] = {
    "application/pdf": "pdf",
    "image/jpeg": "jpg",
    "image/png": "png",
}


class FileValidationError(Exception):
    """Yüklenen dosya doğrulamadan geçemedi (Türkçe mesaj taşır)."""


@dataclass
class StoredFile:
    """Diske yazılmış dosyanın meta verisi (DisciplineAttachment'a yazılır)."""

    file_path: str  # MEDIA_ROOT'a göreli
    mime_type: str
    file_size_bytes: int
    sha256: str


def max_upload_bytes() -> int:
    """İzin verilen azami yükleme boyutu (bayt) — settings.MAX_UPLOAD_SIZE_MB."""
    return int(settings.MAX_UPLOAD_SIZE_MB) * 1024 * 1024


def compute_sha256(file_bytes: bytes) -> str:
    """Dosyanın SHA256 özeti (bütünlük + yinelenen tespiti)."""
    return hashlib.sha256(file_bytes).hexdigest()


def detect_mime(file_bytes: bytes) -> str:
    """İçerikten gerçek MIME türünü tespit eder (uzantı güvenilmez).

    `filetype` sihirli baytlara bakar; tanıyamazsa octet-stream döner (reddedilir).
    """
    kind = filetype.guess(file_bytes)
    return kind.mime if kind is not None else "application/octet-stream"


def validate_upload(file_bytes: bytes) -> str:
    """Boyut + MIME doğrular; geçerliyse tespit edilen MIME türünü döner.

    Boş/aşırı büyük/izinsiz tür → `FileValidationError` (dosya diske yazılmaz).
    """
    size = len(file_bytes)
    if size == 0:
        raise FileValidationError("Boş dosya yüklenemez.")
    limit = max_upload_bytes()
    if size > limit:
        raise FileValidationError(
            f"Dosya çok büyük ({size // (1024 * 1024)} MB). "
            f"Azami {settings.MAX_UPLOAD_SIZE_MB} MB."
        )
    mime = detect_mime(file_bytes)
    if mime not in ALLOWED_MIME_TYPES:
        raise FileValidationError(
            "İzin verilmeyen dosya türü. Yalnızca PDF, JPEG ve PNG kabul edilir."
        )
    return mime


def generate_uuid_filename(mime_type: str) -> str:
    """MIME türüne uygun uzantıyla rastgele (UUID) dosya adı üretir."""
    ext = ALLOWED_MIME_TYPES.get(mime_type, "bin")
    return f"{uuid.uuid4().hex}.{ext}"


def _case_dir(case_id: int) -> Path:
    """Bir dosyaya ait medya klasörü (MEDIA_ROOT altında)."""
    return Path(settings.MEDIA_ROOT) / "discipline" / f"case_{case_id}"


def absolute_path(relative_path: str) -> Path:
    """Göreli yolu MEDIA_ROOT'a göre mutlak yola çevirir (indirme için)."""
    return Path(settings.MEDIA_ROOT) / relative_path


def save_attachment(*, case_id: int, file_bytes: bytes) -> StoredFile:
    """Doğrulanmış bir dosyayı diske yazar ve meta verisini döner.

    Doğrulama burada da tekrar çalışır — çağıran atlasa bile geçersiz dosya yazılmaz.
    """
    mime = validate_upload(file_bytes)
    sha256 = compute_sha256(file_bytes)

    case_dir = _case_dir(case_id)
    case_dir.mkdir(parents=True, exist_ok=True)
    try:
        # KVKK: klasör diğer OS kullanıcılarının erişimine kapalı.
        os.chmod(case_dir, 0o750)  # noqa: S103
    except OSError:
        # Bazı dosya sistemleri (örn. Windows) chmod desteklemez — yok say.
        pass

    filename = generate_uuid_filename(mime)
    target = case_dir / filename
    target.write_bytes(file_bytes)
    try:
        os.chmod(target, 0o640)
    except OSError:
        pass

    relative = str(Path("discipline") / f"case_{case_id}" / filename)
    return StoredFile(
        file_path=relative,
        mime_type=mime,
        file_size_bytes=len(file_bytes),
        sha256=sha256,
    )
