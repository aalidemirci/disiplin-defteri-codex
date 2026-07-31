"""Kurul tanımı + dosya toplantısı + karar defteri testleri (F2) — md. 184-192, 206."""

from __future__ import annotations

from datetime import date

import pytest

from apps.disiplin import services
from apps.disiplin.models import (
    CaseStage,
    CommitteeMemberType,
    CouncilAttendeeRole,
    CouncilMinutesType,
    CouncilType,
    DisciplineCase,
    PrincipalDecision,
)
from apps.disiplin.tests.factories import (
    DisciplineCommitteeFactory,
    PersonnelFactory,
    SchoolYearFactory,
    StudentFactory,
)
from apps.okul.services.terms import configure_terms

pytestmark = pytest.mark.django_db


def _committee_case() -> tuple[DisciplineCase, int]:
    SchoolYearFactory()
    s = StudentFactory()
    case = services.create_case(
        petition_date=date(2026, 5, 18),
        petitioner_name="A",
        petitioner_role="IDARE",
        summary="x",
        student_ids=[s.pk],
    )
    services.add_event(
        case,
        CaseStage.DECIDED,
        date(2026, 5, 19),
        override=True,
        override_reason="atla",
        principal_decisions=[PrincipalDecision.DISCIPLINE_COMMITTEE],
    )
    return case, s.pk


# ---------------------------------------------------------------------------
# Kurul tanımı (md. 185-188)
# ---------------------------------------------------------------------------
def test_kurul_olustur_yil_basina_tek() -> None:
    year = SchoolYearFactory()
    chair = PersonnelFactory(title="Müdür Yardımcısı")
    committee = services.create_committee(school_year_id=year.pk, chair_id=chair.pk)
    assert committee.chair_id == chair.pk
    with pytest.raises(ValueError, match="zaten"):
        services.create_committee(school_year_id=year.pk, chair_id=chair.pk)


def test_uye_ekleme_uc_tipte_ve_dup_engeli() -> None:
    committee = DisciplineCommitteeFactory()
    teacher = PersonnelFactory()
    student = StudentFactory()
    services.add_committee_member(
        committee, member_type=CommitteeMemberType.TEACHER, person_id=teacher.pk
    )
    services.add_committee_member(
        committee, member_type=CommitteeMemberType.STUDENT, person_id=student.pk
    )
    veli = services.add_committee_member(
        committee, member_type=CommitteeMemberType.PARENT, member_name="HASAN VELİ"
    )
    assert veli.member_name == "HASAN VELİ"
    assert committee.members.count() == 3
    with pytest.raises(ValueError, match="zaten üye"):
        services.add_committee_member(
            committee, member_type=CommitteeMemberType.TEACHER, person_id=teacher.pk
        )
    with pytest.raises(ValueError, match="zaten üye"):
        services.add_committee_member(
            committee, member_type=CommitteeMemberType.PARENT, member_name="HASAN VELİ"
        )


def test_veli_uye_ad_zorunlu() -> None:
    committee = DisciplineCommitteeFactory()
    with pytest.raises(ValueError, match="ad-soyad"):
        services.add_committee_member(
            committee, member_type=CommitteeMemberType.PARENT, member_name="  "
        )


# ---------------------------------------------------------------------------
# Dosya toplantısı (md. 191)
# ---------------------------------------------------------------------------
def test_toplanti_katilanlar_aktif_kurul_uyesi_olmali() -> None:
    case, _sid = _committee_case()
    aktif_yil = SchoolYearFactory()  # django_get_or_create: _committee_case'in yılı
    committee = services.create_committee(
        school_year_id=aktif_yil.pk, chair_id=PersonnelFactory().pk
    )
    uye = services.add_committee_member(
        committee, member_type=CommitteeMemberType.TEACHER, person_id=PersonnelFactory().pk
    )
    meeting = services.record_meeting(
        case, meeting_date=date(2026, 5, 25), attendee_member_ids=[uye.pk]
    )
    assert meeting.attendees.count() == 1
    with pytest.raises(ValueError, match="kurulun üyeleri"):
        services.record_meeting(
            case, meeting_date=date(2026, 5, 26), attendee_member_ids=[uye.pk, 99999]
        )


def test_toplanti_aktif_kurul_yoksa_hata() -> None:
    case, _sid = _committee_case()
    with pytest.raises(ValueError, match="disiplin kurulu yok"):
        services.record_meeting(case, meeting_date=date(2026, 5, 25), attendee_member_ids=[])


