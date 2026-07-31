"""Dosya eki depolama testleri (F2) — doğrulama + UUID adlandırma + dedup."""

from __future__ import annotations

from datetime import date

import pytest

from apps.disiplin import file_storage, services
from apps.disiplin.models import AttachmentType, DisciplineCase
from apps.disiplin.tests.factories import SchoolYearFactory, StudentFactory

pytestmark = pytest.mark.django_db

# filetype sihirli baytlara bakar — minimal ama geçerli imzalar.
PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + b"\x00" * 17 + b"IEND\xaeB`\x82"


def _case() -> DisciplineCase:
    SchoolYearFactory()
    s = StudentFactory()
    return services.create_case(
        petition_date=date(2026, 5, 18),
        petitioner_name="A",
        petitioner_role="IDARE",
        summary="x",
        student_ids=[s.pk],
    )


def test_pdf_kabul_edilir_uuid_adla_yazilir(tmp_path: object, settings: object) -> None:
    settings.MEDIA_ROOT = tmp_path  # type: ignore[attr-defined]
    case = _case()
    attachment, is_duplicate = services.add_attachment(
        case=case,
        file_bytes=PDF_BYTES,
        original_filename="dilekçe taraması.pdf",
        file_type=AttachmentType.PETITION_SCAN,
    )
    assert is_duplicate is False
    assert attachment.mime_type == "application/pdf"
    assert attachment.original_filename == "dilekçe taraması.pdf"
    # Diskteki ad UUID'dir (tahmin edilemez), orijinal ad yalnız DB'de.
    assert "dilekçe" not in attachment.file_path
    assert file_storage.absolute_path(attachment.file_path).exists()


def test_ayni_dosya_ikinci_kez_duplicate_isaretlenir(tmp_path: object, settings: object) -> None:
    settings.MEDIA_ROOT = tmp_path  # type: ignore[attr-defined]
    case = _case()
    services.add_attachment(
        case=case,
        file_bytes=PDF_BYTES,
        original_filename="a.pdf",
        file_type=AttachmentType.OTHER,
    )
    _attachment, is_duplicate = services.add_attachment(
        case=case,
        file_bytes=PDF_BYTES,
        original_filename="b.pdf",
        file_type=AttachmentType.OTHER,
    )
    assert is_duplicate is True


def test_izinsiz_tur_reddedilir() -> None:
    with pytest.raises(file_storage.FileValidationError, match="PDF, JPEG ve PNG"):
        file_storage.validate_upload(b"duz metin dosyasi - mime tespit edilemez")


def test_bos_dosya_reddedilir() -> None:
    with pytest.raises(file_storage.FileValidationError, match="Boş"):
        file_storage.validate_upload(b"")


def test_png_kabul_edilir() -> None:
    assert file_storage.validate_upload(PNG_BYTES) == "image/png"
