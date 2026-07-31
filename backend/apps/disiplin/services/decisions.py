"""Disiplin kararı + yasal süreler + itiraz — md. 163-175.

OYS `services/discipline_decisions.py`'den temizlenerek taşındı: audit +
kullanıcı/ip parametreleri silindi; iş günü yüklemi yerel takvimden
(`apps.okul.services.calendar.is_working_day`). İş kuralları AYNEN.
"""

from __future__ import annotations

import re
from datetime import date

from django.db import transaction
from django.utils import timezone

from apps.disiplin import discipline_periods
from apps.disiplin.models import (
    AppealFiledByRole,
    AppealResult,
    DecisionApprovalStatus,
    DisciplineAppeal,
    DisciplineCase,
    DisciplineDecision,
    DisciplineEvent,
    DisciplineMeeting,
    PenaltyType,
)
from apps.disiplin.services.common import case_has_student
from apps.okul.services.calendar import is_working_day


def generate_decision_no(decision_date: date) -> str:
    """Ders yılı içinde sıradaki kurul karar numarasını üretir.

    Biçim ``2025-2026/0001``'dir. Silinmiş kararlar da numarayı tüketir; böylece
    resmî karar defterinde daha önce kullanılmış bir numara yeniden verilmez.
    """
    from apps.okul.models import SchoolYear

    year = (
        SchoolYear.objects.filter(
            start_date__lte=decision_date,
            end_date__gte=decision_date,
        ).first()
        or SchoolYear.objects.filter(is_active=True).first()
    )
    prefix = year.name if year is not None else str(decision_date.year)
    pattern = re.compile(rf"^{re.escape(prefix)}/(\d{{4}})$")
    highest = 0
    for value in DisciplineDecision.all_objects.values_list("decision_no", flat=True):
        match = pattern.match(value or "")
        if match:
            highest = max(highest, int(match.group(1)))
    return f"{prefix}/{highest + 1:04d}"


def ensure_decision_no(decision: DisciplineDecision) -> DisciplineDecision:
    """Eski/boş bir karara ilk belge üretiminde kalıcı karar numarası verir."""
    if not decision.decision_no.strip():
        decision.decision_no = generate_decision_no(decision.decision_date)
        decision.save(update_fields=["decision_no", "updated_at"])
    return decision


def _compile_prior_penalties(student_id: int, exclude_case_id: int) -> str:
    """EK-1 'şimdiye kadar aldığı cezalar' — öğrencinin önceki (canlı) kararlarından derler."""
    prior = (
        DisciplineDecision.objects.filter(student_id=student_id)
        .exclude(case_id=exclude_case_id)
        .order_by("decision_date")
    )
    lines = [
        f"{d.decision_date:%d.%m.%Y} — {d.get_penalty_type_display()}"
        + (f" (karar no {d.decision_no})" if d.decision_no else "")
        for d in prior
    ]
    return "\n".join(lines)


