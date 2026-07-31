"""Kurul süresi + uzatma + tedbir salt-okunur sorguları (md. 175, 192/3).

OYS `selectors/discipline_precautions.py`'den uyarlama. ÖNEMLİ SQLite farkı:
JSONField `__contains` sorgusu SQLite'ta DESTEKLENMEZ (Django kısıtı) — OYS'nin
`principal_decisions__contains=[...]` filtreleri Python tarafında değerlendirilir
(yerel ölçekte dosya sayısı küçük; davranış birebir).
"""

from __future__ import annotations

from datetime import date

from django.db.models import Q, QuerySet

from apps.disiplin import discipline_periods
from apps.disiplin.models import (
    CaseStage,
    DisciplineCase,
    DisciplineDeadlineExtension,
    DisciplineEvent,
    DisciplinePrecaution,
    PrecautionStatus,
    PrincipalDecision,
)
from apps.okul.services.calendar import is_working_day


def committee_referred_on(case: DisciplineCase) -> date | None:
    """Dosyanın kurula sevk edildiği gün (md. 192/3 "kurula gelişi") — yoksa None.

    Kurula sevk = müdürün DISCIPLINE_COMMITTEE içeren DECIDED kararı; en erken
    böyle olayın `event_date`'i alınır. (JSON contains SQLite'ta yok — Python.)
    """
    events: QuerySet[DisciplineEvent] = case.events.filter(stage=CaseStage.DECIDED).order_by(
        "event_date", "recorded_at"
    )
    for event in events:
        if PrincipalDecision.DISCIPLINE_COMMITTEE in (event.principal_decisions or []):
            return event.event_date
    return None


def committee_decision_deadline(case: DisciplineCase) -> date | None:
    """Kurul karar son günü (md. 192/3) — kurula geliş + 10 iş günü; uzatma varsa snapshot.

    Onaylanmış (müdür onaylı) bir süre uzatması varsa onun `new_deadline`'ı esas
    alınır. Dosya kurula sevk edilmemişse None.
    """
    referred = committee_referred_on(case)
    if referred is None:
        return None
    ext = (
        case.deadline_extensions.filter(approved_by_principal=True).order_by("-decided_on").first()
    )
    if ext is not None:
        return ext.new_deadline
    return discipline_periods.committee_decision_deadline(referred, is_working_day=is_working_day)


def extensions_for_case(case: DisciplineCase) -> QuerySet[DisciplineDeadlineExtension]:
    """Dosyanın kurul süre uzatmaları (en yeni önce)."""
    return case.deadline_extensions.all()


def get_extension(case: DisciplineCase, extension_id: int) -> DisciplineDeadlineExtension | None:
    """Belirli dosyaya ait tek süre uzatması (silinmemiş) — yoksa None."""
    return DisciplineDeadlineExtension.objects.filter(case=case, pk=extension_id).first()


def precautions_for_case(case: DisciplineCase) -> QuerySet[DisciplinePrecaution]:
    """Dosyanın tedbir kayıtları (md. 175) — öğrenci önceden çekilir, en yeni önce."""
    return case.precautions.select_related("student").all()


def precautions_for_student(student_id: int) -> QuerySet[DisciplinePrecaution]:
    """Bir öğrencinin tüm tedbir kayıtları (sicil ekranı için) — en yeni önce."""
    return DisciplinePrecaution.objects.filter(student_id=student_id).select_related("case")


def get_precaution(case: DisciplineCase, precaution_id: int) -> DisciplinePrecaution | None:
    """Belirli dosyaya ait tek tedbir (silinmemiş) — yoksa None."""
    return DisciplinePrecaution.objects.filter(case=case, pk=precaution_id).first()


def active_precaution(case: DisciplineCase, student_id: int) -> DisciplinePrecaution | None:
    """Dosyada öğrenciye ait YÜRÜRLÜKTEKİ tedbir — yoksa None (alive-unique gereği tek)."""
    return case.precautions.filter(student_id=student_id, status=PrecautionStatus.ACTIVE).first()


def cases_awaiting_committee_decision(through_date: date) -> list[tuple[DisciplineCase, date]]:
    """Kurul karar süresi `through_date`'e kadar dolan/dolacak açık dosyalar + son günleri.

    Kurula sevk edilmiş, henüz kurul kararı verilmemiş (COMMITTEE_DONE/CLOSED
    değil) ve kapatılmamış dosyalar taranır; her biri için deadline hesaplanır
    (uzatma dahil). "Yaklaşan Süreler" paneli bunu okur. (case, deadline) döner.
    """
    open_cases = (
        DisciplineCase.objects.filter(closed_at__isnull=True, events__stage=CaseStage.DECIDED)
        .exclude(current_stage__in=[CaseStage.COMMITTEE_DONE, CaseStage.CLOSED])
        .distinct()
    )
    result: list[tuple[DisciplineCase, date]] = []
    for case in open_cases:
        # Sevk kontrolü Python'da (JSON contains SQLite'ta yok).
        deadline = committee_decision_deadline(case)
        if deadline is not None and deadline <= through_date:
            result.append((case, deadline))
    return result


def precautions_awaiting_deadline(through_date: date) -> QuerySet[DisciplinePrecaution]:
    """Süresi (bitiş veya işleme-başlama) `through_date`'e kadar dolan yürürlükteki tedbirler.

    md. 175/2: tedbiri izleyen 3 iş günü içinde işleme başlanmalı; tedbir 10 iş
    gününü geçemez. En erken gün önce.
    """
    return (
        DisciplinePrecaution.objects.filter(status=PrecautionStatus.ACTIVE)
        .filter(Q(end_date__lte=through_date) | Q(process_start_deadline__lte=through_date))
        .select_related("case", "student")
        .order_by("end_date")
    )
