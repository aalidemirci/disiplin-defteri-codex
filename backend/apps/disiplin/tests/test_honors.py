"""Onur kurulu + onur belgesi (honors-lite) testleri — md. 159-184."""

from __future__ import annotations

from datetime import date

import pytest

from apps.disiplin import selectors, services
from apps.disiplin.models import (
    CaseStage,
    HonorCertificate,
    HonorCertificateStatus,
    HonorCriterion,
    HonorProposerRole,
    PrincipalDecision,
)
from apps.disiplin.tests.factories import (
    PersonnelFactory,
    SchoolYearFactory,
    StudentFactory,
    approve,
)
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
    decision = services.record_decision(
        case, student_id=student.pk, penalty_type="REPRIMAND", decision_date=date(2026, 5, 22)
    )
    # Onaysız kurul kararı henüz ceza değildir (md. 163/2) — puan düşmez.
    assert selectors.is_eligible_for_honor(student.pk) is True
    approve(decision)
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


def test_md181_cezali_uye_uyarisi_uyelik_elle_sonlandirilir() -> None:
    """md. 181/1: disiplin cezası alan öğrencinin üyeliği düşer — kullanıcı kararı (B):
    otomatik sonlandırılmaz, aktif üye kaydında uyarı (md181_penalty) döner."""
    from rest_framework.test import APIClient

    from apps.disiplin.serializers import HonorBoardMemberSerializer

    year = SchoolYearFactory()
    board = services.create_honor_board(school_year_id=year.pk, chair_id=PersonnelFactory().pk)
    student = StudentFactory(class_level=11, class_section="A")
    assembly = services.add_general_assembly_member(
        school_year_id=year.pk, student_id=student.pk, effective_from=year.start_date
    )
    board_member = services.add_honor_board_member(
        board, student_id=student.pk, grade_level=11, assembly_member_id=assembly.pk
    )
    client = APIClient()

    def assembly_row() -> dict[str, object]:
        rows = client.get("/api/v1/honor/general-assembly/").json()
        return next(r for r in rows if r["id"] == assembly.pk)

    assert assembly_row()["md181_penalty"] is None

    case = services.create_case(
        petition_date=date(2026, 5, 18),
        petitioner_name="İdare",
        petitioner_role="IDARE",
        summary="olay",
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
    d = services.record_decision(
        case, student_id=student.pk, penalty_type="REPRIMAND", decision_date=date(2026, 5, 20)
    )
    assert assembly_row()["md181_penalty"] is None  # onaysız karar ceza değil
    approve(d)

    warning = assembly_row()["md181_penalty"]
    assert warning == {
        "penalty_type_display": "Kınama",
        "decision_no": d.decision_no,
        "decision_date": "2026-05-20",
    }
    assert assembly_row()["is_active"] is True  # otomatik düşürülmez
    board_member.refresh_from_db()
    assert HonorBoardMemberSerializer(board_member).data["md181_penalty"] is not None

    services.end_general_assembly_membership(
        assembly, effective_until=date(2026, 5, 21), reason="md. 181: disiplin cezası"
    )
    assert assembly_row()["md181_penalty"] is None


def test_md180_onur_kurulu_kompozisyonu() -> None:
    """md. 180/1: her sınıf seviyesinden bir asıl üye; ikinci başkan 11/12. sınıftan;
    sınıf seviyesi sicilden (kullanıcı kararı 26.09.2026 — A: engelle)."""
    year = SchoolYearFactory()
    board = services.create_honor_board(school_year_id=year.pk, chair_id=PersonnelFactory().pk)

    def uye(level: int, section: str) -> int:
        s = StudentFactory(class_level=level, class_section=section)
        services.add_general_assembly_member(
            school_year_id=year.pk, student_id=s.pk, effective_from=year.start_date
        )
        return int(s.pk)

    onuncu = uye(10, "A")
    with pytest.raises(ValueError, match="sicilindeki sınıftan"):
        services.add_honor_board_member(board, student_id=onuncu, grade_level=12)
    with pytest.raises(ValueError, match="İkinci başkan"):
        services.add_honor_board_member(board, student_id=onuncu, is_second_chair=True)
    m = services.add_honor_board_member(board, student_id=onuncu)
    assert m.grade_level == 10  # sicilden

    with pytest.raises(ValueError, match="10. sınıf seviyesinden zaten"):
        services.add_honor_board_member(board, student_id=uye(10, "B"))
    yedek = services.add_honor_board_member(board, student_id=uye(10, "C"), is_substitute=True)
    assert yedek.grade_level == 10  # yedek sınırın dışında

    ikinci_baskan = services.add_honor_board_member(
        board, student_id=uye(11, "A"), is_second_chair=True
    )
    assert ikinci_baskan.is_second_chair and ikinci_baskan.grade_level == 11
    # Görevi sonlanan üyenin yerine aynı seviyeden yenisi seçilebilir.
    services.remove_honor_board_member(m)
    services.add_honor_board_member(board, student_id=uye(10, "D"))


def _awarded_certificate(student_id: int) -> HonorCertificate:
    cert = services.propose_honor_certificate(
        student_id=student_id,
        proposer_role=HonorProposerRole.TEACHER,
        criteria=[HonorCriterion.ATTENDANCE],
    )
    services.recommend_honor_certificate(cert, recommended_on=date(2026, 5, 25))
    services.award_honor_certificate(cert, awarded_on=date(2026, 6, 1))
    return cert


def test_m8_mudur_onayinda_uygunluk_yeniden_denetlenir() -> None:
    """Kurul kabulünden sonra ceza alan öğrenciye onur belgesi onaylanmaz (md. 161, 181/1)."""
    SchoolYearFactory()
    student = StudentFactory()
    cert = _awarded_certificate(student.pk)
    case = services.create_case(
        petition_date=date(2026, 6, 2),
        petitioner_name="İdare",
        petitioner_role="IDARE",
        summary="olay",
        student_ids=[student.pk],
    )
    services.add_event(
        case,
        CaseStage.DECIDED,
        date(2026, 6, 2),
        override=True,
        override_reason="atla",
        principal_decisions=[PrincipalDecision.DISCIPLINE_COMMITTEE],
    )
    approve(
        services.record_decision(
            case, student_id=student.pk, penalty_type="REPRIMAND", decision_date=date(2026, 6, 3)
        )
    )
    with pytest.raises(ValueError, match="onaylanamaz"):
        services.approve_honor_proposal_by_principal(cert, decided_on=date(2026, 6, 5))


def test_m8_son_adim_gerekceyle_geri_alinir() -> None:
    from apps.disiplin.models import HonorCertificateEventType

    SchoolYearFactory()
    cert = _awarded_certificate(StudentFactory().pk)
    with pytest.raises(ValueError, match="gerekçesi zorunlu"):
        services.undo_honor_certificate_step(cert, reason=" ")
    services.undo_honor_certificate_step(cert, reason="Yanlış dosya.", undone_on=date(2026, 6, 2))
    cert.refresh_from_db()
    assert cert.status == HonorCertificateStatus.HONOR_BOARD_RECOMMENDED
    assert cert.awarded_at is None
    last = cert.events.order_by("-id").first()
    assert last is not None
    assert last.event_type == HonorCertificateEventType.UNDONE
    assert last.explanation == "Yanlış dosya."

    # Ret → uygun görüşe döner; müdür onayı geri alınamaz.
    services.reject_honor_certificate(cert, reason="x", decided_on=date(2026, 6, 3))
    services.undo_honor_certificate_step(cert, reason="Ret hatalı.", undone_on=date(2026, 6, 4))
    cert.refresh_from_db()
    assert cert.status == HonorCertificateStatus.HONOR_BOARD_RECOMMENDED
    assert cert.rejection_reason == ""
    services.award_honor_certificate(cert, awarded_on=date(2026, 6, 5))
    services.reject_honor_proposal_by_principal(cert, decided_on=date(2026, 6, 6), reason="y")
    services.undo_honor_certificate_step(cert, reason="Müdür vazgeçti.", undone_on=date(2026, 6, 7))
    cert.refresh_from_db()
    assert cert.status == HonorCertificateStatus.AWARDED
    services.approve_honor_proposal_by_principal(cert, decided_on=date(2026, 6, 8))
    with pytest.raises(ValueError, match="geri alınamaz"):
        services.undo_honor_certificate_step(cert, reason="z")


def test_m8_geri_alma_ucu() -> None:
    from rest_framework.test import APIClient

    SchoolYearFactory()
    cert = _awarded_certificate(StudentFactory().pk)
    client = APIClient()
    url = f"/api/v1/honor/certificates/{cert.pk}/undo/"
    assert client.post(url, {}, format="json").status_code == 400
    resp = client.post(url, {"reason": "Yanlış kayıt."}, format="json")
    assert resp.status_code == 200, resp.content
    assert resp.json()["status"] == HonorCertificateStatus.HONOR_BOARD_RECOMMENDED