@transaction.atomic
def record_decision(
    case: DisciplineCase,
    *,
    student_id: int,
    penalty_type: str,
    decision_date: date,
    suspension_days: int | None = None,
    enforcement_start_date: date | None = None,
    statute_ref: str = "",
    penalty_detail: str = "",
    decision_no: str = "",
    event: DisciplineEvent | None = None,
    meeting: DisciplineMeeting | None = None,
    notes: str = "",
) -> DisciplineDecision:
    """Bir dosyadaki öğrenci için resmî disiplin kararı (ceza) kaydeder (md. 163).

    Davranış puanı indirimi (md. 170) ve onay mercii (md. 163/2) cezadan otomatik
    türetilir. Öğrenci dosyaya dahil olmalı; dosya başına öğrenciye tek (silinmemiş)
    karar (ikinci kez ValueError).
    """
    if penalty_type not in set(PenaltyType.values):
        raise ValueError("Geçersiz ceza türü.")
    if not case_has_student(case, student_id):
        raise ValueError("Öğrenci bu disiplin dosyasına dahil değil.")
    if DisciplineDecision.objects.filter(case=case, student_id=student_id).exists():
        raise ValueError(
            "Bu öğrenci için bu dosyada zaten bir karar var (düzeltme için mevcut "
            "karar güncellenir/silinir)."
        )

    decision = DisciplineDecision(
        case=case,
        student_id=student_id,
        event=event,
        meeting=meeting,
        penalty_type=penalty_type,
        statute_ref=statute_ref,
        penalty_detail=penalty_detail,
        decision_no=decision_no.strip() or generate_decision_no(decision_date),
        decision_date=decision_date,
        suspension_days=suspension_days,
        enforcement_start_date=enforcement_start_date,
        behavior_point_deduction=discipline_periods.deduction_for(penalty_type),
        approval_authority=discipline_periods.approval_authority_for(penalty_type),
        approval_status=DecisionApprovalStatus.PENDING,
        prior_penalties_summary=_compile_prior_penalties(student_id, case.pk),
        notes=notes,
    )
    decision.full_clean(exclude=["event", "meeting"])
    decision.save()
    return decision


def _assert_decision_editable(decision: DisciplineDecision) -> None:
    """Karar düzenleme/silme koruması.

    Yalnız BEKLEMEDEKİ (PENDING) + tebliğ edilmemiş + itirazsız karar
    düzenlenebilir/silinebilir. Onaylanmış/tebliğ edilmiş karar resmî süreçtir;
    düzeltmesi kurula iade (md. 197) / itiraz kanalındandır.
    """
    if decision.approval_status != DecisionApprovalStatus.PENDING:
        raise ValueError(
            "Yalnız beklemedeki (onaylanmamış) karar düzenlenebilir/silinebilir; onaylanmış "
            "karar için kurula iade (md. 197) veya itiraz kullanın."
        )
    if decision.notified_at is not None:
        raise ValueError("Tebliğ edilmiş karar düzenlenemez/silinemez.")
    if decision.appeals.exists():
        raise ValueError("İtirazı olan karar düzenlenemez/silinemez.")


@transaction.atomic
def update_decision(
    decision: DisciplineDecision,
    *,
    penalty_type: str,
    decision_date: date,
    suspension_days: int | None = None,
    enforcement_start_date: date | None = None,
    statute_ref: str = "",
    penalty_detail: str = "",
    decision_no: str = "",
    notes: str = "",
) -> DisciplineDecision:
    """BEKLEMEDEKİ bir kararın çekirdek alanlarını düzenler (md. 163).

    Ceza türü değişirse davranış puanı indirimi + onay mercii yeniden türetilir.
    Uzaklaştırma alanları yalnız kısa süreli uzaklaştırmada saklanır.
    """
    _assert_decision_editable(decision)
    if penalty_type not in set(PenaltyType.values):
        raise ValueError("Geçersiz ceza türü.")

    is_suspension = penalty_type == PenaltyType.SHORT_TERM_SUSPENSION
    decision.penalty_type = penalty_type
    decision.decision_date = decision_date
    decision.suspension_days = suspension_days if is_suspension else None
    decision.enforcement_start_date = enforcement_start_date if is_suspension else None
    decision.statute_ref = statute_ref
    decision.penalty_detail = penalty_detail
    decision.decision_no = decision_no
    decision.notes = notes
    decision.behavior_point_deduction = discipline_periods.deduction_for(penalty_type)
    decision.approval_authority = discipline_periods.approval_authority_for(penalty_type)
    decision.full_clean(exclude=["event", "meeting"])
    decision.save()
    return decision


@transaction.atomic
def delete_decision(decision: DisciplineDecision) -> None:
    """BEKLEMEDEKİ bir kararı soft-delete eder (geri alınabilir)."""
    _assert_decision_editable(decision)
    decision.delete()  # soft delete (BaseModel)


