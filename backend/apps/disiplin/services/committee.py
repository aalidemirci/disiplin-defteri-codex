"""Disiplin kurulu yönetimi — md. 185-192.

OYS `services/discipline_committee.py`'den temizlenerek taşındı: audit +
kullanıcı parametreleri silindi; TEACHER üye `okul.Personnel`, PARENT üye
yalnız ad snapshot'ıyla (tasarım §4.2 — Parent tablosu yok).
"""

from __future__ import annotations

from datetime import date
from typing import Any

from django.db import transaction

from apps.disiplin.models import (
    CommitteeMemberType,
    DisciplineCase,
    DisciplineCommittee,
    DisciplineCommitteeMember,
    DisciplineEvent,
    DisciplineMeeting,
)
from apps.okul import selectors as okul_selectors
from apps.okul.models import Personnel, Student


def _validate_not_honor_board_chair(*, school_year_id: int, personnel_id: int) -> None:
    """md. 182: onur kurulu başkanı (ve yedeği) ödül-disiplin kurulu üyelerinin DIŞINDADIR.

    Onur kurulu kurulurken ters yön zaten denetleniyor; bu da disiplin kuruluna
    sonradan eklenen kişi için aynı kuralı uygular.
    """
    from django.db.models import Q

    from apps.disiplin.models import HonorBoard

    if (
        HonorBoard.objects.filter(school_year_id=school_year_id)
        .filter(Q(chair_id=personnel_id) | Q(substitute_chair_id=personnel_id))
        .exists()
    ):
        raise ValueError(
            "Bu öğretmen onur kurulu başkanı/yedeği; ödül ve disiplin kuruluna üye "
            "olamaz (md. 182)."
        )


@transaction.atomic
def create_committee(*, school_year_id: int, chair_id: int, notes: str = "") -> DisciplineCommittee:
    """Bir ders yılı için disiplin kurulu oluşturur (yıl başına tek — md. 185).

    Başkan bir personel olmalı (md. 188 müdür yardımcısı). Aynı yıl için kurul
    varsa ValueError.
    """
    year = okul_selectors.get_school_year(school_year_id)
    if year is None:
        raise ValueError("Ders yılı bulunamadı.")
    chair = okul_selectors.get_personnel(chair_id)
    if chair is None:
        raise ValueError("Kurul başkanı (personel) bulunamadı.")
    if DisciplineCommittee.objects.filter(school_year=year).exists():
        raise ValueError("Bu ders yılı için zaten bir disiplin kurulu var.")
    _validate_not_honor_board_chair(school_year_id=year.pk, personnel_id=chair.pk)

    committee: DisciplineCommittee = DisciplineCommittee.objects.create(
        school_year=year, chair=chair, notes=notes
    )
    return committee


@transaction.atomic
def set_committee_chair(committee: DisciplineCommittee, chair_id: int) -> DisciplineCommittee:
    """Kurul başkanını günceller (md. 188 — müdür görevlendirir)."""
    chair = okul_selectors.get_personnel(chair_id)
    if chair is None:
        raise ValueError("Kurul başkanı (personel) bulunamadı.")
    _validate_not_honor_board_chair(school_year_id=committee.school_year_id, personnel_id=chair.pk)
    committee.chair = chair
    committee.save(update_fields=["chair", "updated_at"])
    return committee


@transaction.atomic
def add_committee_member(
    committee: DisciplineCommittee,
    *,
    member_type: str,
    person_id: int | None = None,
    member_name: str = "",
    is_substitute: bool = False,
    order: int = 0,
    title: str = "",
) -> DisciplineCommitteeMember:
    """Kurula asıl/yedek üye ekler (md. 185-186). Aynı kişi iki kez eklenemez.

    TEACHER→`person_id` Personnel, STUDENT→`person_id` Student; PARENT üyede FK
    YOK — `member_name` zorunludur (ad snapshot yeter, tasarım §4.2).
    """
    m_user: Personnel | None = None
    m_student: Student | None = None
    if member_type == CommitteeMemberType.TEACHER:
        if person_id is None:
            raise ValueError("Öğretmen üye için personel seçilmelidir.")
        m_user = okul_selectors.get_personnel(person_id)
        if m_user is None:
            raise ValueError("Öğretmen üye bulunamadı.")
        _validate_not_honor_board_chair(
            school_year_id=committee.school_year_id, personnel_id=m_user.pk
        )
        name = m_user.full_name
    elif member_type == CommitteeMemberType.STUDENT:
        if person_id is None:
            raise ValueError("Öğrenci üye için öğrenci seçilmelidir.")
        m_student = okul_selectors.get_student(person_id)
        if m_student is None:
            raise ValueError("Öğrenci üye bulunamadı.")
        name = m_student.full_name or f"#{person_id}"
    elif member_type == CommitteeMemberType.PARENT:
        name = (member_name or "").strip()
        if not name:
            raise ValueError("Veli üye için ad-soyad zorunludur.")
    else:
        raise ValueError("Geçersiz üye tipi.")

    # Aynı kişiyi (tipe göre) iki kez eklemeyi engelle; veli üyede ada bakılır.
    dup_qs = DisciplineCommitteeMember.objects.filter(committee=committee)
    if m_user is not None or m_student is not None:
        dup = dup_qs.filter(member_user=m_user, member_student=m_student).exists()
    else:
        dup = dup_qs.filter(member_type=CommitteeMemberType.PARENT, member_name=name).exists()
    if dup:
        raise ValueError("Bu kişi bu kurula zaten üye olarak eklenmiş.")

    member = DisciplineCommitteeMember(
        committee=committee,
        member_type=member_type,
        is_substitute=is_substitute,
        order=order,
        title=title,
        member_user=m_user,
        member_student=m_student,
        member_name=name,
    )
    member.full_clean()
    member.save()
    return member


