"""14.11.2026 kullanıcı kararları — "kurul" grubu (S5, S6, S13).

- S5: Ödül ve Disiplin Kurulu bileşimi md. 185/1'e uymuyorsa UYARILIR, engellenmez.
  md. 185/1: a) müdürün görevlendireceği müdür yardımcısı, b) öğretmenler kurulunca
  seçilecek iki öğretmen, c) onur kurulu ikinci başkanı, ç) okul-aile birliğinin
  seçeceği bir öğrenci velisi.
- S6: Onur Kurulu, davranış puanı indirilmiş öğrenci için uygun görüş verirken
  UYARILIR (md. 161/1), engellenmez (md. 183/b öneri yetkisi). Ödül ve Disiplin
  Kurulu kabulündeki uygunluk denetimi değişmez.
- S13: yeter sayıya (md. 191/1) girmeyen "oy hakkı olan üye" satırları adlarıyla döner.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.disiplin import services
from apps.disiplin.models import (
    CaseStage,
    CommitteeMemberType,
    CouncilMeeting,
    CouncilMeetingAttendee,
    DisciplineCommittee,
    HonorCertificate,
    HonorCertificateStatus,
    HonorCriterion,
    HonorProposerRole,
    PrincipalDecision,
)
from apps.disiplin.selectors.committee import committee_composition_warnings
from apps.disiplin.services.council import meeting_quorum_detail
from apps.disiplin.tests.factories import (
    PersonnelFactory,
    SchoolYearFactory,
    StudentFactory,
    approve,
    council_meeting,
    ensure_terms,
)
from apps.okul.models import SchoolTerm, SchoolYear, Student

pytestmark = pytest.mark.django_db

MEETINGS = "/api/v1/council/meetings/"


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------
def _second_chair(year: SchoolYear) -> Student:
    """Yılın Onur Kurulunu kurar ve 11. sınıftan asıl ikinci başkanını döner (md. 180)."""
    board = services.create_honor_board(school_year_id=year.pk, chair_id=PersonnelFactory().pk)
    student: Student = StudentFactory(class_level=11, class_section="A")
    services.add_general_assembly_member(
        school_year_id=year.pk, student_id=student.pk, effective_from=year.start_date
    )
    services.add_honor_board_member(board, student_id=student.pk, is_second_chair=True)
    return student


def _add_teacher(committee: DisciplineCommittee, **kwargs: Any) -> None:
    services.add_committee_member(
        committee,
        member_type=CommitteeMemberType.TEACHER,
        person_id=PersonnelFactory().pk,
        **kwargs,
    )


def _full_committee(year: SchoolYear) -> DisciplineCommittee:
    """md. 185/1'e uygun kurul: başkan + iki öğretmen + onur kurulu ikinci başkanı + veli."""
    committee = services.create_committee(school_year_id=year.pk, chair_id=PersonnelFactory().pk)
    _add_teacher(committee)
    _add_teacher(committee)
    services.add_committee_member(
        committee, member_type=CommitteeMemberType.STUDENT, person_id=_second_chair(year).pk
    )
    services.add_committee_member(
        committee, member_type=CommitteeMemberType.PARENT, member_name="HASAN VELİOĞLU"
    )
    return committee


def _chair_row(committee: DisciplineCommittee) -> dict[str, Any]:
    return {
        "person_name": committee.chair.full_name,
        "attendee_role": "VOTING_MEMBER",
        "is_chair": True,
        "member_user_id": committee.chair_id,
    }


def _propose(student_id: int) -> HonorCertificate:
    year = SchoolYear.objects.get(is_active=True)
    ensure_terms(year)
    term = SchoolTerm.objects.get(school_year=year, sequence=2)
    return services.propose_honor_certificate(
        student_id=student_id,
        proposer_role=HonorProposerRole.TEACHER,
        school_term_id=term.pk,
        criteria=[HonorCriterion.MANNERS],
    )


def _penalize(student_id: int) -> None:
    """Öğrenciye onaylı kınama (davranış puanı iner — md. 161/1 uygunluğu düşer)."""
    case = services.create_case(
        petition_date=date(2026, 5, 18),
        petitioner_name="İdare",
        petitioner_role="IDARE",
        summary="olay",
        student_ids=[student_id],
    )
    services.add_event(
        case,
        CaseStage.DECIDED,
        date(2026, 5, 19),
        override=True,
        override_reason="atla",
        principal_decisions=[PrincipalDecision.DISCIPLINE_COMMITTEE],
    )
    approve(
        services.record_decision(
            case, student_id=student_id, penalty_type="REPRIMAND", decision_date=date(2026, 5, 20)
        )
    )


# ---------------------------------------------------------------------------
# S5 — md. 185/1 bileşim uyarıları (uyar, engelleme)
# ---------------------------------------------------------------------------
def test_s5_md185_uygun_kurulda_uyari_yok() -> None:
    year = SchoolYearFactory()
    committee = _full_committee(year)
    assert committee_composition_warnings(committee) == []


