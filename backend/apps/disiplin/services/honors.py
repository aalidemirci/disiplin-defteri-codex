"""Onur kurulu + onur belgesi servisleri — honors-LITE (md. 159-184).

OYS `services/honors.py`'den SADELEŞTİRİLEREK taşındı (tasarım §4.2): teklif
penceresi/limiti, form-teslim takibi, kardeş eleme (SUPERSEDED), toplu teklif ve
bildirim ALINMADI. Kalan çekirdek: kurul yönetimi + teklif → uygun görüş →
belge/ret durum makinesi (davranış puanı kapısı AYNEN — md. 161).
"""

from __future__ import annotations

from datetime import date

from django.db import transaction

from apps.disiplin.models import (
    HonorBoard,
    HonorBoardMember,
    HonorCertificate,
    HonorCertificateEvent,
    HonorCertificateEventType,
    HonorCertificateStatus,
    HonorCriterion,
    HonorGeneralAssemblyMember,
    HonorProposerRole,
)
from apps.okul import selectors as okul_selectors
from apps.okul.models import SchoolYear


def _validate_chair_outside_discipline_committee(*, school_year_id: int, personnel_id: int) -> None:
    from apps.disiplin.models import DisciplineCommittee, DisciplineCommitteeMember

    is_member = (
        DisciplineCommittee.objects.filter(
            school_year_id=school_year_id,
            chair_id=personnel_id,
        ).exists()
        or DisciplineCommitteeMember.objects.filter(
            committee__school_year_id=school_year_id,
            member_user_id=personnel_id,
        ).exists()
    )
    if is_member:
        raise ValueError(
            "Onur kurulu başkanı/yedeği, Ödül ve Disiplin Kurulu üyeleri dışından seçilmelidir."
        )


@transaction.atomic
def create_honor_board(
    *,
    school_year_id: int,
    chair_id: int,
    substitute_chair_id: int | None = None,
    notes: str = "",
) -> HonorBoard:
    """Bir ders yılı için onur kurulu oluşturur (yıl başına tek — md. 180).

    Başkan bir öğretmen olmalı (md. 182 — ödül-disiplin kurulu dışından; veri
    olarak zorlanmaz). Aynı yıl için kurul varsa ValueError.
    """
    year = okul_selectors.get_school_year(school_year_id)
    if year is None:
        raise ValueError("Ders yılı bulunamadı.")
    chair = okul_selectors.get_personnel(chair_id)
    if chair is None:
        raise ValueError("Onur kurulu başkanı (personel) bulunamadı.")
    if HonorBoard.objects.filter(school_year=year).exists():
        raise ValueError("Bu ders yılı için zaten bir onur kurulu var.")
    _validate_chair_outside_discipline_committee(
        school_year_id=year.pk,
        personnel_id=chair.pk,
    )
    substitute = None
    if substitute_chair_id is not None:
        substitute = okul_selectors.get_personnel(substitute_chair_id)
        if substitute is None:
            raise ValueError("Onur kurulu başkan yedeği bulunamadı.")
        if substitute.pk == chair.pk:
            raise ValueError("Başkan ve başkan yedeği aynı kişi olamaz.")
        _validate_chair_outside_discipline_committee(
            school_year_id=year.pk,
            personnel_id=substitute.pk,
        )

    board: HonorBoard = HonorBoard.objects.create(
        school_year=year,
        chair=chair,
        substitute_chair=substitute,
        notes=notes,
    )
    return board


@transaction.atomic
def set_honor_board_chair(board: HonorBoard, chair_id: int) -> HonorBoard:
    """Onur kurulu başkanını günceller (md. 182 — öğretmenler kurulu seçer)."""
    chair = okul_selectors.get_personnel(chair_id)
    if chair is None:
        raise ValueError("Onur kurulu başkanı (personel) bulunamadı.")
    _validate_chair_outside_discipline_committee(
        school_year_id=board.school_year_id,
        personnel_id=chair.pk,
    )
    board.chair = chair
    board.save(update_fields=["chair", "updated_at"])
    return board


