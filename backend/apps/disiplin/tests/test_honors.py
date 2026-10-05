"""Onur kurulu + onur belgesi (honors-lite) testleri — md. 159-184.

Kurul kararları (04.10.2026) yalnız toplantı gündeminden verilir: yardımcılar
`recommend`/`award`/`decide_in_meeting` teklifi bir toplantıya alıp karara bağlar.
"""

from __future__ import annotations

from datetime import date

import pytest

from apps.disiplin import selectors, services
from apps.disiplin.models import (
    AgendaItemOutcome,
    CaseStage,
    CouncilAgendaItem,
    HonorCertificate,
    HonorCertificateEventType,
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
    award,
    council_meeting,
    decide_in_meeting,
    ensure_terms,
    recommend,
)
from apps.okul.models import SchoolTerm, SchoolYear

pytestmark = pytest.mark.django_db


def _propose(student_id: int, criterion: str = HonorCriterion.ATTENDANCE) -> HonorCertificate:
    """Aktif yılın 2. dönemine teklif (dönemler yoksa kurulur)."""
    year = SchoolYear.objects.get(is_active=True)
    ensure_terms(year)
    term = SchoolTerm.objects.get(school_year=year, sequence=2)
    return services.propose_honor_certificate(
        student_id=student_id,
        proposer_role=HonorProposerRole.TEACHER,
        school_term_id=term.pk,
        criteria=[criterion],
    )


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
    cert = _propose(StudentFactory().pk)
    assert cert.status == HonorCertificateStatus.PROPOSED
    # Uygun görüş olmadan Ödül ve Disiplin Kurulu gündemine alınamaz.
    odk = council_meeting(cert.school_year, council_type="DISCIPLINE", on=date(2026, 6, 1))
    with pytest.raises(ValueError, match="uygun gördüğü"):
        services.add_agenda_items(odk, honor_certificate_ids=[cert.pk])
    item = recommend(cert)
    assert cert.status == HonorCertificateStatus.HONOR_BOARD_RECOMMENDED
    assert cert.recommended_at == item.meeting.meeting_date
    award(cert)
    assert cert.status == HonorCertificateStatus.AWARDED
    assert cert.awarded_at == date(2026, 6, 1)
    # Olay toplantıya açıkça bağlıdır (tarih tahmini yok).
    awarded = cert.events.get(event_type=HonorCertificateEventType.AWARDED)
    assert awarded.meeting is not None
    assert awarded.meeting.council_type == "DISCIPLINE"


def test_iki_kurulun_olumsuz_karari_ayri_durumdur() -> None:
    """Onur Kurulu uygun görmez → HONOR_BOARD_DECLINED; ÖDK reddeder → COMMITTEE_REJECTED."""
    year = SchoolYearFactory()
    first = _propose(StudentFactory().pk)
    board = council_meeting(year, council_type="HONOR", on=date(2026, 5, 25))
    item = services.add_agenda_items(board, honor_certificate_ids=[first.pk])[0]
    with pytest.raises(ValueError, match="gerekçesi zorunlu"):
        services.decide_agenda_item(item, outcome="UNFAVORABLE")
    # Gerekçesiz deneme geri sarıldı: teklif ve madde karar bekliyor.
    first.refresh_from_db()
    item.refresh_from_db()
    assert first.status == HonorCertificateStatus.PROPOSED
    assert item.outcome == AgendaItemOutcome.PENDING

    services.decide_agenda_item(item, outcome="UNFAVORABLE", decision_text="Somut dayanak yok.")
    first.refresh_from_db()
    assert first.status == HonorCertificateStatus.HONOR_BOARD_DECLINED
    assert first.rejection_reason == "Somut dayanak yok."

    second = _propose(StudentFactory().pk, HonorCriterion.MANNERS)
    recommend(second)
    decide_in_meeting(
        second,
        council_type="DISCIPLINE",
        on=date(2026, 6, 1),
        favorable=False,
        reason="Ölçüt karşılanmıyor.",
    )
    assert second.status == HonorCertificateStatus.COMMITTEE_REJECTED
    assert second.events.filter(event_type=HonorCertificateEventType.COMMITTEE_REJECTED).exists()


def test_odk_karari_uygun_gorusten_once_olamaz() -> None:
    SchoolYearFactory()
    cert = _propose(StudentFactory().pk)
    recommend(cert, on=date(2026, 5, 25))
    with pytest.raises(ValueError, match="önceki bir tarihte"):
        award(cert, on=date(2026, 5, 20))