@transaction.atomic
def restore_decision(decision: DisciplineDecision) -> DisciplineDecision:
    """Soft-delete edilmiş bir kararı geri yükler.

    Aynı öğrenci için bu dosyada zaten CANLI bir karar varsa reddedilir.
    """
    if decision.deleted_at is None:
        raise ValueError("Karar zaten geri yüklenmiş (silinmemiş).")
    if DisciplineDecision.objects.filter(
        case_id=decision.case_id, student_id=decision.student_id
    ).exists():
        raise ValueError("Bu öğrenci için bu dosyada zaten (canlı) bir karar var; geri yüklenemez.")
    decision.restore()
    return decision


@transaction.atomic
def set_decision_approval(
    decision: DisciplineDecision,
    *,
    approval_status: str,
    approved_on: date | None = None,
) -> DisciplineDecision:
    """Kararın onay durumunu günceller (md. 163/2 — merci sistem dışı, manuel giriş).

    md. 197: müdür yalnız onaylar (APPROVED) ya da beklemede bırakır (PENDING);
    reddetme yoktur. APPROVED + kınama/kısa uzaklaştırma → uygulanır (md. 172).
    """
    if approval_status not in {DecisionApprovalStatus.PENDING, DecisionApprovalStatus.APPROVED}:
        raise ValueError("Müdür kararı yalnız onaylayabilir veya beklemede bırakabilir (md. 197).")
    decision.approval_status = approval_status
    decision.approved_at = approved_on
    fields = ["approval_status", "approved_at", "updated_at"]
    if approval_status == DecisionApprovalStatus.APPROVED and decision.penalty_type in (
        PenaltyType.REPRIMAND,
        PenaltyType.SHORT_TERM_SUSPENSION,
    ):
        decision.is_enforced = True
        fields.append("is_enforced")
    decision.save(update_fields=fields)
    return decision


@transaction.atomic
def record_principal_review(
    decision: DisciplineDecision,
    *,
    action: str,
    reason: str,
    decided_on: date,
) -> DisciplineDecision:
    """md. 197 — müdürün kurul kararını uygun bulmaması (reddetme DEĞİL).

    `action="RETURN"`: kararı gerekçeyle kurula iade eder. `action="REFER"`:
    kurul ısrar edince ilçe kuruluna gönderir — yalnız önce iade edilmiş karar.
    """
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("Kurula iade / ilçeye sevk için gerekçe zorunludur (md. 197).")
    if action == "RETURN":
        new_status = DecisionApprovalStatus.RETURNED_TO_COMMITTEE
    elif action == "REFER":
        if decision.approval_status != DecisionApprovalStatus.RETURNED_TO_COMMITTEE:
            raise ValueError(
                "İlçe kuruluna gönderme yalnız önce kurula iade edilmiş kararda yapılabilir "
                "(md. 197 — kurul ısrarı)."
            )
        new_status = DecisionApprovalStatus.REFERRED_TO_DISTRICT
    else:
        raise ValueError("Geçersiz işlem; 'RETURN' veya 'REFER' olmalı.")

    decision.approval_status = new_status
    decision.return_reason = reason
    decision.returned_at = decided_on
    decision.approved_at = None
    decision.is_enforced = False
    decision.save(
        update_fields=[
            "approval_status",
            "return_reason",
            "returned_at",
            "approved_at",
            "is_enforced",
            "updated_at",
        ]
    )
    return decision


@transaction.atomic
def notify_decision(
    decision: DisciplineDecision,
    *,
    notified_on: date,
    notification_method: str = "",
) -> DisciplineDecision:
    """Kararın tebliğini kaydeder ve itiraz son gününü hesaplar (md. 169/3, 169/5).

    `appeal_deadline` = tebliğ + 5 iş günü (snapshot; yerel tatil takvimi dahil).
    """
    decision.notified_at = notified_on
    decision.notification_method = notification_method
    decision.appeal_deadline = discipline_periods.appeal_deadline(
        notified_on, is_working_day=is_working_day
    )
    decision.save(
        update_fields=["notified_at", "notification_method", "appeal_deadline", "updated_at"]
    )
    return decision