@transaction.atomic
def set_honor_board_substitute_chair(
    board: HonorBoard,
    substitute_chair_id: int,
) -> HonorBoard:
    substitute = okul_selectors.get_personnel(substitute_chair_id)
    if substitute is None:
        raise ValueError("Onur kurulu başkan yedeği bulunamadı.")
    if substitute.pk == board.chair_id:
        raise ValueError("Başkan ve başkan yedeği aynı kişi olamaz.")
    _validate_chair_outside_discipline_committee(
        school_year_id=board.school_year_id,
        personnel_id=substitute.pk,
    )
    board.substitute_chair = substitute
    board.save(update_fields=["substitute_chair", "updated_at"])
    return board


@transaction.atomic
def add_honor_board_member(
    board: HonorBoard,
    *,
    student_id: int,
    grade_level: int | None = None,
    is_second_chair: bool = False,
    is_substitute: bool = False,
    order: int = 0,
    title: str = "",
    assembly_member_id: int | None = None,
) -> HonorBoardMember:
    """Onur kuruluna öğrenci üye ekler (md. 180). Aynı öğrenci iki kez eklenemez."""
    student = okul_selectors.get_student(student_id)
    if student is None:
        raise ValueError("Öğrenci üye bulunamadı.")
    if HonorBoardMember.objects.filter(
        board=board,
        member_student_id=student_id,
        effective_until__isnull=True,
    ).exists():
        raise ValueError("Bu öğrenci bu onur kuruluna zaten üye olarak eklenmiş.")
    from apps.disiplin.selectors import is_eligible_for_honor

    if not is_eligible_for_honor(student_id, board.school_year_id):
        raise ValueError("Disiplin cezası/davranış puanı nedeniyle öğrenci kurul üyesi olamaz.")
    assembly_member_qs = HonorGeneralAssemblyMember.objects.filter(
        school_year=board.school_year,
        member_student_id=student_id,
        effective_until__isnull=True,
    )
    if assembly_member_id is not None:
        assembly_member_qs = assembly_member_qs.filter(pk=assembly_member_id)
    assembly_member = assembly_member_qs.first()
    if assembly_member is None:
        raise ValueError(
            "Onur Kurulu öğrencisi, aktif Onur Genel Kurulu temsilcileri arasından seçilmelidir."
        )
    if (
        is_second_chair
        and HonorBoardMember.objects.filter(
            board=board,
            is_second_chair=True,
            is_substitute=False,
            effective_until__isnull=True,
        ).exists()
    ):
        raise ValueError("Onur kurulunda yalnız bir aktif ikinci başkan olabilir.")

    member = HonorBoardMember(
        board=board,
        assembly_member=assembly_member,
        member_student=student,
        grade_level=grade_level,
        is_second_chair=is_second_chair,
        is_substitute=is_substitute,
        order=order,
        title=title,
        member_name=(student.full_name or f"#{student_id}"),
        effective_from=board.school_year.start_date,
    )
    member.full_clean()
    member.save()
    return member


@transaction.atomic
def remove_honor_board_member(member: HonorBoardMember) -> None:
    """Üyeliği tarihçeyi koruyarak sonlandırır."""
    member.effective_until = date.today()
    member.end_reason = "Elle sonlandırıldı."
    member.save(update_fields=["effective_until", "end_reason", "updated_at"])


