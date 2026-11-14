"""Disiplin test fabrikaları — okul sicili + disiplin çekirdeği.

OYS `ogrenci_isleri/tests/factories.py` uyarlaması: User/Parent fabrikaları
yerine `Personnel`; Student düzleştirilmiş modeldir (Enrollment yok).
"""

from __future__ import annotations

from datetime import date
from typing import Any

import factory

from apps.disiplin.models import (
    CaseStage,
    CouncilAgendaItem,
    CouncilMeeting,
    DisciplineCase,
    DisciplineCommittee,
    DisciplineCommitteeMember,
    DisciplineDecision,
    DisciplineDecisionType,
    DisciplineMeeting,
    HonorBoard,
    HonorCertificate,
    PetitionerRole,
)
from apps.okul.models import Personnel, SchoolYear, Student


class SchoolYearFactory(factory.django.DjangoModelFactory):  # type: ignore[misc]  # factory_boy tip stub'ı yok; taban Any
    class Meta:
        model = SchoolYear
        django_get_or_create = ("name",)

    name = "2025-2026"
    start_date = date(2025, 9, 8)
    end_date = date(2026, 6, 26)
    is_active = True


class StudentFactory(factory.django.DjangoModelFactory):  # type: ignore[misc]  # factory_boy tip stub'ı yok; taban Any
    class Meta:
        model = Student

    first_name = "EMRE CAN"
    last_name = factory.Sequence(lambda n: f"YILMAZ{n}")
    student_number = factory.Sequence(lambda n: str(1000 + n))
    class_level = 10
    class_section = "A"


class PersonnelFactory(factory.django.DjangoModelFactory):  # type: ignore[misc]  # factory_boy tip stub'ı yok; taban Any
    class Meta:
        model = Personnel

    first_name = "AYŞE"
    last_name = factory.Sequence(lambda n: f"ÖĞRETMEN{n}")
    title = "Öğretmen"
    branch = "Matematik"


class DisciplineDecisionTypeFactory(factory.django.DjangoModelFactory):  # type: ignore[misc]  # factory_boy tip stub'ı yok; taban Any
    class Meta:
        model = DisciplineDecisionType
        django_get_or_create = ("code",)

    code = factory.Sequence(lambda n: f"KARAR_{n}")
    name = "Kınama"
    is_active = True
    sort_order = 10


class DisciplineCaseFactory(factory.django.DjangoModelFactory):  # type: ignore[misc]  # factory_boy tip stub'ı yok; taban Any
    class Meta:
        model = DisciplineCase

    case_no = factory.Sequence(lambda n: f"2025-2026-{n + 1:04d}")
    petition_date = date(2026, 5, 20)
    petitioner_name = "Veli Veliyev"
    petitioner_role = PetitionerRole.IDARE
    summary = "Sınıf içinde uygunsuz davranış."
    current_stage = CaseStage.PETITION


class DisciplineCommitteeFactory(factory.django.DjangoModelFactory):  # type: ignore[misc]  # factory_boy tip stub'ı yok; taban Any
    class Meta:
        model = DisciplineCommittee

    school_year = factory.SubFactory(SchoolYearFactory)
    chair = factory.SubFactory(PersonnelFactory)


def approve(decision: DisciplineDecision) -> DisciplineDecision:
    """Kararı karar tarihinde onaylar — tebliğden önce ZORUNLU adım (md. 163/2, 169/2)."""
    from apps.disiplin import services

    return services.set_decision_approval(
        decision, approval_status="APPROVED", approved_on=decision.decision_date
    )