@transaction.atomic
def confirm_e_school_entry(
    decision: DisciplineDecision,
    *,
    processed_on: date,
) -> DisciplineDecision:
    """Kesinleşen cezanın e-Okul'a işlendiğini kaydeder.

    Ceza kesinleşmeden veya ceza verilmesine yer olmadığı kararında bu onay
    verilemez. Böylece arayüzdeki uyarı yalnız metin değil, sunucu tarafında da
    uygulanan bir süreç kuralıdır.
    """
    from apps.disiplin import selectors

    if decision.penalty_type == PenaltyType.NO_PENALTY:
        raise ValueError("Ceza verilmesine yer olmadığı kararı e-Okul'a işlenmez.")
    final, reason = selectors.decision_is_final(decision)
    if not final:
        raise ValueError(f"Ceza kesinleşmeden e-Okul onayı verilemez: {reason}.")
    if processed_on > timezone.localdate():
        raise ValueError("e-Okul'a işlenme tarihi gelecekte olamaz.")
    result_dates = [
        appeal.resulted_on for appeal in decision.appeals.all() if appeal.resulted_on is not None
    ]
    if result_dates:
        if processed_on < max(result_dates):
            raise ValueError("e-Okul'a işlenme tarihi itirazın sonuç tarihinden önce olamaz.")
    elif decision.appeal_deadline is not None and processed_on <= decision.appeal_deadline:
        raise ValueError("e-Okul'a işlenme tarihi itiraz süresinin bitiminden sonra olmalıdır.")
    decision.e_school_processed_on = processed_on
    decision.save(update_fields=["e_school_processed_on", "updated_at"])
    return decision


@transaction.atomic
def file_appeal(
    decision: DisciplineDecision,
    *,
    filed_on: date,
    filed_by_role: str,
    filed_by_name: str = "",
) -> DisciplineAppeal:
    """Karara itiraz kaydeder (md. 169/3). Tebliğ yapılmış olmalı.

    `within_deadline` = başvuru ≤ itiraz son günü. Okul değiştirmede süresi
    içinde itiraz → uygulama bekletilir (md. 172/2-ç → is_enforced=False).
    """
    if filed_by_role not in set(AppealFiledByRole.values):
        raise ValueError("Geçersiz itiraz eden rolü.")
    if decision.notified_at is None or decision.appeal_deadline is None:
        raise ValueError("İtiraz için karar önce tebliğ edilmelidir (md. 169/3).")

    within = filed_on <= decision.appeal_deadline
    appeal = DisciplineAppeal(
        decision=decision,
        filed_on=filed_on,
        filed_by_role=filed_by_role,
        filed_by_name=filed_by_name,
        within_deadline=within,
        appeal_authority=discipline_periods.appeal_authority_for(decision.penalty_type),
        forward_deadline=discipline_periods.forward_deadline(
            filed_on, is_working_day=is_working_day
        ),
        result=AppealResult.PENDING,
    )
    appeal.full_clean()
    appeal.save()

    # md. 172/2-ç: okul değiştirmede süresi içinde itiraz → karar verilene kadar uygulanmaz.
    if within and decision.penalty_type == PenaltyType.SCHOOL_CHANGE and decision.is_enforced:
        decision.is_enforced = False
        decision.save(update_fields=["is_enforced", "updated_at"])

    return appeal


@transaction.atomic
def forward_appeal(appeal: DisciplineAppeal, *, forwarded_on: date) -> DisciplineAppeal:
    """İtirazın üst kurula sevkini kaydeder (md. 169/3 — en geç 5 iş günü)."""
    appeal.forwarded_on = forwarded_on
    appeal.save(update_fields=["forwarded_on", "updated_at"])
    return appeal


