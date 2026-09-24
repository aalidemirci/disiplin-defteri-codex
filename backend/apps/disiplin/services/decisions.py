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
    ApprovalAuthority,
    DecisionApprovalStatus,
    DisciplineAppeal,
    DisciplineCase,
    DisciplineDecision,
    DisciplineEvent,
    DisciplineMeeting,
    PenaltyType,
)
from apps.disiplin.services.common import case_has_student
from apps.okul.services.calendar import is_school_open_day, is_working_day

#: Onaylayan merciden bir üst itiraz mercii (md. 169/3-4: kararı onaylayan kurul aynı
#: karara itirazı görüşemez; müdür onaylı ceza → ilçe; ilçe → il; il → üst kurul).
_NEXT_APPEAL_BOARD: dict[str, str] = {
    ApprovalAuthority.PRINCIPAL: ApprovalAuthority.DISTRICT_BOARD,
    ApprovalAuthority.DISTRICT_BOARD: ApprovalAuthority.PROVINCIAL_BOARD,
    ApprovalAuthority.PROVINCIAL_BOARD: ApprovalAuthority.UPPER_BOARD,
}


def appeal_authority_for_decision(decision: DisciplineDecision) -> str:
    """Kararın itiraz mercii — cezayı ONAYLAYAN merciinin bir üstü (md. 169/3-4).

    Normal akışta ceza türünden türeyen tabloyla aynıdır (kınama/uzaklaştırma →
    ilçe; okul değiştirme → il; örgün dışı → üst kurul). Fark md. 197'dedir:
    müdürün ilçeye gönderdiği kararı ilçe kurulu bağlar; ona itiraz il kurulundadır
    (md. 202/1-b).
    """
    approver = (
        ApprovalAuthority.DISTRICT_BOARD
        if decision.referred_to_district
        and decision.approval_authority == ApprovalAuthority.PRINCIPAL
        else decision.approval_authority
    )
    return _NEXT_APPEAL_BOARD.get(approver, ApprovalAuthority.UPPER_BOARD)


