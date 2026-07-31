"""Evrak kütüğü salt-okunur sorguları.

OYS `selectors/document_log.py`'den uyarlama (generated_by FK'sı yok).
"""

from __future__ import annotations

from django.db.models import Prefetch, QuerySet

from apps.disiplin.models import (
    DisciplineCase,
    GeneratedDocument,
)

# =============================================================================
# Disiplin Evrak Kütüğü (Tur 76, Faz C) — üretilen belge zaman çizelgesi
# =============================================================================


def documents_for_case(case: DisciplineCase) -> QuerySet[GeneratedDocument]:
    """Dosyada üretilen belgeler (en yeni önce) — öğrenci/üreten önceden çekilir."""
    return case.generated_documents.defer("stored_pdf_b64").select_related("student").all()


def document_timeline(case: DisciplineCase) -> list[GeneratedDocument]:
    """Dosyanın evrak dizisi: yalnız ANA evraklar (parent_document boş), dizi sırasına
    (sort_order) göre ARTAN — varsayılan kanonik süreç sırası, arayüzden yeniden
    düzenlenebilir (Tur 103). Alt/destekleyici evraklar `sub_documents` ile prefetch
    edilir (Tur 104); eşitlikte üretim tarihi/oluşturma sırası (kararlı)."""
    return list(
        case.generated_documents.filter(parent_document__isnull=True)
        .defer("stored_pdf_b64")
        .select_related("student")
        .prefetch_related(
            Prefetch(
                "sub_documents",
                queryset=GeneratedDocument.objects.defer("stored_pdf_b64").select_related(
                    "student"
                ),
            )
        )
        .order_by("sort_order", "generated_on", "created_at")
    )


def get_document(case: DisciplineCase, document_id: int) -> GeneratedDocument | None:
    """Belirli dosyaya ait tek belge kaydı (silinmemiş) — yoksa None."""
    return (
        GeneratedDocument.objects.filter(case=case, pk=document_id).defer("stored_pdf_b64").first()
    )


def get_any_document(case: DisciplineCase, document_id: int) -> GeneratedDocument | None:
    """Belirli dosyaya ait tek belge — SİLİNMİŞLER DAHİL (geri yükleme için; Tur 150) — yoksa None."""
    return GeneratedDocument.all_objects.filter(case=case, pk=document_id).first()


def deleted_documents(case: DisciplineCase) -> list[GeneratedDocument]:
    """Dosyanın SİLİNMİŞ belgeleri (çöp kutusu; Tur 150) — en son silinen önce."""
    return list(
        GeneratedDocument.all_objects.filter(case=case, deleted_at__isnull=False)
        .defer("stored_pdf_b64")
        .select_related("student")
        .order_by("-deleted_at")
    )


def documents_for_student(student_id: int) -> QuerySet[GeneratedDocument]:
    """Bir öğrenciye özgü üretilmiş belgeler (sicil ekranı için) — en yeni önce."""
    return (
        GeneratedDocument.objects.filter(student_id=student_id)
        .defer("stored_pdf_b64")
        .select_related("case")
    )
