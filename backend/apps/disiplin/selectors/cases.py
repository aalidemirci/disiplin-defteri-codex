"""Disiplin dosyası salt-okunur sorguları.

OYS `selectors/discipline_cases.py`'den YALINLAŞTIRILDI: rol/görünürlük
fonksiyonları silindi (tek kullanıcı her dosyayı görür) — `cases_for_user`
yerine `all_cases()` (aşama/arama filtreli).
"""

from __future__ import annotations

from django.db.models import QuerySet

from apps.disiplin.models import (
    DisciplineAttachment,
    DisciplineCase,
    DisciplineDecisionType,
)


def decision_types(*, active_only: bool = True) -> QuerySet[DisciplineDecisionType]:
    """Disiplin karar tipleri (lookup). Varsayılan: yalnızca aktif olanlar."""
    qs = DisciplineDecisionType.objects.all()
    if active_only:
        qs = qs.filter(is_active=True)
    return qs


def get_decision_type(decision_type_id: int) -> DisciplineDecisionType | None:
    """Tek karar tipini id ile getirir — yoksa None."""
    return DisciplineDecisionType.objects.filter(pk=decision_type_id).first()


def get_case(case_id: int) -> DisciplineCase | None:
    """Tek disiplin dosyası (canlı) — ilişkili öğrenci/olay/ek önceden çekilir."""
    return (
        DisciplineCase.objects.filter(pk=case_id)
        .prefetch_related("case_students__student", "events", "attachments")
        .first()
    )


def get_attachment(case: DisciplineCase, attachment_id: int) -> DisciplineAttachment | None:
    """Belirli dosyaya ait tek eki getirir (canlı) — yoksa None."""
    return DisciplineAttachment.objects.filter(case=case, pk=attachment_id).first()


def case_student_ids(case: DisciplineCase) -> set[int]:
    """Dosyadaki öğrenci id'leri."""
    return set(case.case_students.values_list("student_id", flat=True))


def all_cases(*, stage: str = "", search: str = "") -> QuerySet[DisciplineCase]:
    """Tüm (canlı) disiplin dosyaları — aşama ve dosya-no/dilekçe araması filtreli."""
    qs = DisciplineCase.objects.all()
    if stage.strip():
        qs = qs.filter(current_stage=stage.strip())
    if search.strip():
        needle = search.strip()
        qs = qs.filter(case_no__icontains=needle) | qs.filter(petitioner_name__icontains=needle)
    return qs.distinct()


def open_cases_for_close_scan() -> QuerySet[DisciplineCase]:
    """Kapanış taramasına giren açık dosyalar (karar/kurul aşamasını geçmiş).

    "Yaklaşan Süreler" paneli 5. bölümü bunu okur.
    """
    from apps.disiplin.models import CaseStage

    return DisciplineCase.objects.filter(
        closed_at__isnull=True,
        current_stage__in=[CaseStage.DECIDED, CaseStage.COMMITTEE_DONE],
    )


def cases_for_student(student_id: int) -> QuerySet[DisciplineCase]:
    """Belirli öğrencinin disiplin dosyaları (sicil ekranı için)."""
    return DisciplineCase.objects.filter(case_students__student_id=student_id).distinct()