# ---------------------------------------------------------------------------
# TOPLANTI ZORUNLU (S8, 14.11.2026): disiplin kararı yalnız kayıtlı, yeter sayılı dosya
# toplantısına bağlı girilir; karar tarihi = toplantı tarihi. Testler gerçek yoldan geçer:
# `decide` önce toplantıyı `services.record_meeting` ile kaydeder, sonra kararı ona bağlar.
# ---------------------------------------------------------------------------
def ensure_meeting(case: DisciplineCase, on: date) -> DisciplineMeeting:
    """Dosyanın `on` tarihli kurul toplantısı; yoksa gerçek servisle kaydedilir.

    Katılanlar: aktif kurulun (yoksa kurulur) dosyada engelli OLMAYAN (md. 191/2) bütün
    üyeleri. Başkan dosyada şikâyetçi / zarar gören ise toplantı vekâletli kaydedilir
    (`chair_absent` + ilk uygun asıl öğretmen üye — md. 188). Kurulda hiç üye yoksa iki
    öğretmen asıl üye eklenir (yeter sayı en az bir katılımcı satırı ister).
    """
    from apps.disiplin import selectors, services
    from apps.disiplin.services.committee import (
        acting_chair_candidates,
        chair_conflicted,
        conflicted_ids,
    )

    existing: DisciplineMeeting | None = case.meetings.filter(meeting_date=on).first()
    if existing is not None:
        return existing
    committee = selectors.get_active_committee()
    if committee is None:
        year = SchoolYear.objects.filter(is_active=True).first()
        if year is None:
            raise ValueError("Aktif ders yılı yok; toplantı kaydedilemez.")
        committee = committee_for(year)
    # Üyeler tazeden sorgulanır: `get_active_committee` önbelleği eklenen üyeyi göstermez.
    members_qs = DisciplineCommitteeMember.objects.filter(committee=committee)
    if not members_qs.exists():
        for _ in range(2):
            services.add_committee_member(
                committee, member_type="TEACHER", person_id=PersonnelFactory().pk
            )
    users, students = conflicted_ids(case)
    attendee_ids = [
        m.pk
        for m in members_qs
        if not (
            (m.member_user_id is not None and m.member_user_id in users)
            or (m.member_student_id is not None and m.member_student_id in students)
        )
    ]
    absent = chair_conflicted(case, committee)
    acting_id: int | None = None
    if absent:
        candidates = acting_chair_candidates(committee, case)
        acting_id = candidates[0].pk if candidates else None
    meeting: DisciplineMeeting = services.record_meeting(
        case,
        meeting_date=on,
        attendee_member_ids=attendee_ids,
        chair_absent=absent,
        acting_chair_member_id=acting_id,
    )
    return meeting


def orm_meeting(
    case: DisciplineCase, on: date, *, attendees: int | None = None
) -> DisciplineMeeting:
    """Servis denetimlerinden GEÇMEDEN (doğrudan ORM) kaydedilmiş toplantı taklidi.

    `record_meeting` sevk tarihini ve yeter sayıyı kayıt anında denetler; eski sürümde
    kaydedilmiş (yeter sayısız / sevk yeniden yapıldığı için sevk öncesinde kalmış) toplantı
    satırı ancak böyle kurulur. `attendees`: katılımcı satırı sayısı (varsayılan: bütün üyeler).
    """
    year = SchoolYear.objects.filter(is_active=True).first() or SchoolYearFactory()
    committee = committee_for(year)
    members = list(DisciplineCommitteeMember.objects.filter(committee=committee))
    meeting: DisciplineMeeting = DisciplineMeeting.objects.create(case=case, meeting_date=on)
    meeting.attendees.set(members if attendees is None else members[:attendees])
    return meeting


def committee_attendees(year: SchoolYear | None = None) -> list[dict[str, object]]:
    """Karar defteri (CouncilMeeting) katılımcıları: yılın kurulunun başkanı + asıl üyeleri."""
    committee = committee_for(year or SchoolYearFactory())
    people = [(committee.chair.full_name, committee.chair_id)] + [
        (m.member_name, m.member_user_id)
        for m in DisciplineCommitteeMember.objects.filter(committee=committee, is_substitute=False)
    ]
    return [
        {
            "person_name": name,
            "attendee_role": "VOTING_MEMBER",
            "is_chair": index == 0,
            "member_user_id": user_id,
        }
        for index, (name, user_id) in enumerate(people)
    ]


def decide(
    case: DisciplineCase,
    *,
    decision_date: date,
    meeting: DisciplineMeeting | None = None,
    **kwargs: Any,
) -> DisciplineDecision:
    """Kararı GERÇEK yoldan girer: o tarihli toplantı (yoksa kaydedilir) + `record_decision`.

    Toplantı kaydedilemiyorsa (kapalı / sevksiz dosya, sevk öncesi tarih…) toplantısız
    çağrıya düşülür: servisin KENDİ reddi (kapalı dosya, sevk yok, toplantı yok) döner.
    """
    from apps.disiplin import services

    if meeting is None:
        try:
            meeting = ensure_meeting(case, decision_date)
        except ValueError:
            return services.record_decision(case, decision_date=decision_date, **kwargs)
    return services.record_decision(case, meeting=meeting, decision_date=decision_date, **kwargs)


def legacy_decision(
    case: DisciplineCase, *, decision_date: date, **kwargs: Any
) -> DisciplineDecision:
    """S8 ÖNCESİ kayıt taklidi: toplantıya bağlı OLMAYAN karar (`meeting IS NULL`).

    Yalnız "toplantısız girilmiş eski karar" durumunu sınayan testlerde kullanılır.
    """
    from apps.disiplin.services.decisions import _create_decision

    return _create_decision(case, decision_date=decision_date, meeting=None, **kwargs)


