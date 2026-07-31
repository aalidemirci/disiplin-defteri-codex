"""Evrak kütüğü servisleri — üretilen/eklenen belge izi ve PDF kopyası.

OYS `services/discipline_documents.py`'den temizlenerek taşındı: audit +
kullanıcı/ip parametreleri silindi (narrative bölümü `services/decisions.py`'de).
Kurallar AYNEN: alt-evrak ana evrağa bağlanır, kanonik sıra ×10, tek-belge
sil/geri-al, reorder yalnız sırayı değiştirir.
"""

from __future__ import annotations

import base64
from datetime import date
from typing import Any

from django.db import transaction

from apps.disiplin.models import DisciplineCase, DocumentType, GeneratedDocument
from apps.disiplin.services.common import case_has_student

#: "Verilmedi" nöbetçisi — None'dan ayırt etmek için (kısmi güncelleme).
_UNSET: Any = object()


@transaction.atomic
def log_generated_document(
    case: DisciplineCase,
    *,
    document_type: str,
    title: str,
    generated_on: date,
    document_no: str = "",
    student_id: int | None = None,
    source_label: str = "",
    source_name: str = "",
    notes: str = "",
    page_count: int = 1,
    parent_document_id: int | None = None,
    pdf_content: bytes | None = None,
    stored_filename: str = "",
) -> GeneratedDocument:
    """Üretilen/yazdırılan bir disiplin belgesini kütüğe ve PDF arşivine kaydeder.

    Belge türü geçerli olmalı; öğrenci-özgü belge için `student_id` dosyaya dahil
    olmalı. `parent_document_id` verilirse ALT/destekleyici evraktır → ana evrak
    aynı dosyaya ait olmalı. `page_count` üretilende WeasyPrint'ten otomatik,
    eklenende elle. Rehberlik görüşme formu (no-trace) bu servisle KAYDEDİLMEZ.
    """
    if document_type not in set(DocumentType.values):
        raise ValueError("Geçersiz belge türü.")
    if not (title or "").strip():
        raise ValueError("Belge başlığı (title) zorunludur.")
    if student_id is not None and not case_has_student(case, student_id):
        raise ValueError("Öğrenci bu disiplin dosyasına dahil değil.")
    if (
        parent_document_id is not None
        and not case.generated_documents.filter(
            pk=parent_document_id, parent_document__isnull=True
        ).exists()
    ):
        raise ValueError("Bağlanılacak ana evrak bu dosyada yok (veya kendisi alt evrak).")

    # Dizi pusulası varsayılan sırası = kanonik süreç sırası (lazy import:
    # documents modülü services'i import eder → döngüyü kırmak için içeride).
    from apps.disiplin import documents

    document = GeneratedDocument(
        case=case,
        student_id=student_id,
        document_type=document_type,
        title=title,
        document_no=document_no,
        source_label=source_label,
        source_name=source_name,
        generated_on=generated_on,
        notes=notes,
        page_count=page_count,
        parent_document_id=parent_document_id,
        sort_order=documents.canonical_order(document_type),
        stored_pdf_b64=base64.b64encode(pdf_content).decode("ascii") if pdf_content else "",
        stored_pdf_size=len(pdf_content) if pdf_content else 0,
        stored_filename=stored_filename.strip() if pdf_content else "",
    )
    document.full_clean(exclude=["student"])
    document.save()
    return document


@transaction.atomic
def update_document(
    document: GeneratedDocument,
    *,
    page_count: Any = _UNSET,
    title: Any = _UNSET,
    notes: Any = _UNSET,
    source_label: Any = _UNSET,
    source_name: Any = _UNSET,
) -> GeneratedDocument:
    """Bir kütük kaydının düzenlenebilir metadata'sını günceller (içerik DEĞİL).

    Yalnız sayfa/başlık/açıklama + "kimden" (dizi pusulası). Verilmeyen alan
    değişmez (kısmi). Başlık verilirse boş olamaz.
    """
    updated: list[str] = []
    if page_count is not _UNSET:
        document.page_count = page_count
        updated.append("page_count")
    if title is not _UNSET:
        if not (title or "").strip():
            raise ValueError("Belge başlığı (title) boş olamaz.")
        document.title = title
        updated.append("title")
    if notes is not _UNSET:
        document.notes = notes or ""
        updated.append("notes")
    if source_label is not _UNSET:
        document.source_label = source_label or ""
        updated.append("source_label")
    if source_name is not _UNSET:
        document.source_name = source_name or ""
        updated.append("source_name")
    if updated:
        document.save(update_fields=[*updated, "updated_at"])
    return document


@transaction.atomic
def delete_document(document: GeneratedDocument) -> None:
    """Kütük kaydını soft-delete eder (geri alınabilir).

    Ana evrakın (canlı) alt evrakı varsa silinemez — önce alt evraklar
    silinmeli/taşınmalı (sil/geri-al hep TEK belge → undo temiz).
    """
    if document.parent_document_id is None and document.sub_documents.exists():
        raise ValueError("Bu ana evrakın alt evrakları var; önce onları silin.")
    document.delete()  # soft delete (BaseModel)


@transaction.atomic
def restore_document(document: GeneratedDocument) -> GeneratedDocument:
    """Soft-delete edilmiş bir belgeyi geri yükler.

    Alt evrak ise bağlı olduğu ana evrak silinmiş olamaz (önce onu geri yükleyin).
    """
    if document.deleted_at is None:
        raise ValueError("Belge zaten geri yüklenmiş (silinmemiş).")
    if document.parent_document_id is not None:
        parent = GeneratedDocument.all_objects.filter(pk=document.parent_document_id).first()
        if parent is not None and parent.deleted_at is not None:
            raise ValueError(
                "Önce bağlı olduğu ana evrakı geri yükleyin (alt evrak sahipsiz kalmasın)."
            )
    document.restore()
    return document


@transaction.atomic
def reorder_documents(case: DisciplineCase, *, ordered_ids: list[int]) -> list[GeneratedDocument]:
    """Dizi pusulasındaki belge sırasını yeniden düzenler.

    `ordered_ids` istenen sırada belge id'leridir; hepsi bu dosyaya ait olmalı.
    Her belgeye `sort_order = (sıra+1)*10` atanır (kanonik ×10 aralığıyla uyumlu).
    """
    docs = {d.pk: d for d in case.generated_documents.all()}
    unknown = [i for i in ordered_ids if i not in docs]
    if unknown:
        raise ValueError("Sıralanacak belgeler bu dosyaya ait değil.")

    updated: list[GeneratedDocument] = []
    for index, doc_id in enumerate(ordered_ids):
        doc = docs[doc_id]
        new_order = (index + 1) * 10
        if doc.sort_order != new_order:
            doc.sort_order = new_order
            doc.save(update_fields=["sort_order", "updated_at"])
        updated.append(doc)
    return updated