def test_gundem_kurallari() -> None:
    """Gündem: kurul türü/aşama/yıl uyumu, tek açık madde, genel kurul ve dosya tutanağı reddi."""
    year = SchoolYearFactory()
    cert = _propose(StudentFactory().pk)
    board_meeting = council_meeting(year, council_type="HONOR", on=date(2026, 5, 25))
    services.add_agenda_items(board_meeting, honor_certificate_ids=[cert.pk])
    other = council_meeting(year, council_type="HONOR", on=date(2026, 5, 26))
    with pytest.raises(ValueError, match="başka bir toplantının gündeminde"):
        services.add_agenda_items(other, honor_certificate_ids=[cert.pk])
    with pytest.raises(ValueError, match="en az bir teklif"):
        services.add_agenda_items(other, honor_certificate_ids=[])

    assembly = services.create_council_meeting(
        school_year_id=year.pk,
        council_type="HONOR",
        honor_meeting_kind="GENERAL_ASSEMBLY",
        meeting_date=date(2026, 5, 27),
        attendees=[{"person_name": "Başkan", "attendee_role": "VOTING_MEMBER", "is_chair": True}],
    )
    with pytest.raises(ValueError, match="Onur Genel Kurulu"):
        services.add_agenda_items(assembly, honor_certificate_ids=[cert.pk])

    other_year = SchoolYear.objects.create(
        name="2026-2027",
        start_date=date(2026, 9, 7),
        end_date=date(2027, 6, 25),
        is_active=False,
    )
    other_cert = HonorCertificate.objects.create(
        student=StudentFactory(),
        school_year=other_year,
        proposer_role=HonorProposerRole.TEACHER,
        criteria=[HonorCriterion.MANNERS],
    )
    with pytest.raises(ValueError, match="aynı ders yılına"):
        services.add_agenda_items(other, honor_certificate_ids=[other_cert.pk])

    # Bekleyen madde gündemden çıkarılır, başka toplantıya alınabilir.
    pending = CouncilAgendaItem.objects.get(meeting=board_meeting, honor_certificate=cert)
    services.remove_agenda_item(pending)
    services.add_agenda_items(other, honor_certificate_ids=[cert.pk])
    candidates = selectors.honor_agenda_candidates(council_type="HONOR", school_year_id=year.pk)
    assert cert not in list(candidates)


def test_odk_yeter_sayi_yoksa_karar_verilemez() -> None:
    """md. 191/1: kurul (başkan + 2 asıl üye = 3) en az 2 oy hakkı olan katılımcıyla toplanır."""
    year = SchoolYearFactory()
    cert = _propose(StudentFactory().pk)
    recommend(cert)
    thin = council_meeting(year, council_type="DISCIPLINE", on=date(2026, 6, 1), voting=1)
    item = services.add_agenda_items(thin, honor_certificate_ids=[cert.pk])[0]
    quorum = services.meeting_quorum(thin)
    assert quorum == {"full": 3, "required": 2, "present": 1, "ok": False}
    with pytest.raises(ValueError, match="yeter sayısı yok"):
        services.decide_agenda_item(item, outcome="FAVORABLE")
    cert.refresh_from_db()
    assert cert.status == HonorCertificateStatus.HONOR_BOARD_RECOMMENDED

    # Katılımcı tamamlanınca karar verilir; karara bağlı toplantıda yeter sayı bozulamaz.
    committee = thin.discipline_committee
    assert committee is not None
    full = [
        {
            "person_name": committee.chair.full_name,
            "attendee_role": "VOTING_MEMBER",
            "is_chair": True,
        },
        {"person_name": "Üye 1", "attendee_role": "VOTING_MEMBER", "is_chair": False},
    ]
    services.update_council_meeting(thin, attendees=full)
    services.decide_agenda_item(item, outcome="FAVORABLE")
    with pytest.raises(ValueError, match="yeter sayısı yok"):
        services.update_council_meeting(thin, attendees=full[:1])


def test_karara_bagli_toplanti_silinemez_tarihi_degismez() -> None:
    year = SchoolYearFactory()
    cert = _propose(StudentFactory().pk)
    item = recommend(cert)
    meeting = item.meeting
    with pytest.raises(ValueError, match="silinemez"):
        services.delete_council_meeting(meeting)
    with pytest.raises(ValueError, match="tarihi değiştirilemez"):
        services.update_council_meeting(meeting, meeting_date=date(2026, 5, 26))
    with pytest.raises(ValueError, match="zaten karara bağlandı"):
        services.decide_agenda_item(item, outcome="UNFAVORABLE", decision_text="x")
    with pytest.raises(ValueError, match="çıkarılamaz"):
        services.remove_agenda_item(item)
    # Bekleyen maddeli toplantı silinir; madde de düşer.
    other = _propose(StudentFactory().pk, HonorCriterion.MANNERS)
    empty = council_meeting(year, council_type="HONOR", on=date(2026, 5, 27))
    services.add_agenda_items(empty, honor_certificate_ids=[other.pk])
    services.delete_council_meeting(empty)
    assert not CouncilAgendaItem.objects.filter(honor_certificate=other).exists()