# ---------------------------------------------------------------------------
# Kurul işleyişi (04.10.2026): kurul kararı toplantının gündem maddesinde verilir.
# ---------------------------------------------------------------------------
def ensure_terms(year: SchoolYear) -> None:
    """Ders yılının iki dönemi yoksa kurar (Onur Kurulu toplantısı dönem ister)."""
    from apps.okul.models import SchoolTerm

    if SchoolTerm.objects.filter(school_year=year).exists():
        return
    SchoolTerm.objects.create(
        school_year=year, sequence=1, start_date=year.start_date, end_date=date(2026, 1, 23)
    )
    SchoolTerm.objects.create(
        school_year=year, sequence=2, start_date=date(2026, 2, 9), end_date=year.end_date
    )


def committee_for(year: SchoolYear) -> DisciplineCommittee:
    """Yılın Ödül ve Disiplin Kurulu; yoksa başkan + iki öğretmen asıl üyeyle kurulur."""
    from apps.disiplin import services

    existing: DisciplineCommittee | None = DisciplineCommittee.objects.filter(
        school_year=year
    ).first()
    if existing is not None:
        return existing
    committee = services.create_committee(school_year_id=year.pk, chair_id=PersonnelFactory().pk)
    for _ in range(2):
        services.add_committee_member(
            committee, member_type="TEACHER", person_id=PersonnelFactory().pk
        )
    return committee


def council_meeting(
    year: SchoolYear, *, council_type: str, on: date, voting: int | None = None
) -> CouncilMeeting:
    """Kurul toplantısı. ÖDK'da katılanlar kurulun başkan + asıl üyeleridir (`voting` ile
    kısaltılabilir — yeter sayı testi); Onur Kurulunda adla bir başkan + bir üye."""
    from apps.disiplin import services

    attendees: list[dict[str, object]]
    if council_type == "DISCIPLINE":
        committee = committee_for(year)
        people = [(committee.chair.full_name, committee.chair_id)] + [
            (m.member_name, m.member_user_id) for m in committee.members.filter(is_substitute=False)
        ]
        attendees = [
            {
                "person_name": name,
                "attendee_role": "VOTING_MEMBER",
                "is_chair": index == 0,
                "member_user_id": user_id,
            }
            for index, (name, user_id) in enumerate(people[: voting or len(people)])
        ]
    else:
        ensure_terms(year)
        # Onur Kurulu tanımlı değilken uygun görüş kararı verilemez (saha denetimi 13.11.2026).
        if not HonorBoard.objects.filter(school_year=year).exists():
            services.create_honor_board(school_year_id=year.pk, chair_id=PersonnelFactory().pk)
        attendees = [
            {"person_name": "Onur Başkanı", "attendee_role": "VOTING_MEMBER", "is_chair": True},
            {"person_name": "Öğrenci Üye", "attendee_role": "VOTING_MEMBER", "is_chair": False},
        ]
    meeting: CouncilMeeting = services.create_council_meeting(
        school_year_id=year.pk, council_type=council_type, meeting_date=on, attendees=attendees
    )
    return meeting


def decide_in_meeting(
    certificate: HonorCertificate,
    *,
    council_type: str,
    on: date,
    favorable: bool = True,
    reason: str = "",
    meeting: CouncilMeeting | None = None,
) -> CouncilAgendaItem:
    """Teklifi bir kurul toplantısının gündemine alıp karara bağlar."""
    from apps.disiplin import services

    if meeting is None:
        meeting = council_meeting(certificate.school_year, council_type=council_type, on=on)
    item = services.add_agenda_items(meeting, honor_certificate_ids=[certificate.pk])[0]
    decided: CouncilAgendaItem = services.decide_agenda_item(
        item, outcome="FAVORABLE" if favorable else "UNFAVORABLE", decision_text=reason
    )
    certificate.refresh_from_db()
    return decided


def recommend(certificate: HonorCertificate, on: date = date(2026, 5, 25)) -> CouncilAgendaItem:
    """Onur Kurulu toplantısında uygun görüş (md. 183/b)."""
    return decide_in_meeting(certificate, council_type="HONOR", on=on)


def award(certificate: HonorCertificate, on: date = date(2026, 6, 1)) -> CouncilAgendaItem:
    """Ödül ve Disiplin Kurulu toplantısında kabul (md. 161/1)."""
    return decide_in_meeting(certificate, council_type="DISCIPLINE", on=on)
