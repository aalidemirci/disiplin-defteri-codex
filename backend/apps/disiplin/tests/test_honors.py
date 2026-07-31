"""Onur kurulu + onur belgesi (honors-lite) testleri — md. 159-184."""

from __future__ import annotations

from datetime import date

import pytest

from apps.disiplin import selectors, services
from apps.disiplin.models import (
    CaseStage,
    HonorCertificateStatus,
    HonorCriterion,
    HonorProposerRole,
    PrincipalDecision,
)
from apps.disiplin.tests.factories import PersonnelFactory, SchoolYearFactory, StudentFactory
from apps.okul.models import SchoolTerm

pytestmark = pytest.mark.django_db


def test_onur_kurulu_yil_basina_tek_ve_uye_dup() -> None:
    year = SchoolYearFactory()
    chair = PersonnelFactory()
    board = services.create_honor_board(school_year_id=year.pk, chair_id=chair.pk)
    with pytest.raises(ValueError, match="zaten"):
        services.create_honor_board(school_year_id=year.pk, chair_id=chair.pk)
    student = StudentFactory(class_level=11, class_section="A")
    assembly_member = services.add_general_assembly_member(
        school_year_id=year.pk,
        student_id=student.pk,
        effective_from=year.start_date,
    )
    services.add_honor_board_member(
        board,
        student_id=student.pk,
        grade_level=11,
        is_second_chair=True,
        assembly_member_id=assembly_member.pk,
    )
    with pytest.raises(ValueError, match="zaten üye"):
        services.add_honor_board_member(board, student_id=student.pk)


def test_teklif_bir_veya_birden_fazla_kriter_kabul_eder() -> None:
    SchoolYearFactory()
    student = StudentFactory()
    certificate = services.propose_honor_certificate(
        student_id=student.pk,
        proposer_role=HonorProposerRole.TEACHER,
        criteria=[HonorCriterion.LANGUAGE, HonorCriterion.MANNERS],
    )
    assert certificate.criteria == [HonorCriterion.LANGUAGE, HonorCriterion.MANNERS]
    with pytest.raises(ValueError, match="En az bir"):
        services.propose_honor_certificate(
            student_id=student.pk,
            proposer_role=HonorProposerRole.TEACHER,
            criteria=[],
        )
    with pytest.raises(ValueError, match="Geçersiz onur kriteri"):
        services.propose_honor_certificate(
            student_id=student.pk,
            proposer_role=HonorProposerRole.TEACHER,
            criteria=["UYDURUK"],
        )


def test_davranis_puani_dusen_ogrenciye_teklif_edilemez() -> None:
    SchoolYearFactory()
    student = StudentFactory()
    case = services.create_case(
        petition_date=date(2026, 5, 18),
        petitioner_name="A",
        petitioner_role="IDARE",
        summary="x",
        student_ids=[student.pk],
    )
    services.add_event(
        case,
        CaseStage.DECIDED,
        date(2026, 5, 19),
        override=True,
        override_reason="atla",
        principal_decisions=[PrincipalDecision.DISCIPLINE_COMMITTEE],
    )
    services.record_decision(
        case, student_id=student.pk, penalty_type="REPRIMAND", decision_date=date(2026, 5, 22)
    )
    assert selectors.is_eligible_for_honor(student.pk) is False
    with pytest.raises(ValueError, match="davranış puanı"):
        services.propose_honor_certificate(
            student_id=student.pk,
            proposer_role=HonorProposerRole.TEACHER,
            criteria=[HonorCriterion.MANNERS],
        )