def test_s5_eksik_uyeler_turuyle_sayilir() -> None:
    """Yalnız başkanı olan kurul: üç eksik de ayrı ayrı, bendiyle söylenir."""
    year = SchoolYearFactory()
    committee = services.create_committee(school_year_id=year.pk, chair_id=PersonnelFactory().pk)
    warnings = committee_composition_warnings(committee)
    assert len(warnings) == 3
    assert all("md. 185/1" in w for w in warnings)
    assert any("eksik" in w and "öğretmen üye tanımlı değil" in w for w in warnings)
    assert any("eksik" in w and "onur kurulu ikinci başkanı tanımlı değil" in w for w in warnings)
    assert any("eksik" in w and "okul-aile birliği temsilcisi" in w for w in warnings)

    _add_teacher(committee)
    warnings = committee_composition_warnings(committee)
    assert any("iki öğretmen üyeden yalnız biri tanımlı" in w for w in warnings)


def test_s5_fazla_uye_ve_yedekler() -> None:
    """Fazla asıl üye uyarılır; yedek üyeler (md. 186) bileşim sayımına girmez."""
    year = SchoolYearFactory()
    committee = _full_committee(year)
    _add_teacher(committee, is_substitute=True)
    services.add_committee_member(
        committee,
        member_type=CommitteeMemberType.PARENT,
        member_name="IŞIL ÇİÇEK",
        is_substitute=True,
    )
    assert committee_composition_warnings(committee) == []

    _add_teacher(committee)
    services.add_committee_member(
        committee, member_type=CommitteeMemberType.PARENT, member_name="AYŞE YILDIZ"
    )
    warnings = committee_composition_warnings(committee)
    assert len(warnings) == 2
    assert any("fazla" in w and "3 asıl öğretmen üye" in w for w in warnings)
    assert any("fazla" in w and "2 asıl veli üye" in w for w in warnings)


def test_s5_ogrenci_uye_onur_kurulu_ikinci_baskani_degilse_uyarilir() -> None:
    year = SchoolYearFactory()
    committee = services.create_committee(school_year_id=year.pk, chair_id=PersonnelFactory().pk)
    _add_teacher(committee)
    _add_teacher(committee)
    services.add_committee_member(
        committee, member_type=CommitteeMemberType.PARENT, member_name="HASAN VELİOĞLU"
    )
    other: Student = StudentFactory()
    services.add_committee_member(
        committee, member_type=CommitteeMemberType.STUDENT, person_id=other.pk
    )
    warnings = committee_composition_warnings(committee)
    assert len(warnings) == 1
    assert other.full_name in warnings[0]
    assert "Onur Kurulunun ikinci başkanı değil" in warnings[0]
    assert "md. 185/1-c" in warnings[0]


def test_s5_uyari_kurul_yanitinda_doner_ve_kaydi_engellemez() -> None:
    """Kurul ucu `composition_warnings` taşır; eksik kurula üye eklenir, toplantı yazılır."""
    year = SchoolYearFactory()
    client = APIClient()
    created = client.post(
        "/api/v1/discipline/committee/",
        {"school_year": year.pk, "chair": PersonnelFactory().pk},
        format="json",
    )
    assert created.status_code == 201, created.content
    assert len(created.json()["composition_warnings"]) == 3

    added = client.post(
        "/api/v1/discipline/committee/members/",
        {"member_type": "PARENT", "member_name": "HASAN VELİOĞLU"},
        format="json",
    )
    assert added.status_code == 201, added.content
    # Üye eklendikten sonraki yanıt bayat değildir (§7.5): veli uyarısı kalkar.
    warnings = added.json()["composition_warnings"]
    assert len(warnings) == 2
    assert not any("okul-aile birliği" in w for w in warnings)
    assert client.get("/api/v1/discipline/committee/").json()["composition_warnings"] == warnings

    committee = DisciplineCommittee.objects.get(school_year=year)
    meeting = client.post(
        MEETINGS,
        {
            "school_year": year.pk,
            "council_type": "DISCIPLINE",
            "meeting_date": "2026-05-25",
            "attendees": [_chair_row(committee)],
        },
        format="json",
    )
    # Eksik bileşim toplantı kaydını ENGELLEMEZ; toplantı yanıtı aynı uyarıları taşır.
    assert meeting.status_code == 201, meeting.content
    assert meeting.json()["composition_warnings"] == warnings


def test_s5_onur_kurulu_toplantisinda_bilesim_uyarisi_yok() -> None:
    year = SchoolYearFactory()
    services.create_committee(school_year_id=year.pk, chair_id=PersonnelFactory().pk)
    meeting = council_meeting(year, council_type="HONOR", on=date(2026, 5, 25))
    body = APIClient().get(f"{MEETINGS}{meeting.pk}/").json()
    assert body["composition_warnings"] == []


