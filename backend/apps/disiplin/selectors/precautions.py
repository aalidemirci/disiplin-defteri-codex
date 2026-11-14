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
    DisciplinePrecaution,
    PrecautionStatus,
    PrincipalDecision,
)
from apps.disiplin.selectors.cases import latest_principal_decision_event
from apps.okul.services.calendar import is_working_day

#: Müdür kararından (DECIDED) ÖNCEKİ aşamalar — bu aşamadaki dosya kurula sevkli değildir.
_PRE_DECISION_STAGES: frozenset[str] = frozenset(
    {CaseStage.PETITION, CaseStage.GUIDANCE_REFERRED, CaseStage.GUIDANCE_RETURNED}
)


def committee_referred_on(case: DisciplineCase) -> date | None:
    """Dosyanın kurula sevk edildiği gün (md. 192/3 "kurula gelişi") — yoksa None.

    Kurula sevk = müdürün DISCIPLINE_COMMITTEE içeren DECIDED kararı. Aşama geri
    alınıp müdür kararı yeniden verilmişse YALNIZ SON müdür kararı geçerlidir
    (kullanıcı kararı 27.09.2026): konu kurula fiilen son sevkte gelir; son karar
    sevk değilse (ör. yazılı uyarıya dönüldüyse) dosya sevkli sayılmaz.
    (JSON contains SQLite'ta yok — Python.)

    GERİ ALINMIŞ SEVK SAYILMAZ: `revert_stage` aşama olaylarını silmez; dosyanın
    GÜNCEL aşaması müdür kararı öncesindeyse (dilekçe/rehberlik) eski sevk olayı
    hukuken yoktur — kurul süresi işlemez, ceza kararı girilemez (md. 163/2).
    """
    if case.current_stage in _PRE_DECISION_STAGES:
        return None
    # "Son" = en son KAYDEDİLEN karar (olay tarihi sırası değil) — tek ortak ölçüt.
    latest = latest_principal_decision_event(case)
    if latest is not None and PrincipalDecision.DISCIPLINE_COMMITTEE in (
        latest.principal_decisions or []
    ):
        return latest.event_date
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

    Bütün suçlananlar hakkında (canlı) karar girilmiş dosya da listelenmez: kurul
    "karara bağlamıştır" (md. 192/3); COMMITTEE_DONE olayı henüz eklenmemiş diye
    süresinde verilmiş karar için GEÇTİ alarmı yanıltıcıdır.
    """
    from apps.disiplin.models import DisciplineDecision

    open_cases = (
        DisciplineCase.objects.filter(closed_at__isnull=True, events__stage=CaseStage.DECIDED)
        .exclude(current_stage__in=[CaseStage.COMMITTEE_DONE, CaseStage.CLOSED])
        .distinct()
    )
    result: list[tuple[DisciplineCase, date]] = []
    for case in open_cases:
        accused = set(case.case_students.values_list("student_id", flat=True))
        decided = set(
            DisciplineDecision.objects.filter(case=case).values_list("student_id", flat=True)
        )
        if accused and accused <= decided:
            continue
        # Sevk kontrolü Python'da (JSON contains SQLite'ta yok).
        deadline = committee_decision_deadline(case)
        if deadline is not None and deadline <= through_date:
            result.append((case, deadline))
    return result


def precautions_awaiting_deadline(through_date: date) -> QuerySet[DisciplinePrecaution]:
    """Süresi (bitiş veya işleme-başlama) `through_date`'e kadar dolan yürürlükteki tedbirler.

    md. 175/2: tedbiri izleyen 3 iş günü içinde işleme başlanmalı; tedbir 10 iş
    gününü geçemez. En erken gün önce. Kapalı dosyanın tedbiri izlenmez (kapanışta
    sonlandırılmamış tedbir panelde kalıcı GEÇTİ satırı üretiyordu).
    """
    return (
        DisciplinePrecaution.objects.filter(
            status=PrecautionStatus.ACTIVE, case__closed_at__isnull=True
        )
        .filter(Q(end_date__lte=through_date) | Q(process_start_deadline__lte=through_date))
        .select_related("case", "student")
        .order_by("end_date")
    )