@transaction.atomic
def resolve_appeal(
    appeal: DisciplineAppeal,
    *,
    result: str,
    resulted_on: date,
    result_notes: str = "",
) -> DisciplineAppeal:
    """İtiraz sonucunu kaydeder (md. 169/4 — sonuç kesindir).

    OVERTURNED (bozuldu) → ceza kaldırılır: karar REJECTED + uygulama kalkar;
    davranış puanı iadesi selector tarafında bozulmuş kararlar hariç tutularak
    sağlanır (md. 171).
    """
    if result not in set(AppealResult.values):
        raise ValueError("Geçersiz itiraz sonucu.")
    appeal.result = result
    appeal.resulted_on = resulted_on
    appeal.result_notes = result_notes
    appeal.save(update_fields=["result", "resulted_on", "result_notes", "updated_at"])

    if result == AppealResult.OVERTURNED:
        decision = appeal.decision
        decision.approval_status = DecisionApprovalStatus.REJECTED
        decision.is_enforced = False
        decision.save(update_fields=["approval_status", "is_enforced", "updated_at"])

    return appeal


# EK-1 anlatı + öğrenci-bağlam alanları — karar sonrası da (dosya kapanana dek)
# güncellenebilir (OYS decision_narrative ucu paritesi).
NARRATIVE_FIELDS: tuple[str, ...] = (
    "accused_statement_summary",
    "witness_statement_summary",
    "other_evidence",
    "mitigating_aggravating",
    "committee_opinion",
    "psychosocial_summary",
    "boarding_status",
    "academic_standing",
    "health_status",
    "family_economic_status",
    "lives_with_family",
    "parents_alive",
    "parents_biological",
    "studies_near_family",
    "upbringing_environment",
    "family_residence_area",
    "incident_place",
    "incident_date",
    "prior_penalties_summary",
)


#: "Verilmedi" nöbetçisi — None'dan ayırt etmek için (None = alanı TEMİZLE).
_UNSET: object = object()


@transaction.atomic
def update_decision_narrative(
    decision: DisciplineDecision,
    *,
    fields: dict[str, object],
    enforcement_start_date: object = _UNSET,
    student_birth_date: object = _UNSET,
) -> DisciplineDecision:
    """EK-1 anlatı/bağlam alanlarını günceller — dosya kapanana kadar serbest.

    Karar çekirdeği (`update_decision`) tebliğ/onay sonrası kilitliyken EK-1
    anlatısı kapanışa dek düzenlenebilir (OYS Tur 107 davranışı).

    - `enforcement_start_date` (md. 164/2): uygulama başlangıcı genelde
      kesinleşme SONRASI belli olur → post-hoc set/temizlenebilir (OYS Tur 102).
    - `student_birth_date`: karara değil öğrenci SİCİLİNE yazılır (EK-1'de doğum
      tarihi boş kalan e-Okul veli ihracı senaryosu — OYS Tur 220); None/verilmemiş
      sicile dokunmaz.
    - Kapalı-dosya kilidi OYS kodunda YOKTUR — model dokümantasyonundaki niyet
      ("dosya kapanana kadar güncellenir") burada bilinçli olarak koda döküldü.
    """
    if decision.case.closed_at is not None:
        raise ValueError("Dosya kapatılmış; EK-1 alanları artık güncellenemez.")
    changed: list[str] = []
    for name in NARRATIVE_FIELDS:
        if name in fields and getattr(decision, name) != fields[name]:
            setattr(decision, name, fields[name])
            changed.append(name)
    if (
        enforcement_start_date is not _UNSET
        and decision.enforcement_start_date != enforcement_start_date
    ):
        decision.enforcement_start_date = enforcement_start_date  # type: ignore[assignment]
        changed.append("enforcement_start_date")
    if changed:
        decision.save(update_fields=[*changed, "updated_at"])
    if student_birth_date is not _UNSET and student_birth_date is not None:
        from apps.okul.services import persons as okul_persons

        okul_persons.update_student(decision.student, birth_date=student_birth_date)
    return decision