@transaction.atomic
def add_general_assembly_member(
    *,
    school_year_id: int,
    student_id: int,
    effective_from: date | None = None,
    replaced_member_id: int | None = None,
) -> HonorGeneralAssemblyMember:
    """Şube temsilcisini kaydeder; varsa önceki temsilcinin görevini sonlandırır."""

    year = okul_selectors.get_school_year(school_year_id)
    student = okul_selectors.get_student(student_id)
    if year is None:
        raise ValueError("Ders yılı bulunamadı.")
    if effective_from is None:
        effective_from = year.start_date
    if student is None or student.class_level is None or not student.class_section:
        raise ValueError("Öğrencinin sınıf ve şube bilgisi bulunmalıdır.")
    if not (year.start_date <= effective_from <= year.end_date):
        raise ValueError("Görev başlangıcı ders yılı içinde olmalıdır.")
    from apps.disiplin.selectors import is_eligible_for_honor

    if not is_eligible_for_honor(student_id, year.pk):
        raise ValueError("Disiplin cezası/davranış puanı nedeniyle öğrenci temsilci olamaz.")
    previous = HonorGeneralAssemblyMember.objects.filter(
        school_year=year,
        class_level=student.class_level,
        class_section=student.class_section,
        effective_until__isnull=True,
    ).first()
    if previous is not None:
        if replaced_member_id != previous.pk:
            raise ValueError("Bu şubenin aktif temsilcisi var; değişiklik olarak kaydedin.")
        from apps.okul.models import SchoolTerm

        second_term = SchoolTerm.objects.filter(school_year=year, sequence=2).first()
        if second_term is None:
            raise ValueError("Temsilci değişikliği için önce ders yılı dönemleri tanımlanmalıdır.")
        if effective_from != second_term.start_date:
            raise ValueError(
                "Onur Genel Kurulu temsilci değişikliği 2. dönemin başlangıç tarihinde yürürlüğe girer."
            )
        from datetime import timedelta

        previous.effective_until = effective_from - timedelta(days=1)
        previous.end_reason = "İzleyen dönem başında yeni temsilci seçildi."
        previous.save(update_fields=["effective_until", "end_reason", "updated_at"])
    member: HonorGeneralAssemblyMember = HonorGeneralAssemblyMember.objects.create(
        school_year=year,
        member_student=student,
        class_level=student.class_level,
        class_section=student.class_section,
        member_name=student.full_name,
        effective_from=effective_from,
        replaced_member=previous,
    )
    return member


@transaction.atomic
def end_general_assembly_membership(
    member: HonorGeneralAssemblyMember,
    *,
    effective_until: date | None = None,
    reason: str,
) -> HonorGeneralAssemblyMember:
    if effective_until is None:
        effective_until = date.today()
    if not reason.strip():
        raise ValueError("Üyelik bitiş nedeni zorunludur.")
    if effective_until < member.effective_from:
        raise ValueError("Görev bitişi başlangıçtan önce olamaz.")
    member.effective_until = effective_until
    member.end_reason = reason.strip()
    member.save(update_fields=["effective_until", "end_reason", "updated_at"])
    return member


# ---------------------------------------------------------------------------
# Onur belgesi durum makinesi (md. 161 + 183/b) — tek yönlü süreç
# ---------------------------------------------------------------------------
def _validate_criteria(criteria: list[str] | None) -> list[str]:
    """Kriter kodlarını doğrular (md. 161 a-ğ + 161/2). Geçersiz kod → ValueError."""
    cleaned = list(criteria or [])
    valid = set(HonorCriterion.values)
    bad = [c for c in cleaned if c not in valid]
    if bad:
        raise ValueError(f"Geçersiz onur kriteri: {', '.join(bad)}.")
    if not cleaned:
        raise ValueError("En az bir onur kriteri seçilmelidir.")
    return list(dict.fromkeys(cleaned))


def _record_event(
    certificate: HonorCertificate,
    *,
    event_type: str,
    event_date: date,
    meeting_id: int | None = None,
    explanation: str = "",
) -> HonorCertificateEvent:
    from apps.disiplin.models import CouncilMeeting, CouncilType, HonorMeetingKind
    from apps.okul.services.terms import term_for_date

    meetings = CouncilMeeting.objects.filter(
        school_year=certificate.school_year,
        meeting_date=event_date,
    )
    if event_type == HonorCertificateEventType.RECOMMENDED:
        meetings = meetings.filter(
            council_type=CouncilType.HONOR,
            honor_meeting_kind=HonorMeetingKind.BOARD,
        )
    elif event_type == HonorCertificateEventType.AWARDED:
        meetings = meetings.filter(council_type=CouncilType.DISCIPLINE)
    elif event_type in {
        HonorCertificateEventType.PRINCIPAL_APPROVED,
        HonorCertificateEventType.PRINCIPAL_REJECTED,
    }:
        meetings = meetings.none()
    if meeting_id is not None:
        meeting = meetings.filter(pk=meeting_id).first()
        if meeting is None:
            raise ValueError(
                "Seçilen toplantı işlem tarihi, ders yılı veya kurul türüyle uyumlu değil."
            )
    else:
        candidates = list(meetings[:2])
        meeting = candidates[0] if len(candidates) == 1 else None

    event: HonorCertificateEvent = HonorCertificateEvent.objects.create(
        certificate=certificate,
        event_type=event_type,
        event_date=event_date,
        school_term=(
            certificate.school_term
            if event_type == HonorCertificateEventType.PROPOSED
            else term_for_date(certificate.school_year, event_date)
        ),
        meeting=meeting,
        explanation=explanation,
    )
    return event


