"""Rollü katılımcı + müdür uyarısı + tekrar tespiti salt-okunur sorguları (md. 157/7, 193).

OYS `selectors/discipline_participants.py`'den uyarlama (issued_by FK'sı yok).
"""

from __future__ import annotations

from dataclasses import dataclass

from django.db.models import QuerySet

from apps.disiplin.models import (
    AppealResult,
    DisciplineAppeal,
    DisciplineCase,
    DisciplineDecision,
    DisciplineParticipant,
    DisciplineWarning,
)


def participants_for_case(case: DisciplineCase) -> QuerySet[DisciplineParticipant]:
    """Bir dosyanın katılımcıları (hakkında işlem yapılan/mağdur/tanık) — rol sırasıyla."""
    return case.participants.select_related("student", "user").all()


def get_participant(case: DisciplineCase, participant_id: int) -> DisciplineParticipant | None:
    """Belirli dosyaya ait tek katılımcı (silinmemiş) — yoksa None."""
    return DisciplineParticipant.objects.filter(case=case, pk=participant_id).first()


def warnings_for_case(case: DisciplineCase) -> QuerySet[DisciplineWarning]:
    """Bir dosyanın müdür uyarıları (en yeni önce)."""
    return case.warnings.select_related("student").all()


def warnings_for_student(student_id: int) -> QuerySet[DisciplineWarning]:
    """Bir öğrencinin tüm müdür uyarıları (md. 157/7) — en yeni önce."""
    return DisciplineWarning.objects.filter(student_id=student_id).select_related("case")


@dataclass
class DisciplineHistory:
    """Bir öğrencinin disiplin geçmişi özeti — triaj önerisi için."""

    student_id: int
    warning_count: int  # daha önce verilmiş müdür uyarısı (md. 157/7)
    penalty_count: int  # bozulmamış resmî ceza kararı (md. 163)
    should_route_to_committee: bool  # tekrar/önceki ceza → kurul (md. 157/7, 166)


def student_discipline_history(
    student_id: int, *, exclude_case_id: int | None = None
) -> DisciplineHistory:
    """Öğrencinin geçmiş uyarı/ceza sayımı + kurula yönlendirme önerisi (md. 157/7, 166).

    `exclude_case_id`: triajı yapılan dosya hariç tutulur. Müdür uyarısı CEZA
    değildir ama tekrar göstergesidir; bozulmuş (OVERTURNED) cezalar geçmiş
    sayılmaz (md. 171).
    """
    warnings = DisciplineWarning.objects.filter(student_id=student_id)
    decisions = DisciplineDecision.objects.filter(student_id=student_id)
    if exclude_case_id is not None:
        warnings = warnings.exclude(case_id=exclude_case_id)
        decisions = decisions.exclude(case_id=exclude_case_id)

    overturned = DisciplineAppeal.objects.filter(result=AppealResult.OVERTURNED).values_list(
        "decision_id", flat=True
    )
    penalty_count = decisions.exclude(pk__in=overturned).count()
    warning_count = warnings.count()
    return DisciplineHistory(
        student_id=student_id,
        warning_count=warning_count,
        penalty_count=penalty_count,
        should_route_to_committee=(warning_count > 0 or penalty_count > 0),
    )


def should_route_to_committee(student_id: int, *, exclude_case_id: int | None = None) -> bool:
    """Öğrenci triajda kurula yönlendirilmeli mi (daha önce uyarı/ceza var mı)?

    md. 157/7: ilk kınamalık + ceza yoksa müdür uyarısı (Dal A); aksi → kurul
    (Dal B). md. 166: tekrar → kurul. Yalnızca öneridir; nihai kararı müdür verir.
    """
    return student_discipline_history(
        student_id, exclude_case_id=exclude_case_id
    ).should_route_to_committee


def accused_student_ids(case: DisciplineCase) -> list[int]:
    """Dosyadaki suçlanan öğrenci id'leri (triaj önerisi için — through tablodan)."""
    return list(case.case_students.values_list("student_id", flat=True))