# ---------------------------------------------------------------------------
# Karar defteri (md. 184/206)
# ---------------------------------------------------------------------------
def _attendees() -> list[dict[str, object]]:
    return [
        {
            "person_name": "ALİ ÖRNEK",
            "title": "Kurul Başkanı",
            "attendee_role": CouncilAttendeeRole.VOTING_MEMBER,
            "is_chair": True,
        },
        {
            "person_name": "AYŞE ÖĞRETMEN",
            "attendee_role": CouncilAttendeeRole.VOTING_MEMBER,
            "is_chair": False,
        },
    ]


def test_karar_defteri_no_yil_tur_basina_artar() -> None:
    year = SchoolYearFactory()
    configure_terms(
        year,
        first_end=date(2026, 1, 16),
        second_start=date(2026, 2, 2),
    )
    m1 = services.create_council_meeting(
        school_year_id=year.pk,
        council_type=CouncilType.DISCIPLINE,
        meeting_date=date(2026, 5, 25),
        attendees=_attendees(),
        decision_text="Gündem görüşüldü.",
    )
    m2 = services.create_council_meeting(
        school_year_id=year.pk,
        council_type=CouncilType.DISCIPLINE,
        meeting_date=date(2026, 6, 25),
        attendees=_attendees(),
    )
    honor = services.create_council_meeting(
        school_year_id=year.pk,
        council_type=CouncilType.HONOR,
        meeting_date=date(2026, 5, 25),
        attendees=_attendees(),
    )
    assert (m1.meeting_no, m2.meeting_no) == (1, 2)
    assert honor.meeting_no == 1  # tür başına ayrı seri
    assert m1.meeting_no_display == "T001"


def test_silinen_tutanagin_numarasi_tekrarlanmaz() -> None:
    year = SchoolYearFactory()
    m1 = services.create_council_meeting(
        school_year_id=year.pk,
        council_type=CouncilType.DISCIPLINE,
        meeting_date=date(2026, 5, 25),
        attendees=_attendees(),
    )
    services.delete_council_meeting(m1)
    m2 = services.create_council_meeting(
        school_year_id=year.pk,
        council_type=CouncilType.DISCIPLINE,
        meeting_date=date(2026, 6, 25),
        attendees=_attendees(),
    )
    assert m2.meeting_no == 2  # defter numarası atlar, tekrar etmez


def test_katilimci_dogrulama_kurallari() -> None:
    year = SchoolYearFactory()
    with pytest.raises(ValueError, match="En az bir katılımcı"):
        services.create_council_meeting(
            school_year_id=year.pk,
            council_type=CouncilType.DISCIPLINE,
            meeting_date=date(2026, 5, 25),
            attendees=[],
        )
    with pytest.raises(ValueError, match="bir başkan"):
        services.create_council_meeting(
            school_year_id=year.pk,
            council_type=CouncilType.DISCIPLINE,
            meeting_date=date(2026, 5, 25),
            attendees=[
                {
                    "person_name": "A",
                    "attendee_role": CouncilAttendeeRole.VOTING_MEMBER,
                    "is_chair": False,
                }
            ],
        )


def test_dosya_gorusme_tutanagi_kurallari() -> None:
    case, sid = _committee_case()
    year = SchoolYearFactory()
    # Kararsız dosyaya CASE_REVIEW bağlanamaz.
    with pytest.raises(ValueError, match="resmî karar yok"):
        services.create_council_meeting(
            school_year_id=year.pk,
            council_type=CouncilType.DISCIPLINE,
            meeting_date=date(2026, 5, 25),
            attendees=_attendees(),
            minutes_type=CouncilMinutesType.CASE_REVIEW,
            discipline_case_id=case.pk,
        )
    services.record_decision(
        case, student_id=sid, penalty_type="REPRIMAND", decision_date=date(2026, 5, 22)
    )
    meeting = services.create_council_meeting(
        school_year_id=year.pk,
        council_type=CouncilType.DISCIPLINE,
        meeting_date=date(2026, 5, 25),
        attendees=_attendees(),
        minutes_type=CouncilMinutesType.CASE_REVIEW,
        discipline_case_id=case.pk,
    )
    assert meeting.discipline_case_id == case.pk
    assert case.case_no in meeting.agenda  # gündem otomatik dolduruldu


def test_prefill_attendees_aktif_kuruldan() -> None:
    year = SchoolYearFactory()
    chair = PersonnelFactory()
    committee = services.create_committee(school_year_id=year.pk, chair_id=chair.pk)
    services.add_committee_member(
        committee, member_type=CommitteeMemberType.TEACHER, person_id=PersonnelFactory().pk
    )
    taslak = services.prefill_attendees(CouncilType.DISCIPLINE)
    assert len(taslak) == 2
    assert taslak[0]["is_chair"] is True
    assert taslak[0]["person_name"] == chair.full_name
