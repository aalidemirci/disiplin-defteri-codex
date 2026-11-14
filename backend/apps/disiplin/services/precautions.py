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
from apps.disiplin.services.common import assert_not_future, case_has_student
from apps.okul.services.calendar import is_working_day


def _assert_case_open(case: DisciplineCase, what: str) -> None:
    """Kapalı dosyada tedbir ve kurul süre uzatması işlemi yapılmaz.

    Tedbir (md. 175) "kovuşturmanın tamamlanmasını beklemeden" alınan acele bir
    önlemdir; kurul süre uzatması (md. 192/3) karar bekleyen dosya içindir — ikisi de
    kapanmış dosyada anlamsızdır ve süre panelinde yanlış alarm üretir. Yürürlükte
    kalmış tedbirin SONLANDIRILMASI (`lift_precaution`) bu kilide tabi değildir.
    """
    if case.closed_at is not None:
        raise ValueError(
            f"Dosya kapalı: {what}. Gerekiyorsa önce dosyayı yeniden açın (aşama geri alma)."
        )


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

    _assert_case_open(case, "kurul süre uzatması eklenemez")
    if requested_days < 1:
        raise ValueError("Uzatma süresi en az 1 iş günü olmalıdır.")
    assert_not_future(decided_on, "Ara karar tarihi")
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
    """Süre uzatmasını müdür onayına bağlar (md. 192/3 — okul müdürünün onayı/Form-13).

    Onay ara karardan SONRA gelir (md. 192/3 "alınacak ara karar ve okul müdürünün
    onayıyla"); onaylanmış kayıt yeniden onaylanamaz (ikinci çağrı onay tarihini
    sessizce değiştiriyordu).
    """
    _assert_case_open(extension.case, "süre uzatması onaylanamaz")
    if extension.approved_by_principal:
        raise ValueError("Bu süre uzatması zaten onaylanmış; onay tarihi değiştirilemez.")
    assert_not_future(approved_on, "Onay tarihi")
    if approved_on < extension.decided_on:
        raise ValueError(
            "Müdür onayı ara karar tarihinden önce olamaz "
            f"(ara karar {extension.decided_on:%d.%m.%Y})."
        )
    extension.approved_by_principal = True
    extension.approved_on = approved_on
    extension.save(update_fields=["approved_by_principal", "approved_on", "updated_at"])
    return extension


@transaction.atomic
def delete_extension(extension: DisciplineDeadlineExtension) -> None:
    """Yanlış girilen ya da müdürün onaylamadığı süre uzatmasını siler (soft delete).

    Yalnız ONAYSIZ kayıt silinebilir: onaysız uzatma son günü değiştirmez (md. 192/3
    müdür onayı şarttır), dolayısıyla silinmesi hiçbir süreyi etkilemez. Onaylanmış
    uzatma kurul karar süresini fiilen uzatmıştır — silinemez. "Ancak bir kez" kuralı
    canlı kayda bakar; silinen kaydın yerine doğrusu girilebilir (§7.6 tek yönlü kapan).
    """
    if extension.approved_by_principal:
        raise ValueError(
            "Müdürün onayladığı süre uzatması silinemez: kurul karar süresi bu onayla "
            "uzamıştır (md. 192/3). Yalnız onaylanmamış kayıt silinebilir."
        )
    extension.delete()  # soft delete


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
    _assert_case_open(case, "tedbir eklenemez")
    if not case_has_student(case, student_id):
        raise ValueError("Öğrenci bu disiplin dosyasına dahil değil.")
    # Başlangıç tarihi TATİL GÜNÜ olabilir (reddedilmez): modelde ayrı bir "karar tarihi"
    # yoktur, başlangıç = tedbir kararının alındığı gündür ve md. 175/2 "tedbir kararının
    # alınmasını izleyen en geç üç iş günü" bu günden sayılır. Karar hafta sonu/tatilde
    # alınabilir (ör. pansiyonlu okul); ilk iş gününe ötelemek 175/2 son gününü bir gün
    # geç hesaplatırdı. Kullanıcı kararı, 14.11.2026 — S4: tatil günü başlangıcında
    # tedbirin iş günleri (md. 175/1) izleyen İLK İŞ GÜNÜNDEN sayılır
    # (`discipline_periods.precaution_end_date`); `start_date` karar günü olarak kalır.
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
    if lifted_on < precaution.start_date:
        raise ValueError(
            "Sonlanma tarihi tedbirin başlangıcından önce olamaz "
            f"(başlangıç {precaution.start_date:%d.%m.%Y})."
        )
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

    Her uzatma AYRI bir süredir: en fazla 10 iş günü (md. 175/1 sınırı her tedbir
    kararı için geçerli), en fazla iki uzatma. Uzatma mevcut bitiş gününden sonra
    başlar: ek günler bitişi İZLEYEN iş günlerinden sayılır, tatil günü hiç sayılmaz
    (kullanıcı kararı, 14.11.2026 — S4 ile aynı kural). Haklı ve zorlayıcı sebeplerin devamı + Millî Eğitim Müdürünün onayı
    şarttır (`mne_notified=True` bu uçta onayın alındığını kaydeder).
    """
    _assert_case_open(precaution.case, "tedbir uzatılamaz")
    if precaution.status != PrecautionStatus.ACTIVE:
        raise ValueError("Yalnızca yürürlükteki bir tedbir uzatılabilir.")
    if not (1 <= additional_days <= discipline_periods.PRECAUTION_MAX_WORKING_DAYS):
        raise ValueError(
            "Her uzatma 1-"
            f"{discipline_periods.PRECAUTION_MAX_WORKING_DAYS} iş günü olmalıdır (md. 175/1-2)."
        )
    if precaution.extension_count >= discipline_periods.PRECAUTION_EXTENSION_MAX_COUNT:
        raise ValueError("Tedbir en fazla iki kez uzatılabilir (md. 175/2).")
    if not mne_notified:
        raise ValueError(
            "Tedbirin uzatılması Millî Eğitim Müdürünün onayına bağlıdır (md. 175/2); "
            "onay alındığını işaretleyin."
        )

    precaution.requested_days += additional_days
    precaution.end_date = discipline_periods.add_working_days(
        precaution.end_date, additional_days, is_working_day=is_working_day
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