def test_onur_listesi_iki_belge_ister() -> None:
    year = SchoolYearFactory()
    student = StudentFactory()

    def _award(criterion: str) -> None:
        c = _propose(student.pk, criterion)
        recommend(c)
        award(c)

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

    recommend(proposal, on=date(2026, 6, 15))
    award(proposal, on=date(2026, 6, 18))
    assert [c.pk for c in selectors.principal_pending()["honor_certificates"]] == [proposal.pk]
    services.approve_honor_proposal_by_principal(
        proposal,
        decided_on=date(2026, 6, 19),
        explanation="Uygundur.",
    )
    proposal.refresh_from_db()
    assert proposal.status == HonorCertificateStatus.PRINCIPAL_APPROVED
    assert proposal.principal_decided_at == date(2026, 6, 19)
    assert selectors.principal_pending()["honor_certificates"] == []


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
    cert = _propose(student_id)
    recommend(cert)
    award(cert)
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
    SchoolYearFactory()
    cert = _awarded_certificate(StudentFactory().pk)
    committee_item = CouncilAgendaItem.objects.get(
        honor_certificate=cert, meeting__council_type="DISCIPLINE"
    )
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
    # Geri alınan kararın gündem maddesi aynı toplantıda yeniden karar bekler.
    committee_item.refresh_from_db()
    assert committee_item.outcome == AgendaItemOutcome.PENDING

    # Ret → uygun görüşe döner; müdür onayı geri alınamaz.
    services.decide_agenda_item(committee_item, outcome="UNFAVORABLE", decision_text="x")
    cert.refresh_from_db()
    assert cert.status == HonorCertificateStatus.COMMITTEE_REJECTED
    services.undo_honor_certificate_step(cert, reason="Ret hatalı.", undone_on=date(2026, 6, 4))
    cert.refresh_from_db()
    assert cert.status == HonorCertificateStatus.HONOR_BOARD_RECOMMENDED
    assert cert.rejection_reason == ""
    committee_item.refresh_from_db()
    services.decide_agenda_item(committee_item, outcome="FAVORABLE")
    cert.refresh_from_db()
    services.reject_honor_proposal_by_principal(cert, decided_on=date(2026, 6, 6), reason="y")
    services.undo_honor_certificate_step(cert, reason="Müdür vazgeçti.", undone_on=date(2026, 6, 7))
    cert.refresh_from_db()
    assert cert.status == HonorCertificateStatus.AWARDED
    services.approve_honor_proposal_by_principal(cert, decided_on=date(2026, 6, 8))
    with pytest.raises(ValueError, match="geri alınamaz"):
        services.undo_honor_certificate_step(cert, reason="z")


def test_uygun_gorus_geri_alinamaz_odk_gundemindeyken() -> None:
    year = SchoolYearFactory()
    cert = _propose(StudentFactory().pk)
    board_item = recommend(cert)
    odk = council_meeting(year, council_type="DISCIPLINE", on=date(2026, 6, 1))
    services.add_agenda_items(odk, honor_certificate_ids=[cert.pk])
    with pytest.raises(ValueError, match="gündeminde karar bekliyor"):
        services.undo_honor_certificate_step(cert, reason="Hatalı uygun görüş.")
    services.remove_agenda_item(CouncilAgendaItem.objects.get(meeting=odk))
    services.undo_honor_certificate_step(cert, reason="Hatalı uygun görüş.")
    cert.refresh_from_db()
    board_item.refresh_from_db()
    assert cert.status == HonorCertificateStatus.PROPOSED
    assert board_item.outcome == AgendaItemOutcome.PENDING


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