@transaction.atomic
def remove_committee_member(member: DisciplineCommitteeMember) -> None:
    """Kurul üyesini soft-delete eder (kayıt korunur)."""
    member.delete()


def _check_quorum(committee: DisciplineCommittee, attendee_count: int) -> None:
    """md. 191/1: kurul üyelerin SALT ÇOĞUNLUĞUYLA toplanır.

    Üye tam sayısı = başkan + asıl üyeler (md. 185/1). Başkan toplantıda sayılır
    (yokluğunda md. 188 gereği öğretmen üye başkanlık eder, yedek katılır — o
    yedek de katılımcı listesine girer).
    """
    full = 1 + committee.members.filter(is_substitute=False).count()
    present = attendee_count + 1
    if attendee_count < 1 or present * 2 <= full:
        needed = full // 2 + 1
        raise ValueError(
            f"Toplantı yeter sayısı yok: kurul {full} kişi, en az {needed} kişi (başkan "
            "dahil) katılmalı (md. 191/1 — üyelerin salt çoğunluğu)."
        )


def _check_conflicts(case: DisciplineCase, members: Any) -> None:
    """md. 191/2: şikâyetçi veya zarar gören üye kurula katılamaz (yerine yedek)."""
    from apps.disiplin.models import ParticipantRole

    conflicted_users = set(
        case.participants.filter(role=ParticipantRole.VICTIM, user__isnull=False).values_list(
            "user_id", flat=True
        )
    )
    conflicted_students = set(
        case.participants.filter(
            role__in=[ParticipantRole.VICTIM, ParticipantRole.ACCUSED], student__isnull=False
        ).values_list("student_id", flat=True)
    )
    if case.petitioner_user_id is not None:
        conflicted_users.add(case.petitioner_user_id)
    if case.petitioner_student_id is not None and case.petitioner_role == "OGRENCI":
        conflicted_students.add(case.petitioner_student_id)
    names = [
        m.member_name
        for m in members
        if (m.member_user_id is not None and m.member_user_id in conflicted_users)
        or (m.member_student_id is not None and m.member_student_id in conflicted_students)
    ]
    if names:
        raise ValueError(
            f"{', '.join(names)} bu dosyada şikâyetçi/zarar gören (veya hakkında işlem "
            "yapılan) kişi; kurula katılamaz, yerine yedek üye çağrılır (md. 191/2)."
        )


@transaction.atomic
def record_meeting(
    case: DisciplineCase,
    *,
    meeting_date: date,
    attendee_member_ids: list[int],
    notes: str = "",
    event: DisciplineEvent | None = None,
) -> DisciplineMeeting:
    """Bir dosya için kurul toplantısı kaydeder; katılanlar kurul üyelerinden seçilir.

    Katılımcılar aktif kurulun üyeleri olmalı (md. 191). Tutanak/PDF veriyi
    buradan çeker.
    """
    from apps.disiplin.selectors import get_active_committee

    committee = get_active_committee()
    if committee is None:
        raise ValueError("Aktif ders yılı için tanımlı bir disiplin kurulu yok.")

    valid_ids = set(
        committee.members.filter(pk__in=attendee_member_ids).values_list("id", flat=True)
    )
    unknown = set(attendee_member_ids) - valid_ids
    if unknown:
        raise ValueError("Katılımcılar aktif kurulun üyeleri arasından seçilmelidir.")
    _check_quorum(committee, len(valid_ids))
    _check_conflicts(case, committee.members.filter(pk__in=valid_ids))

    meeting = DisciplineMeeting(case=case, event=event, meeting_date=meeting_date, notes=notes)
    meeting.full_clean(exclude=["event"])
    meeting.save()
    if valid_ids:
        meeting.attendees.set(valid_ids)
    return meeting