@transaction.atomic
def propose_honor_certificate(
    *,
    student_id: int,
    proposer_role: str,
    school_year_id: int | None = None,
    school_term_id: int | None = None,
    criteria: list[str] | None = None,
    justification: str = "",
    proposer_name: str = "",
) -> HonorCertificate:
    """Onur belgesi teklifi oluşturur (md. 161 — öğrenci/öğretmen/yönetim teklifi).

    Davranış puanı indirilmemiş olmalı (md. 161); bir veya birden fazla örnek
    davranış seçilebilir. Ders yılı verilmezse aktif yıl. Durum = PROPOSED.
    """
    from apps.disiplin.selectors import is_eligible_for_honor
    from apps.okul import selectors as okul_selectors

    student = okul_selectors.get_student(student_id)
    if student is None:
        raise ValueError("Öğrenci bulunamadı.")
    if proposer_role not in set(HonorProposerRole.values):
        raise ValueError("Geçersiz teklif eden rolü.")
    year: SchoolYear | None
    if school_year_id is not None:
        year = okul_selectors.get_school_year(school_year_id)
    else:
        year = okul_selectors.active_school_year()
    if year is None:
        raise ValueError("Aktif ders yılı tanımlı değil; teklif için ders yılı gerekli.")
    cleaned = _validate_criteria(criteria)
    if not is_eligible_for_honor(student_id, year.pk):
        raise ValueError(
            "Öğrencinin davranış puanı indirilmiş; onur belgesi teklif edilemez (md. 161)."
        )
    from apps.okul.models import SchoolTerm

    school_term = None
    if school_term_id is None:
        if SchoolTerm.objects.filter(school_year=year).exists():
            raise ValueError("Onur belgesi teklifi için dönem seçilmelidir.")
    else:
        school_term = SchoolTerm.objects.filter(
            pk=school_term_id,
            school_year=year,
        ).first()
        if school_term is None:
            raise ValueError("Seçilen teklif dönemi ders yılıyla uyumlu değil.")

    certificate = HonorCertificate(
        student=student,
        school_year=year,
        school_term=school_term,
        status=HonorCertificateStatus.PROPOSED,
        proposer_role=proposer_role,
        proposer_name=proposer_name,
        criteria=cleaned,
        justification=justification,
    )
    certificate.full_clean(exclude=["criteria"])
    certificate.save()
    _record_event(
        certificate,
        event_type=HonorCertificateEventType.PROPOSED,
        event_date=date.today(),
    )
    return certificate


@transaction.atomic
def recommend_honor_certificate(
    certificate: HonorCertificate, *, recommended_on: date, meeting_id: int | None = None
) -> HonorCertificate:
    """Onur kurulunun uygun görüşü (md. 183/b): PROPOSED → HONOR_BOARD_RECOMMENDED."""
    if certificate.status != HonorCertificateStatus.PROPOSED:
        raise ValueError("Yalnız teklif aşamasındaki belge onur kurulu görüşüne sunulabilir.")
    certificate.status = HonorCertificateStatus.HONOR_BOARD_RECOMMENDED
    certificate.recommended_at = recommended_on
    certificate.save(update_fields=["status", "recommended_at", "updated_at"])
    _record_event(
        certificate,
        event_type=HonorCertificateEventType.RECOMMENDED,
        event_date=recommended_on,
        meeting_id=meeting_id,
    )
    return certificate