def _validate_enforcement_start(
    decision_penalty_type: str,
    enforcement_start_date: date | None,
    *,
    approved_at: date | None = None,
) -> None:
    """Uzaklaştırma uygulama başlangıcı okulun AÇIK olduğu bir gün olmalı (md. 172/1-a).

    Hafta sonu/tatil/ara tatil günü başlangıç olarak 1. ceza günü sayılır ve
    öğrenci fiilen eksik gün ceza çeker. Onay tarihi biliniyorsa başlangıç ondan
    önce olamaz (md. 163/2 "onayından sonra uygulanır").
    """
    if enforcement_start_date is None:
        return
    if decision_penalty_type != PenaltyType.SHORT_TERM_SUSPENSION:
        return
    if not is_school_open_day(enforcement_start_date):
        raise ValueError(
            "Uzaklaştırma başlangıcı okulun açık olduğu bir gün olmalıdır "
            "(hafta sonu, tatil, ara tatil veya ders yılı dışı olamaz — md. 172/1-a)."
        )
    if approved_at is not None and enforcement_start_date < approved_at:
        raise ValueError("Uzaklaştırma, karar onaylanmadan başlatılamaz (md. 163/2).")


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
    """EK-1 'şimdiye kadar aldığı cezalar' — öğrencinin YÜRÜRLÜKTEKİ önceki cezaları.

    Onaysız, "ceza verilmesine yer olmadığı", itirazla bozulmuş ve md. 171/2 ile
    kaldırılmış kararlar yazılmaz — md. 171/3: kaldırılan ceza için "disiplin
    cezası bulunmadığı bildirilir".
    """
    from apps.disiplin.selectors import penalties_in_force

    prior = penalties_in_force(
        DisciplineDecision.objects.filter(student_id=student_id).exclude(case_id=exclude_case_id)
    ).order_by("decision_date")
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
    from apps.disiplin import selectors

    if penalty_type not in set(PenaltyType.values):
        raise ValueError("Geçersiz ceza türü.")
    if case.closed_at is not None:
        raise ValueError("Dosya kapatılmış; resmî karar girilemez.")
    referred_on = selectors.committee_referred_on(case)
    if referred_on is None:
        raise ValueError(
            "Dosya okul öğrenci ödül ve disiplin kuruluna sevk edilmemiş; ceza kararı "
            "yalnız kurulda görüşülüp karara bağlanan dosyada girilir (md. 163/2)."
        )
    if decision_date < referred_on:
        raise ValueError("Karar tarihi kurula sevk tarihinden önce olamaz.")
    if not case_has_student(case, student_id):
        raise ValueError("Öğrenci bu disiplin dosyasına dahil değil.")
    _validate_enforcement_start(penalty_type, enforcement_start_date)
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
    if is_suspension:
        _validate_enforcement_start(penalty_type, enforcement_start_date)
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
    if not case_has_student(decision.case, decision.student_id):
        raise ValueError("Öğrenci artık bu dosyada değil; karar geri yüklenemez.")
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
    modified_penalty_type: str = "",
    modified_suspension_days: int | None = None,
) -> DisciplineDecision:
    """Kararın onay durumunu günceller (md. 163/2 — merci sistem dışı, manuel giriş).

    md. 197: müdür yalnız onaylar (APPROVED) ya da beklemede bırakır (PENDING);
    reddetme yoktur. APPROVED + kınama/kısa uzaklaştırma → uygulanır (md. 172).

    Geçiş korumaları: itirazla bozulmuş (REJECTED) karar yeniden onaylanamaz;
    tebliğ edilmiş karar onaysız hâle döndürülemez; onay tarihi karar tarihinden
    önce olamaz. İlçe kuruluna gönderilmiş (md. 197) kararda APPROVED = ilçe
    kurulunun kararı bağlaması.

    `modified_penalty_type`: onay mercii bir KURUL ise (okul değiştirme → ilçe,
    örgün dışı → il; md. 197 ile ilçeye giden karar) kurul "onaylar veya
    DEĞİŞTİRİR" (md. 200/1-a, 202/1-a). Değiştirilen ceza türü + puan burada
    işlenir; itiraz mercii onaylayan kurulun bir üstü kalır.
    """
    if approval_status not in {DecisionApprovalStatus.PENDING, DecisionApprovalStatus.APPROVED}:
        raise ValueError("Müdür kararı yalnız onaylayabilir veya beklemede bırakabilir (md. 197).")
    if decision.approval_status == DecisionApprovalStatus.REJECTED:
        raise ValueError("İtiraz sonucu bozulmuş (kaldırılmış) karar yeniden onaylanamaz.")
    if approval_status == DecisionApprovalStatus.PENDING and decision.notified_at is not None:
        raise ValueError("Tebliğ edilmiş karar onaysız duruma döndürülemez.")
    if approval_status == DecisionApprovalStatus.APPROVED:
        if approved_on is None:
            raise ValueError("Onay tarihi zorunludur.")
        if approved_on < decision.decision_date:
            raise ValueError("Onay tarihi karar tarihinden önce olamaz.")
    fields = ["approval_status", "approved_at", "updated_at"]
    if modified_penalty_type:
        board_approves = (
            decision.approval_authority != ApprovalAuthority.PRINCIPAL
            or decision.approval_status == DecisionApprovalStatus.REFERRED_TO_DISTRICT
        )
        if approval_status != DecisionApprovalStatus.APPROVED or not board_approves:
            raise ValueError(
                "Ceza türü yalnız onay mercii kurul olan kararda, onay sırasında "
                "değiştirilebilir (md. 200/1-a, 202/1-a); okul kurulu kararı müdürce "
                "değiştirilemez (md. 197)."
            )
        fields += _apply_penalty_change(decision, modified_penalty_type, modified_suspension_days)
    decision.approval_status = approval_status
    decision.approved_at = approved_on
    decision.is_enforced = approval_status == DecisionApprovalStatus.APPROVED and (
        decision.penalty_type in (PenaltyType.REPRIMAND, PenaltyType.SHORT_TERM_SUSPENSION)
    )
    fields.append("is_enforced")
    decision.save(update_fields=fields)
    return decision