def test_gundem_api_akisi() -> None:
    """Toplantı aç (gündemli) → madde kararı → yeter sayı/çizelge; eski karar uçları yok."""
    from rest_framework.test import APIClient

    year = SchoolYearFactory()
    ensure_terms(year)
    cert = _propose(StudentFactory().pk)
    client = APIClient()
    base = "/api/v1/council/meetings/"

    for old in ("recommend", "award", "reject"):
        resp = client.post(f"/api/v1/honor/certificates/{cert.pk}/{old}/", {}, format="json")
        assert resp.status_code == 404

    candidates = client.get(f"{base}agenda-candidates/", {"council_type": "HONOR"}).json()
    assert [c["id"] for c in candidates] == [cert.pk]

    created = client.post(
        base,
        {
            "school_year": year.pk,
            "council_type": "HONOR",
            "meeting_date": "2026-05-25",
            "attendees": [
                {"person_name": "Başkan", "attendee_role": "VOTING_MEMBER", "is_chair": True}
            ],
            "honor_certificate_ids": [cert.pk],
        },
        format="json",
    )
    assert created.status_code == 201, created.content
    meeting = created.json()
    assert meeting["quorum"] is None  # Onur Kurulunda yeter sayı hükmü yok
    item = meeting["agenda_items"][0]
    assert item["outcome_display"] == "Karar bekliyor"
    decide_url = f"{base}{meeting['id']}/agenda-items/{item['id']}/decide/"
    bad = client.post(decide_url, {"outcome": "UNFAVORABLE"}, format="json")
    assert bad.status_code == 400
    ok = client.post(
        decide_url, {"outcome": "FAVORABLE", "decision_basis": "MAJORITY"}, format="json"
    )
    assert ok.status_code == 200, ok.content
    decided = ok.json()["agenda_items"][0]
    assert decided["outcome_display"] == "Uygun görüldü"
    assert decided["decision_basis"] == "MAJORITY"
    assert client.delete(f"{base}{meeting['id']}/").status_code == 400

    pdf = client.post(
        "/api/v1/honor/documents/recommendation-record/", {"meeting": meeting["id"]}, format="json"
    )
    assert pdf.status_code == 200
    assert pdf["Content-Type"] == "application/pdf"
    minutes = client.get(f"{base}{meeting['id']}/minutes/")
    assert minutes.status_code == 200

    pending = client.get("/api/v1/disiplin/mudur-onayi-bekleyenler/").json()
    assert pending == {"honor_certificates": [], "decisions": []}


def test_0012_veri_gocu_ret_ayrimi_ve_gundem_doldurma() -> None:
    """Eski REJECTED kaydı hangi kurulda alındıysa ona ayrılır; toplantılı karar gündeme dolar."""
    import importlib

    from django.apps import apps as django_apps

    from apps.disiplin.models import HonorCertificateEvent

    migration = importlib.import_module("apps.disiplin.migrations.0012_council_agenda")
    year = SchoolYearFactory()
    ensure_terms(year)
    board_meeting = council_meeting(year, council_type="HONOR", on=date(2026, 5, 25))

    def legacy(status: str, events: list[tuple[str, object]]) -> HonorCertificate:
        cert: HonorCertificate = HonorCertificate.objects.create(
            student=StudentFactory(),
            school_year=year,
            proposer_role=HonorProposerRole.TEACHER,
            criteria=[HonorCriterion.MANNERS],
            status=status,
            recommended_at=date(2026, 5, 25)
            if any(e == "RECOMMENDED" for e, _ in events)
            else None,
            rejection_reason="eski gerekçe" if status == "REJECTED" else "",
        )
        for event_type, meeting in events:
            HonorCertificateEvent.objects.create(
                certificate=cert,
                event_type=event_type,
                event_date=date(2026, 5, 25),
                meeting=meeting,
            )
        return cert

    declined = legacy("REJECTED", [("PROPOSED", None), ("REJECTED", board_meeting)])
    committee_rejected = legacy(
        "REJECTED", [("PROPOSED", None), ("RECOMMENDED", board_meeting), ("REJECTED", None)]
    )
    # Uygun görüş geri alınıp ret verilmiş: ret Onur Kurulunundur.
    undone_then_declined = legacy(
        "REJECTED",
        [("PROPOSED", None), ("RECOMMENDED", None), ("UNDONE", None), ("REJECTED", None)],
    )

    migration._split_and_backfill(django_apps, None)

    for cert in (declined, committee_rejected, undone_then_declined):
        cert.refresh_from_db()
    assert declined.status == HonorCertificateStatus.HONOR_BOARD_DECLINED
    assert committee_rejected.status == HonorCertificateStatus.COMMITTEE_REJECTED
    assert undone_then_declined.status == HonorCertificateStatus.HONOR_BOARD_DECLINED
    assert not HonorCertificateEvent.objects.filter(event_type="REJECTED").exists()

    declined_item = CouncilAgendaItem.objects.get(honor_certificate=declined)
    assert declined_item.meeting_id == board_meeting.pk
    assert declined_item.outcome == AgendaItemOutcome.UNFAVORABLE
    assert declined_item.decision_text == "eski gerekçe"
    recommended_item = CouncilAgendaItem.objects.get(honor_certificate=committee_rejected)
    assert recommended_item.outcome == AgendaItemOutcome.FAVORABLE
    assert not CouncilAgendaItem.objects.filter(honor_certificate=undone_then_declined).exists()