@transaction.atomic
def award_honor_certificate(
    certificate: HonorCertificate,
    *,
    awarded_on: date,
    meeting_id: int | None = None,
) -> HonorCertificate:
    """Ödül-disiplin kurulunun kabul kararı (md. 161): RECOMMENDED → AWARDED.

    Davranış puanı yeniden doğrulanır (puan teklif ile karar arasında düşmüş
    olabilir; md. 161).
    """
    from apps.disiplin.selectors import is_eligible_for_honor

    if certificate.status != HonorCertificateStatus.HONOR_BOARD_RECOMMENDED:
        raise ValueError(
            "Yalnız onur kurulunun uygun gördüğü belge ödül-disiplin kurulunca verilebilir."
        )
    if not is_eligible_for_honor(certificate.student_id, certificate.school_year_id):
        raise ValueError("Öğrencinin davranış puanı indirilmiş; onur belgesi verilemez (md. 161).")
    certificate.status = HonorCertificateStatus.AWARDED
    certificate.awarded_at = awarded_on
    certificate.save(update_fields=["status", "awarded_at", "updated_at"])
    _record_event(
        certificate,
        event_type=HonorCertificateEventType.AWARDED,
        event_date=awarded_on,
        meeting_id=meeting_id,
    )
    return certificate


@transaction.atomic
def approve_honor_proposal_by_principal(
    certificate: HonorCertificate,
    *,
    decided_on: date,
    explanation: str = "",
) -> HonorCertificate:
    """Ödül-disiplin kurulu kararını okul müdürü onayına bağlar."""
    if certificate.status != HonorCertificateStatus.AWARDED:
        raise ValueError(
            "Yalnız ödül ve disiplin kurulunca kabul edilen teklif okul müdürünce onaylanabilir."
        )
    certificate.status = HonorCertificateStatus.PRINCIPAL_APPROVED
    certificate.principal_decided_at = decided_on
    certificate.principal_decision_reason = explanation.strip()
    certificate.save(
        update_fields=[
            "status",
            "principal_decided_at",
            "principal_decision_reason",
            "updated_at",
        ]
    )
    _record_event(
        certificate,
        event_type=HonorCertificateEventType.PRINCIPAL_APPROVED,
        event_date=decided_on,
        explanation=explanation.strip(),
    )
    return certificate


@transaction.atomic
def reject_honor_proposal_by_principal(
    certificate: HonorCertificate,
    *,
    decided_on: date,
    reason: str,
) -> HonorCertificate:
    """Ödül-disiplin kurulu kararının okul müdürünce onaylanmamasını kaydeder."""
    reason = reason.strip()
    if not reason:
        raise ValueError("Okul müdürünün onaylamama gerekçesi zorunludur.")
    if certificate.status != HonorCertificateStatus.AWARDED:
        raise ValueError(
            "Yalnız ödül ve disiplin kurulunca kabul edilen teklif okul müdürü onayına sunulabilir."
        )
    certificate.status = HonorCertificateStatus.PRINCIPAL_REJECTED
    certificate.principal_decided_at = decided_on
    certificate.principal_decision_reason = reason
    certificate.save(
        update_fields=[
            "status",
            "principal_decided_at",
            "principal_decision_reason",
            "updated_at",
        ]
    )
    _record_event(
        certificate,
        event_type=HonorCertificateEventType.PRINCIPAL_REJECTED,
        event_date=decided_on,
        explanation=reason,
    )
    return certificate


@transaction.atomic
def reject_honor_certificate(
    certificate: HonorCertificate,
    *,
    reason: str,
    decided_on: date,
    meeting_id: int | None = None,
) -> HonorCertificate:
    """Onur belgesini uygun görmez (terminal red): PROPOSED|RECOMMENDED → REJECTED.

    Geri dönüş yoktur; yeniden değerlendirme yeni teklif gerektirir.
    """
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("Ret için gerekçe zorunludur.")
    if certificate.status not in {
        HonorCertificateStatus.PROPOSED,
        HonorCertificateStatus.HONOR_BOARD_RECOMMENDED,
    }:
        raise ValueError("Yalnız teklif veya uygun görüş aşamasındaki belge reddedilebilir.")
    certificate.status = HonorCertificateStatus.REJECTED
    certificate.rejection_reason = reason
    certificate.rejected_at = decided_on
    certificate.save(update_fields=["status", "rejection_reason", "rejected_at", "updated_at"])
    _record_event(
        certificate,
        event_type=HonorCertificateEventType.REJECTED,
        event_date=decided_on,
        meeting_id=meeting_id,
        explanation=reason,
    )
    return certificate