def test_durum_makinesi_teklif_uygun_gorus_belge() -> None:
    SchoolYearFactory()
    student = StudentFactory()
    cert = services.propose_honor_certificate(
        student_id=student.pk,
        proposer_role=HonorProposerRole.TEACHER,
        criteria=[HonorCriterion.ATTENDANCE],
        justification="Devam örnekliği.",
        proposer_name="AYŞE ÖĞRETMEN",
    )
    assert cert.status == HonorCertificateStatus.PROPOSED
    # Doğrudan AWARDED yapılamaz.
    with pytest.raises(ValueError, match="uygun gördüğü"):
        services.award_honor_certificate(cert, awarded_on=date(2026, 6, 1))
    services.recommend_honor_certificate(cert, recommended_on=date(2026, 5, 25))
    cert.refresh_from_db()
    assert cert.status == HonorCertificateStatus.HONOR_BOARD_RECOMMENDED
    services.award_honor_certificate(cert, awarded_on=date(2026, 6, 1))
    cert.refresh_from_db()
    assert cert.status == HonorCertificateStatus.AWARDED
    # Terminal: ret artık mümkün değil.
    with pytest.raises(ValueError, match="reddedilebilir"):
        services.reject_honor_certificate(cert, reason="x", decided_on=date(2026, 6, 2))


def test_ret_gerekce_ister_ve_terminaldir() -> None:
    SchoolYearFactory()
    student = StudentFactory()
    cert = services.propose_honor_certificate(
        student_id=student.pk,
        proposer_role=HonorProposerRole.STUDENT,
        criteria=[HonorCriterion.MANNERS],
    )
    with pytest.raises(ValueError, match="gerekçe"):
        services.reject_honor_certificate(cert, reason=" ", decided_on=date(2026, 5, 25))
    services.reject_honor_certificate(
        cert, reason="Somut dayanak yok.", decided_on=date(2026, 5, 25)
    )
    cert.refresh_from_db()
    assert cert.status == HonorCertificateStatus.REJECTED
    with pytest.raises(ValueError, match="teklif aşamasındaki"):
        services.recommend_honor_certificate(cert, recommended_on=date(2026, 5, 26))


def test_onur_listesi_iki_belge_ister() -> None:
    year = SchoolYearFactory()
    student = StudentFactory()

    def _award(criterion: str) -> None:
        c = services.propose_honor_certificate(
            student_id=student.pk,
            proposer_role=HonorProposerRole.ADMINISTRATION,
            criteria=[criterion],
        )
        services.recommend_honor_certificate(c, recommended_on=date(2026, 5, 25))
        services.award_honor_certificate(c, awarded_on=date(2026, 6, 1))

    _award(HonorCriterion.MANNERS)
    assert selectors.honor_list_for_year(year.pk) == []  # tek belge yetmez (md. 161/2)
    _award(HonorCriterion.ATTENDANCE)
    assert selectors.honor_list_for_year(year.pk) == [student.pk]


def test_donemli_teklif_kurul_karari_ve_mudur_onayi() -> None:
    year = SchoolYearFactory()
    term = SchoolTerm.objects.create(
        school_year=year,
        sequence=2,
        start_date=date(2026, 2, 2),
        end_date=year.end_date,
    )
    student = StudentFactory()

    with pytest.raises(ValueError, match="dönem seçilmelidir"):
        services.propose_honor_certificate(
            student_id=student.pk,
            proposer_role=HonorProposerRole.TEACHER,
            criteria=[HonorCriterion.MANNERS],
        )

    proposal = services.propose_honor_certificate(
        student_id=student.pk,
        proposer_role=HonorProposerRole.TEACHER,
        school_term_id=term.pk,
        criteria=[HonorCriterion.MANNERS],
    )
    assert proposal.school_term_id == term.pk

    services.recommend_honor_certificate(proposal, recommended_on=date(2026, 6, 15))
    services.award_honor_certificate(proposal, awarded_on=date(2026, 6, 18))
    services.approve_honor_proposal_by_principal(
        proposal,
        decided_on=date(2026, 6, 19),
        explanation="Uygundur.",
    )
    proposal.refresh_from_db()
    assert proposal.status == HonorCertificateStatus.PRINCIPAL_APPROVED
    assert proposal.principal_decided_at == date(2026, 6, 19)