def _apply_penalty_change(
    decision: DisciplineDecision, penalty_type: str, suspension_days: int | None
) -> list[str]:
    """Üst kurulun cezayı değiştirmesini karara işler (puan dahil — md. 170).

    `approval_authority` DEĞİŞMEZ: kararı bağlayan (onaylayan) merci aynı kalır;
    itiraz mercii ondan türer (`appeal_authority_for_decision`).
    """
    if penalty_type not in set(PenaltyType.values):
        raise ValueError("Geçersiz ceza türü.")
    if penalty_type == decision.penalty_type:
        raise ValueError("Değiştirilen ceza türü mevcut cezayla aynı olamaz.")
    is_suspension = penalty_type == PenaltyType.SHORT_TERM_SUSPENSION
    decision.penalty_type = penalty_type
    decision.suspension_days = suspension_days if is_suspension else None
    if not is_suspension:
        decision.enforcement_start_date = None
    decision.behavior_point_deduction = discipline_periods.deduction_for(penalty_type)
    decision.full_clean(exclude=["event", "meeting"])
    return [
        "penalty_type",
        "suspension_days",
        "enforcement_start_date",
        "behavior_point_deduction",
    ]


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
    if decision.notified_at is not None:
        raise ValueError("Tebliğ edilmiş karar kurula iade edilemez / ilçeye gönderilemez.")
    if decided_on < decision.decision_date:
        raise ValueError("İade / sevk tarihi karar tarihinden önce olamaz.")
    if action == "RETURN":
        if decision.approval_status != DecisionApprovalStatus.PENDING:
            raise ValueError("Yalnız onay bekleyen karar kurula iade edilebilir (md. 197).")
        if decision.returned_at is not None:
            raise ValueError(
                "Karar kurula zaten bir kez iade edildi; md. 197 yalnız 'bir defa daha "
                "görüşülmek üzere' iade öngörür. Kurul ısrar ediyorsa ilçeye gönderin."
            )
        new_status = DecisionApprovalStatus.RETURNED_TO_COMMITTEE
    elif action == "REFER":
        if decision.approval_status != DecisionApprovalStatus.RETURNED_TO_COMMITTEE:
            raise ValueError(
                "İlçe kuruluna gönderme yalnız önce kurula iade edilmiş kararda yapılabilir "
                "(md. 197 — kurul ısrarı)."
            )
        new_status = DecisionApprovalStatus.REFERRED_TO_DISTRICT
        decision.referred_to_district = True
        # İade gerekçesi korunur; ilçeye sevk gerekçesi (müdürün görüş ve teklifleri)
        # alta eklenir — iki md. 197 adımı da kayıtta kalır.
        reason = f"{decision.return_reason}\n\nİlçeye sevk: {reason}".strip()
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
            "referred_to_district",
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
    Yalnız ONAYLANMIŞ karar tebliğ edilir (md. 163/2, 169/2 — ceza onaydan sonra
    uygulanır; onaysız kararın tebliği itiraz süresini erken başlatırdı). İtirazı
    olan kararın tebliğ tarihi değiştirilemez (itiraz süre bayrakları bayatlar).
    """
    if decision.approval_status != DecisionApprovalStatus.APPROVED:
        raise ValueError(
            "Karar onaylanmadan tebliğ edilemez (md. 163/2, 169/2): önce onay "
            "durumunu (müdür / ilçe / il kurulu onayı) kaydedin."
        )
    if decision.appeals.exists():
        raise ValueError("İtirazı olan kararın tebliğ tarihi değiştirilemez.")
    if decision.approved_at is not None and notified_on < decision.approved_at:
        raise ValueError("Tebliğ tarihi onay tarihinden önce olamaz.")
    if notified_on < decision.decision_date:
        raise ValueError("Tebliğ tarihi karar tarihinden önce olamaz.")
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
    if decision.penalty_type == PenaltyType.NO_PENALTY:
        raise ValueError("'Ceza verilmesine yer olmadığı' kararına itiraz yolu yoktur (md. 169/3).")
    if decision.notified_at is None or decision.appeal_deadline is None:
        raise ValueError("İtiraz için karar önce tebliğ edilmelidir (md. 169/3).")
    if filed_on < decision.notified_at:
        raise ValueError("İtiraz tarihi tebliğ tarihinden önce olamaz (md. 169/3).")
    if decision.appeals.filter(resulted_on__isnull=False).exists():
        raise ValueError(
            "Bu karara yapılan itiraz sonuçlanmış; itiraz sonucu verilen karar kesindir, "
            "yeniden itiraz edilemez (md. 169/4)."
        )
    if filed_by_role == AppealFiledByRole.STUDENT_ADULT:
        _assert_adult(decision, filed_on)

    within = filed_on <= decision.appeal_deadline
    appeal = DisciplineAppeal(
        decision=decision,
        filed_on=filed_on,
        filed_by_role=filed_by_role,
        filed_by_name=filed_by_name,
        within_deadline=within,
        appeal_authority=appeal_authority_for_decision(decision),
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


def _assert_adult(decision: DisciplineDecision, on: date) -> None:
    """md. 169/3: öğrenci kendisi ancak 18 yaşını tamamlamışsa itiraz eder."""
    birth = decision.student.birth_date
    if birth is None:
        raise ValueError(
            "Öğrencinin doğum tarihi kayıtlı değil; 18 yaşını tamamladığı doğrulanamadı "
            "(md. 169/3). Önce öğrenci kartına doğum tarihini girin."
        )
    try:
        eighteenth = birth.replace(year=birth.year + 18)
    except ValueError:  # 29 Şubat doğumlu → 1 Mart
        eighteenth = date(birth.year + 18, 3, 1)
    if on < eighteenth:
        raise ValueError(
            "Öğrenci itiraz tarihinde 18 yaşını tamamlamamış; itirazı veli veya okul "
            "müdürü yapar (md. 169/3)."
        )


@transaction.atomic
def forward_appeal(appeal: DisciplineAppeal, *, forwarded_on: date) -> DisciplineAppeal:
    """İtirazın üst kurula sevkini kaydeder (md. 169/3 — en geç 5 iş günü)."""
    if appeal.result != AppealResult.PENDING:
        raise ValueError("Sonuçlanmış itirazın sevk tarihi değiştirilemez.")
    if forwarded_on < appeal.filed_on:
        raise ValueError("Sevk tarihi itiraz başvuru tarihinden önce olamaz.")
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
    new_penalty_type: str = "",
    new_suspension_days: int | None = None,
) -> DisciplineAppeal:
    """İtiraz sonucunu kaydeder (md. 169/4 — sonuç kesindir).

    OVERTURNED (bozuldu) → ceza kaldırılır: karar REJECTED + uygulama kalkar;
    davranış puanı iadesi selector tarafında bozulmuş kararlar hariç tutularak
    sağlanır (md. 171).

    REDUCED (değiştirildi — md. 200/Ç, 202/1-c, 204/1-b) → `new_penalty_type`
    zorunludur; karar yeni cezaya güncellenir (puan md. 170'e göre yeniden
    türer), eski tür itiraz kaydında (`previous_penalty_type`) saklanır.

    Sonuç kesin olduğundan bir kez girilir; yeniden sonuçlandırılamaz.
    """
    if result not in set(AppealResult.values) or result == AppealResult.PENDING:
        raise ValueError("Geçersiz itiraz sonucu.")
    if appeal.result != AppealResult.PENDING:
        raise ValueError("İtiraz zaten sonuçlanmış; itiraz sonucu kesindir (md. 169/4).")
    if resulted_on < appeal.filed_on:
        raise ValueError("Sonuç tarihi itiraz başvuru tarihinden önce olamaz.")
    decision = appeal.decision
    if result == AppealResult.REDUCED:
        if not new_penalty_type:
            raise ValueError(
                "'Değiştirildi' sonucunda itiraz kurulunun verdiği yeni ceza seçilmelidir "
                "(davranış puanı buna göre yeniden hesaplanır — md. 170)."
            )
        appeal.previous_penalty_type = decision.penalty_type
        changed = _apply_penalty_change(decision, new_penalty_type, new_suspension_days)
        decision.save(update_fields=[*changed, "updated_at"])
    appeal.result = result
    appeal.resulted_on = resulted_on
    appeal.result_notes = result_notes
    appeal.save(
        update_fields=[
            "result",
            "resulted_on",
            "result_notes",
            "previous_penalty_type",
            "updated_at",
        ]
    )

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
        _validate_enforcement_start(
            decision.penalty_type,
            enforcement_start_date,  # type: ignore[arg-type]
            approved_at=decision.approved_at,
        )
        decision.enforcement_start_date = enforcement_start_date  # type: ignore[assignment]
        changed.append("enforcement_start_date")
    if changed:
        decision.save(update_fields=[*changed, "updated_at"])
    if student_birth_date is not _UNSET and student_birth_date is not None:
        from apps.okul.services import persons as okul_persons

        okul_persons.update_student(decision.student, birth_date=student_birth_date)
    return decision


@transaction.atomic
def remove_penalty(
    decision: DisciplineDecision, *, removed_on: date, note: str = ""
) -> DisciplineDecision:
    """md. 171/2: öğretmenler kurulunca cezanın kaldırılması + davranış puanı iadesi.

    Yalnız kesinleşmiş, yürürlükteki gerçek ceza kaldırılabilir. Kaldırılan ceza
    davranış puanından, triajdan ve EK-1 "önceki cezalar"dan düşer; md. 171/3
    gereği öğrencinin "disiplin cezası bulunmadığı" kabul edilir. Kaldırılan ceza
    e-Okul'dan 5 iş günü içinde çıkarılır (kullanıcıya hatırlatılır).
    """
    from apps.disiplin import selectors

    if decision.penalty_type == PenaltyType.NO_PENALTY:
        raise ValueError("'Ceza verilmesine yer olmadığı' kararında kaldırılacak ceza yok.")
    if decision.penalty_removed_on is not None:
        raise ValueError("Bu ceza zaten kaldırılmış.")
    final, reason = selectors.decision_is_final(decision)
    if not final:
        raise ValueError(f"Yalnız kesinleşmiş ceza kaldırılabilir: {reason}.")
    if removed_on < decision.decision_date:
        raise ValueError("Kaldırma tarihi karar tarihinden önce olamaz.")
    if removed_on > timezone.localdate():
        raise ValueError("Kaldırma tarihi gelecekte olamaz.")
    decision.penalty_removed_on = removed_on
    decision.penalty_removal_note = (note or "").strip()
    decision.save(update_fields=["penalty_removed_on", "penalty_removal_note", "updated_at"])
    return decision


@transaction.atomic
def undo_penalty_removal(decision: DisciplineDecision) -> DisciplineDecision:
    """Yanlışlıkla girilen md. 171/2 kaldırma kaydını geri alır (tek yönlü kapan olmasın)."""
    if decision.penalty_removed_on is None:
        raise ValueError("Bu cezada kaldırma kaydı yok.")
    decision.penalty_removed_on = None
    decision.penalty_removal_note = ""
    decision.save(update_fields=["penalty_removed_on", "penalty_removal_note", "updated_at"])
    return decision
