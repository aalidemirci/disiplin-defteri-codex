"""Kurul süresi uzatma + tedbir — md. 175, 192/3.

OYS `services/discipline_precautions.py`'den temizlenerek taşındı: audit +
kullanıcı parametreleri silindi; iş günü yüklemi yerel takvimden. Kurallar AYNEN.
"""

from __future__ import annotations

from datetime import date

from django.db import transaction

from apps.disiplin import discipline_periods
from apps.disiplin.models import (
    DisciplineCase,
    DisciplineDeadlineExtension,
    DisciplineEvent,
    DisciplinePrecaution,
    PrecautionStatus,
)
from apps.disiplin.services.common import case_has_student
from apps.okul.services.calendar import is_working_day


@transaction.atomic
def create_extension(
    case: DisciplineCase,
    *,
    requested_days: int,
    reason: str,
    decided_on: date,
    approved_by_principal: bool = False,
    approved_on: date | None = None,
    notes: str = "",
) -> DisciplineDeadlineExtension:
    """Kurul karar süresi uzatması kaydeder (Form-12/13, md. 192/3 — ANCAK BİR KEZ).

    Dosya önce kurula sevk edilmiş olmalı; `original_deadline` = mevcut kurul son
    günü; `new_deadline` = original + `requested_days` iş günü (snapshot). Dosya
    başına ikinci canlı uzatma DB kısıtıyla ve burada açıkça reddedilir.
    """
    from apps.disiplin import selectors

    if requested_days < 1:
        raise ValueError("Uzatma süresi en az 1 iş günü olmalıdır.")
    if not (reason or "").strip():
        raise ValueError("Uzatma gerekçesi (reason) zorunludur (md. 192/3 ara karar).")

    original = selectors.committee_decision_deadline(case)
    if original is None:
        raise ValueError(
            "Dosya kurula sevk edilmemiş; uzatılacak kurul karar süresi yok (md. 192/3)."
        )
    if case.deadline_extensions.exists():
        raise ValueError("Kurul karar süresi yalnızca bir kez uzatılabilir (md. 192/3).")

    new_deadline = discipline_periods.add_working_days(
        original, requested_days, is_working_day=is_working_day
    )
    extension = DisciplineDeadlineExtension(
        case=case,
        requested_days=requested_days,
        reason=reason,
        decided_on=decided_on,
        approved_by_principal=approved_by_principal,
        approved_on=approved_on if approved_by_principal else None,
        original_deadline=original,
        new_deadline=new_deadline,
        notes=notes,
    )
    extension.full_clean()
    extension.save()
    return extension


@transaction.atomic
def approve_extension(
    extension: DisciplineDeadlineExtension, *, approved_on: date
) -> DisciplineDeadlineExtension:
    """Süre uzatmasını müdür onayına bağlar (md. 192/3 — okul müdürünün onayı/Form-13)."""
    extension.approved_by_principal = True
    extension.approved_on = approved_on
    extension.save(update_fields=["approved_by_principal", "approved_on", "updated_at"])
    return extension


@transaction.atomic
def create_precaution(
    case: DisciplineCase,
    *,
    student_id: int,
    start_date: date,
    requested_days: int,
    reason: str = "",
    mne_notified: bool = False,
    event: DisciplineEvent | None = None,
    notes: str = "",
) -> DisciplinePrecaution:
    """Tedbir (geçici uzaklaştırma) kaydeder (md. 175). Öğrenci dosyaya dahil olmalı.

    Süre 1-10 iş günü (md. 175/1); `end_date` ve `process_start_deadline`
    (başlangıç + 3 iş günü, md. 175/2) snapshot yazılır. Öğrenciye o dosyada
    zaten yürürlükte tedbir varsa ValueError. Uzaklaştırma devamsızlıktan
    sayılmaz (md. 175/1).
    """
    if not case_has_student(case, student_id):
        raise ValueError("Öğrenci bu disiplin dosyasına dahil değil.")
    if _active_precaution_exists(case, student_id):
        raise ValueError("Bu öğrenci için dosyada zaten yürürlükte bir tedbir var (md. 175).")

    end_date = discipline_periods.precaution_end_date(
        start_date, requested_days, is_working_day=is_working_day
    )
    process_start_deadline = discipline_periods.precaution_process_start_deadline(
        start_date, is_working_day=is_working_day
    )
    precaution = DisciplinePrecaution(
        case=case,
        student_id=student_id,
        event=event,
        start_date=start_date,
        requested_days=requested_days,
        end_date=end_date,
        process_start_deadline=process_start_deadline,
        mne_notified=mne_notified,
        status=PrecautionStatus.ACTIVE,
        reason=reason,
        notes=notes,
    )
    precaution.full_clean(exclude=["event"])
    precaution.save()
    return precaution


def _active_precaution_exists(case: DisciplineCase, student_id: int) -> bool:
    """Dosyada öğrenciye ait yürürlükte tedbir var mı (servis-içi guard)."""
    return case.precautions.filter(student_id=student_id, status=PrecautionStatus.ACTIVE).exists()


@transaction.atomic
def lift_precaution(
    precaution: DisciplinePrecaution, *, lifted_on: date, expired: bool = False
) -> DisciplinePrecaution:
    """Tedbiri sonlandırır: karara bağlandı (LIFTED) veya kendiliğinden kalktı (EXPIRED).

    md. 175/2: tedbir süresinde işlem sonuçlanmazsa tedbir kendiliğinden kalkar.
    Yalnız yürürlükteki tedbir sonlandırılabilir.
    """
    if precaution.status != PrecautionStatus.ACTIVE:
        raise ValueError("Yalnızca yürürlükteki bir tedbir sonlandırılabilir.")
    precaution.status = PrecautionStatus.EXPIRED if expired else PrecautionStatus.LIFTED
    precaution.lifted_on = lifted_on
    precaution.save(update_fields=["status", "lifted_on", "updated_at"])
    return precaution


@transaction.atomic
def extend_precaution(
    precaution: DisciplinePrecaution,
    *,
    additional_days: int,
    mne_notified: bool = False,
) -> DisciplinePrecaution:
    """Tedbir süresini uzatır (md. 175/2 — milli eğitim müdürü onayıyla iki kez daha).

    Toplam süre md. 175/1 sınırını (10 iş günü) aşamaz; en fazla iki uzatma.
    """
    if precaution.status != PrecautionStatus.ACTIVE:
        raise ValueError("Yalnızca yürürlükteki bir tedbir uzatılabilir.")
    if additional_days < 1:
        raise ValueError("Uzatma süresi en az 1 iş günü olmalıdır.")
    if precaution.extension_count >= discipline_periods.PRECAUTION_EXTENSION_MAX_COUNT:
        raise ValueError("Tedbir en fazla iki kez uzatılabilir (md. 175/2).")
    if precaution.requested_days + additional_days > discipline_periods.PRECAUTION_MAX_WORKING_DAYS:
        raise ValueError("Toplam tedbir süresi 10 iş gününü aşamaz (md. 175/1).")

    precaution.requested_days += additional_days
    precaution.end_date = discipline_periods.precaution_end_date(
        precaution.start_date, precaution.requested_days, is_working_day=is_working_day
    )
    precaution.extension_count += 1
    if mne_notified:
        precaution.mne_notified = True
    precaution.save(
        update_fields=[
            "requested_days",
            "end_date",
            "extension_count",
            "mne_notified",
            "updated_at",
        ]
    )
    return precaution
