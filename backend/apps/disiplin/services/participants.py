"""Disiplin rollü katılımcı + müdür uyarısı — md. 157/7, 166, 193.

OYS `services/discipline_participants.py`'den temizlenerek taşındı: audit +
kullanıcı parametreleri silindi; STAFF referansı `okul.Personnel`. İş kuralları
(suçlanan senkronu, tekillik, koruma) AYNEN.
"""

from __future__ import annotations

from datetime import date

from django.db import transaction

from apps.disiplin.models import (
    DisciplineCase,
    DisciplineCaseStudent,
    DisciplineDecision,
    DisciplineParticipant,
    DisciplineWarning,
    ParticipantPersonType,
    ParticipantRole,
)
from apps.disiplin.services.common import case_has_student
from apps.okul import selectors as okul_selectors
from apps.okul.models import Personnel, Student


def ensure_accused_participant(case: DisciplineCase, student: Student) -> None:
    """Bir öğrenci için (silinmemiş) ACCUSED/STUDENT katılımcı yoksa oluşturur (idempotent).

    `create_case` ve `add_participant` ortak kullanır; suçlanan roster'ını
    `DisciplineCaseStudent` ile tutarlı tutar.
    """
    exists = DisciplineParticipant.objects.filter(
        case=case, role=ParticipantRole.ACCUSED, student=student
    ).exists()
    if exists:
        return
    participant = DisciplineParticipant(
        case=case,
        role=ParticipantRole.ACCUSED,
        person_type=ParticipantPersonType.STUDENT,
        student=student,
        name_snapshot=(student.full_name or f"#{student.pk}"),
    )
    participant.full_clean()
    participant.save()


def _resolve_participant_person(
    person_type: str, person_id: int | None, external_name: str
) -> tuple[Student | None, Personnel | None, str, str]:
    """Kişi tipine göre referansı çözer; (student, user, external_name, ad_snapshot) döner."""
    if person_type == ParticipantPersonType.STUDENT:
        if person_id is None:
            raise ValueError("Öğrenci katılımcı için öğrenci seçilmelidir.")
        s = okul_selectors.get_student(person_id)
        if s is None:
            raise ValueError("Öğrenci bulunamadı.")
        return s, None, "", (s.full_name or f"#{person_id}")
    if person_type == ParticipantPersonType.STAFF:
        if person_id is None:
            raise ValueError("Personel katılımcı için personel seçilmelidir.")
        u = okul_selectors.get_personnel(person_id)
        if u is None:
            raise ValueError("Personel bulunamadı.")
        return None, u, "", u.full_name
    if person_type == ParticipantPersonType.EXTERNAL:
        name = (external_name or "").strip()
        if not name:
            raise ValueError("Dış kişi için ad zorunludur.")
        return None, None, name, name
    raise ValueError("Geçersiz kişi tipi.")


@transaction.atomic
def add_participant(
    case: DisciplineCase,
    *,
    role: str,
    person_type: str,
    person_id: int | None = None,
    external_name: str = "",
    external_title: str = "",
    notes: str = "",
) -> DisciplineParticipant:
    """Dosyaya rollü katılımcı ekler (hakkında işlem yapılan/mağdur/tanık).

    Suçlanan-öğrenci katılımcı `DisciplineCaseStudent` ile senkronlanır (through
    satırı garanti edilir). Aynı öğrenci/personel aynı rolde iki kez eklenemez.
    """
    if role not in set(ParticipantRole.values):
        raise ValueError("Geçersiz katılımcı rolü.")
    student, person, ext_name, name = _resolve_participant_person(
        person_type, person_id, external_name
    )

    if student is not None:
        dup = DisciplineParticipant.objects.filter(case=case, role=role, student=student).exists()
        if dup:
            raise ValueError("Bu öğrenci bu rolde dosyaya zaten eklenmiş.")
    elif person is not None:
        dup = DisciplineParticipant.objects.filter(case=case, role=role, user=person).exists()
        if dup:
            raise ValueError("Bu personel bu rolde dosyaya zaten eklenmiş.")

    participant = DisciplineParticipant(
        case=case,
        role=role,
        person_type=person_type,
        student=student,
        user=person,
        external_name=ext_name,
        external_title=(external_title or "").strip(),
        name_snapshot=name,
        notes=notes,
    )
    participant.full_clean()
    participant.save()

    # Suçlanan öğrenci → DisciplineCaseStudent senkronu (karar dayanağı).
    if role == ParticipantRole.ACCUSED and person_type == ParticipantPersonType.STUDENT:
        DisciplineCaseStudent.objects.get_or_create(case=case, student=student)

    return participant


@transaction.atomic
def remove_participant(participant: DisciplineParticipant) -> None:
    """Katılımcıyı soft-delete eder (kayıt korunur).

    Suçlanan öğrenci için: karar verilmişse çıkarılamaz; dosyada tek suçlanan
    kalmışsa çıkarılamaz (1..n suçlanan). Aksi halde `DisciplineCaseStudent`
    through satırı da kaldırılır (senkron).
    """
    case_id = participant.case_id
    accused_student_id: int | None = (
        participant.student_id
        if participant.role == ParticipantRole.ACCUSED
        and participant.person_type == ParticipantPersonType.STUDENT
        else None
    )
    if accused_student_id is not None:
        if DisciplineDecision.objects.filter(
            case_id=case_id, student_id=accused_student_id
        ).exists():
            raise ValueError("Hakkında karar verilmiş öğrenci dosyadan çıkarılamaz.")
        remaining = (
            DisciplineParticipant.objects.filter(case_id=case_id, role=ParticipantRole.ACCUSED)
            .exclude(pk=participant.pk)
            .count()
        )
        if remaining == 0:
            raise ValueError("Dosyada en az bir suçlanan öğrenci kalmalıdır.")

    participant.delete()  # soft delete
    if accused_student_id is not None:
        DisciplineCaseStudent.objects.filter(
            case_id=case_id, student_id=accused_student_id
        ).delete()


@transaction.atomic
def issue_warning(
    case: DisciplineCase,
    *,
    student_id: int,
    warning_date: date,
    summary: str,
) -> DisciplineWarning:
    """Müdür uyarısı kaydeder (md. 157/7). CEZA DEĞİLDİR — davranış puanı düşmez.

    Öğrenci dosyaya dahil (suçlanan) olmalı. Tekrarı triajda kurula yönlendirir
    (md. 166, selectors.should_route_to_committee).
    """
    if not case_has_student(case, student_id):
        raise ValueError("Öğrenci bu disiplin dosyasına dahil değil.")
    if not (summary or "").strip():
        raise ValueError("Uyarı gerekçesi (summary) zorunludur.")

    warning = DisciplineWarning(
        case=case,
        student_id=student_id,
        warning_date=warning_date,
        summary=summary,
    )
    warning.full_clean()
    warning.save()
    return warning