# ---------------------------------------------------------------------------
# S6 — Onur Kurulu: puanı indirilmiş öğrencide uyarı, engel yok
# ---------------------------------------------------------------------------
def test_s6_gundem_maddesi_uygunlugu_tasir_ve_uygun_gorus_verilebilir() -> None:
    year = SchoolYearFactory()
    clean = _propose(StudentFactory().pk)
    penalized = _propose(StudentFactory().pk)
    _penalize(penalized.student_id)  # teklif sonrası ceza: puan indirildi
    meeting = council_meeting(year, council_type="HONOR", on=date(2026, 5, 25))
    services.add_agenda_items(meeting, honor_certificate_ids=[clean.pk, penalized.pk])

    client = APIClient()
    items = {
        item["honor_certificate"]: item
        for item in client.get(f"{MEETINGS}{meeting.pk}/").json()["agenda_items"]
    }
    assert items[clean.pk]["honor_eligible"] is True
    assert items[penalized.pk]["honor_eligible"] is False

    # md. 183/b: Onur Kurulu öneri verir — uygun görüş yine kaydedilir.
    decided = client.post(
        f"{MEETINGS}{meeting.pk}/agenda-items/{items[penalized.pk]['id']}/decide/",
        {"outcome": "FAVORABLE"},
        format="json",
    )
    assert decided.status_code == 200, decided.content
    penalized.refresh_from_db()
    assert penalized.status == HonorCertificateStatus.HONOR_BOARD_RECOMMENDED


def test_s6_odk_kabulundeki_uygunluk_denetimi_degismez() -> None:
    """Uygun görüş verilse de Ödül ve Disiplin Kurulu puanı inen öğrenciyi kabul edemez."""
    from apps.disiplin.tests.factories import decide_in_meeting

    SchoolYearFactory()
    cert = _propose(StudentFactory().pk)
    _penalize(cert.student_id)
    decide_in_meeting(cert, council_type="HONOR", on=date(2026, 5, 25))
    assert cert.status == HonorCertificateStatus.HONOR_BOARD_RECOMMENDED
    with pytest.raises(ValueError, match="davranış puanı indirilmiş"):
        decide_in_meeting(cert, council_type="DISCIPLINE", on=date(2026, 6, 1))


# ---------------------------------------------------------------------------
# S13 — yeter sayıya girmeyen satırlar adlarıyla döner
# ---------------------------------------------------------------------------
def _odk_meeting(year: SchoolYear, committee: DisciplineCommittee) -> CouncilMeeting:
    meeting: CouncilMeeting = services.create_council_meeting(
        school_year_id=year.pk,
        council_type="DISCIPLINE",
        meeting_date=date(2026, 5, 25),
        attendees=[_chair_row(committee)],
    )
    return meeting


def test_s13_eslesmeyen_oy_hakki_satirlari_adlariyla_doner() -> None:
    year = SchoolYearFactory()
    committee = _full_committee(year)
    meeting = _odk_meeting(year, committee)
    # Denetim gelmeden önce kaydedilmiş, kurul listesiyle eşleşmeyen satırlar (eski kayıt).
    for order, (name, role) in enumerate(
        [
            ("Öğr. Kurul Dışı Kişi", "VOTING_MEMBER"),
            ("Davetli Rehber Öğretmen", "NON_VOTING_INVITEE"),
        ],
        start=5,
    ):
        CouncilMeetingAttendee.objects.create(
            meeting=meeting, attendee_role=role, person_name=name, order=order
        )
    detail = meeting_quorum_detail(meeting)
    assert detail == {
        "full": 5,
        "required": 3,
        "present": 1,
        "ok": False,
        "unmatched": ["Öğr. Kurul Dışı Kişi"],  # davetli (md. 185/6) listeye girmez
    }
    # Sayım değişmedi: eski çıktı aynı (yalnız `unmatched` eklendi).
    assert services.meeting_quorum(meeting) == {
        "full": 5,
        "required": 3,
        "present": 1,
        "ok": False,
    }
    body = APIClient().get(f"{MEETINGS}{meeting.pk}/").json()
    assert body["quorum"]["unmatched"] == ["Öğr. Kurul Dışı Kişi"]


def test_s13_eslesmeyen_satir_yoksa_liste_bos_onur_kurulunda_none() -> None:
    year = SchoolYearFactory()
    committee = _full_committee(year)
    meeting = _odk_meeting(year, committee)
    detail = meeting_quorum_detail(meeting)
    assert detail is not None and detail["unmatched"] == []
    honor = council_meeting(year, council_type="HONOR", on=date(2026, 5, 26))
    assert meeting_quorum_detail(honor) is None
