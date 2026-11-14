"""Saha (Windows uçtan uca) testinde bulunan kurul + onur kusurlarının regresyon testleri.

Kapsam: md. 191/1 yeter sayısının kurul dışı ad / yinelenen üye ile doldurulması,
müdür onay tarihi, gelecek tarihli toplantıda karar, ileri tarihli temsilci
değişikliği (md. 178/1), Onur Kurulu başkan/yedek ve ikinci başkan yedeği
(md. 180/1, 182), kurula ait olmayan madde atıfları, sevksiz/kapalı dosyaya
kurul toplantısı ve toplantı kaydının silinmesi.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pytest
from django.utils import timezone

from apps.disiplin import selectors, services
from apps.disiplin.models import (
    CaseStage,
    CommitteeMemberType,
    CouncilMeeting,
    CouncilMeetingAttendee,
    DisciplineCase,
    DisciplineCommittee,
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
    award,
    committee_for,
    decide,
    ensure_terms,
    recommend,
)
from apps.okul.models import SchoolTerm, SchoolYear

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------
def _five_member_committee(year: SchoolYear) -> DisciplineCommittee:
    """Başkan + 4 asıl üye (2 öğretmen, 1 öğrenci, 1 veli) + veli yedeği — tam sayı 5."""
    committee = services.create_committee(school_year_id=year.pk, chair_id=PersonnelFactory().pk)
    for _ in range(2):
        services.add_committee_member(
            committee, member_type=CommitteeMemberType.TEACHER, person_id=PersonnelFactory().pk
        )
    services.add_committee_member(
        committee, member_type=CommitteeMemberType.STUDENT, person_id=StudentFactory().pk
    )
    services.add_committee_member(
        committee, member_type=CommitteeMemberType.PARENT, member_name="HASAN VELİOĞLU"
    )
    services.add_committee_member(
        committee,
        member_type=CommitteeMemberType.PARENT,
        member_name="IŞIL ÇİÇEK",
        is_substitute=True,
    )
    return committee


def _row(
    name: str, *, chair: bool = False, role: str = "VOTING_MEMBER", **fk: int | None
) -> dict[str, Any]:
    return {"person_name": name, "attendee_role": role, "is_chair": chair, **fk}


def _chair_row(committee: DisciplineCommittee) -> dict[str, Any]:
    return _row(committee.chair.full_name, chair=True, member_user_id=committee.chair_id)


def _odk_meeting(year: SchoolYear, attendees: list[dict[str, Any]]) -> CouncilMeeting:
    meeting: CouncilMeeting = services.create_council_meeting(
        school_year_id=year.pk,
        council_type="DISCIPLINE",
        meeting_date=date(2026, 6, 1),
        attendees=attendees,
    )
    return meeting


def _propose(student_id: int) -> HonorCertificate:
    year = SchoolYear.objects.get(is_active=True)
    ensure_terms(year)
    term = SchoolTerm.objects.get(school_year=year, sequence=2)
    return services.propose_honor_certificate(
        student_id=student_id,
        proposer_role=HonorProposerRole.TEACHER,
        school_term_id=term.pk,
        criteria=[HonorCriterion.ATTENDANCE],
    )


def _current_year() -> tuple[SchoolYear, SchoolTerm, SchoolTerm]:
    """Bugünü içeren ders yılı: 1. dönem sürüyor, 2. dönem ileride."""
    today = timezone.localdate()
    year = SchoolYearFactory(
        name="Güncel Yıl",
        start_date=today - timedelta(days=60),
        end_date=today + timedelta(days=200),
    )
    first = SchoolTerm.objects.create(
        school_year=year,
        sequence=1,
        start_date=year.start_date,
        end_date=today + timedelta(days=60),
    )
    second = SchoolTerm.objects.create(
        school_year=year,
        sequence=2,
        start_date=today + timedelta(days=75),
        end_date=year.end_date,
    )
    return year, first, second


def _referred_case(referred_on: date = date(2026, 5, 19)) -> DisciplineCase:
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
        referred_on,
        override=True,
        override_reason="atla",
        principal_decisions=[PrincipalDecision.DISCIPLINE_COMMITTEE],
    )
    return case


# ---------------------------------------------------------------------------
# 37 — md. 191/1 yeter sayısı yalnız kurul üyeleriyle sağlanır
# ---------------------------------------------------------------------------
def test_kurul_uyesi_olmayan_kisi_oy_hakki_olan_uye_yazilamaz() -> None:
    """md. 191/1: "üyelerin dışında toplantıya çağrılanlar oy kullanamazlar"."""
    year = SchoolYearFactory()
    committee = _five_member_committee(year)
    teacher = committee.members.filter(member_type=CommitteeMemberType.TEACHER).first()
    assert teacher is not None
    rows = [
        _chair_row(committee),
        _row(teacher.member_name, member_user_id=teacher.member_user_id),
        _row("Kurul Dışı Kişi"),
    ]
    with pytest.raises(ValueError, match="kurul üyesi değil"):
        _odk_meeting(year, rows)
    # Aynı kişi davetli (md. 185/6) olarak yazılabilir; yeter sayıya girmez.
    rows[2] = _row("Kurul Dışı Kişi", role="NON_VOTING_INVITEE")
    meeting = _odk_meeting(year, rows)
    assert services.meeting_quorum(meeting) == {
        "full": 5,
        "required": 3,
        "present": 2,
        "ok": False,
    }


def test_ayni_uye_iki_kez_yazilamaz() -> None:
    year = SchoolYearFactory()
    committee = _five_member_committee(year)
    rows = [_chair_row(committee), _row("Hasan Velioğlu"), _row("HASAN VELİOĞLU")]
    with pytest.raises(ValueError, match="birden çok kez"):
        _odk_meeting(year, rows)
    # Onur Kurulunda da aynı kişi iki satır olamaz.
    ensure_terms(year)
    with pytest.raises(ValueError, match="birden çok kez"):
        services.create_council_meeting(
            school_year_id=year.pk,
            council_type="HONOR",
            meeting_date=date(2026, 5, 25),
            attendees=[_row("Başkan Öğretmen", chair=True), _row("Ali Can"), _row("ali can")],
        )


def test_yedek_uye_adla_eslesir_ve_yeter_sayiya_girer() -> None:
    """Yedek üye arayüzde elle (FK'sız) yazılır — ad eşleşmesi Türkçe harfe duyarsızdır."""
    year = SchoolYearFactory()
    committee = _five_member_committee(year)
    meeting = _odk_meeting(
        year, [_chair_row(committee), _row("Hasan Velioğlu"), _row("ışıl çiçek")]
    )
    quorum = services.meeting_quorum(meeting)
    assert quorum is not None
    assert quorum["present"] == 3 and quorum["ok"] is True


def test_yeter_sayi_eski_kayittaki_kurul_disi_satiri_saymaz() -> None:
    """Düzeltmeden önce kaydedilmiş kurul dışı / yinelenen satırlar sayıma girmez."""
    year = SchoolYearFactory()
    committee = _five_member_committee(year)
    meeting = _odk_meeting(year, [_chair_row(committee), _row("Hasan Velioğlu")])
    for name in ("Kurul Dışı Kişi", "HASAN VELİOĞLU"):
        CouncilMeetingAttendee.objects.create(
            meeting=meeting, attendee_role="VOTING_MEMBER", person_name=name
        )
    assert services.meeting_quorum(meeting) == {
        "full": 5,
        "required": 3,
        "present": 2,
        "ok": False,
    }


def test_uyelik_degisince_gecmis_toplantinin_yeter_sayisi_degismez() -> None:
    """Toplantı günü üye olan kişi sonradan kuruldan çıkarılsa da o toplantıda sayılır.

    Gözden geçirme (14.11.2026): yeter sayı GÜNCEL listeye bağlanınca üye değişikliği
    geçmiş toplantıyı yeter sayısız gösteriyordu. Yeni toplantıda canlı üyeler esastır.
    """
    from apps.disiplin.models import DisciplineCommitteeMember

    year = SchoolYearFactory()
    committee = _five_member_committee(year)
    teacher = committee.members.filter(member_type=CommitteeMemberType.TEACHER).first()
    parent = committee.members.get(member_name="HASAN VELİOĞLU")
    assert teacher is not None
    rows = [
        _chair_row(committee),
        _row(teacher.member_name, member_user_id=teacher.member_user_id),
        _row("Hasan Velioğlu"),
    ]
    meeting = _odk_meeting(year, rows)  # 01.06.2026
    before = services.meeting_quorum(meeting)
    assert before is not None and before["present"] == 3 and before["ok"] is True

    services.remove_committee_member(parent)  # toplantıdan SONRA çıkarıldı (bugün)
    after = services.meeting_quorum(meeting)
    assert after is not None and after["present"] == 3 and after["ok"] is True
    # Geçmiş toplantının katılımcıları düzeltilirken de o günkü üye kabul edilir.
    services.update_council_meeting(meeting, attendees=rows)
    # Yeni toplantıda canlı üyeler esastır: çıkarılmış üye oy hakkıyla yazılamaz.
    with pytest.raises(ValueError, match="kurul üyesi değil"):
        _odk_meeting(year, rows)

    # Toplantı tarihinden ÖNCE çıkarılmış üye o toplantıda sayılmaz.
    DisciplineCommitteeMember.all_objects.filter(pk=parent.pk).update(
        deleted_at=timezone.now() - timedelta(days=365)
    )
    earlier = services.meeting_quorum(meeting)
    assert earlier is not None and earlier["present"] == 2


def test_eski_eslesmeyen_satirli_toplanti_duzeltilebilir_ve_silinebilir() -> None:
    """Denetimden önce kaydedilmiş, kurul listesiyle adı eşleşmeyen oy hakkı satırı
    (ör. unvanlı yazım) toplantının düzeltilmesini ve silinmesini engellemez (§7.6)."""
    year = SchoolYearFactory()
    committee = _five_member_committee(year)
    meeting = _odk_meeting(year, [_chair_row(committee), _row("Hasan Velioğlu")])
    CouncilMeetingAttendee.objects.create(
        meeting=meeting, attendee_role="VOTING_MEMBER", person_name="Öğr. Ali Can"
    )
    kept = [_chair_row(committee), _row("Hasan Velioğlu"), _row("Öğr. Ali Can")]
    services.update_council_meeting(meeting, notes="Düzeltildi.", attendees=kept)
    quorum = services.meeting_quorum(meeting)
    assert quorum is not None and quorum["present"] == 2  # eski satır sayılmaz
    # YENİ yazılan kurul dışı ad yine reddedilir.
    with pytest.raises(ValueError, match="kurul üyesi değil"):
        services.update_council_meeting(meeting, attendees=[*kept, _row("Başka Biri")])
    services.delete_council_meeting(meeting)
    assert not CouncilMeeting.objects.filter(pk=meeting.pk).exists()


def test_oy_hakki_olan_katilimci_kurul_tam_sayisini_asamaz() -> None:
    """Yedek yalnız katılamayan asıl üyenin yerine çağrılır (md. 186, 191/2)."""
    year = SchoolYearFactory()
    committee = _five_member_committee(year)
    rows = [_chair_row(committee)] + [_row(m.member_name) for m in committee.members.all()]
    assert len(rows) == 6
    with pytest.raises(ValueError, match="tam sayısını"):
        _odk_meeting(year, rows)


def test_katilimci_duzeltmesi_de_uyelik_denetler() -> None:
    year = SchoolYearFactory()
    committee = _five_member_committee(year)
    meeting = _odk_meeting(year, [_chair_row(committee), _row("Hasan Velioğlu")])
    with pytest.raises(ValueError, match="kurul üyesi değil"):
        services.update_council_meeting(
            meeting, attendees=[_chair_row(committee), _row("Başka Biri")]
        )


# ---------------------------------------------------------------------------
# 38 — müdür onay/ret tarihi
# ---------------------------------------------------------------------------
def _awarded() -> HonorCertificate:
    SchoolYearFactory()
    cert = _propose(StudentFactory().pk)
    recommend(cert, on=date(2026, 5, 25))
    award(cert, on=date(2026, 6, 1))
    return cert


def test_mudur_onayi_kurul_kararindan_once_olamaz() -> None:
    cert = _awarded()
    with pytest.raises(ValueError, match="Kurulu kararından"):
        services.approve_honor_proposal_by_principal(cert, decided_on=date(2026, 5, 31))
    with pytest.raises(ValueError, match="Kurulu kararından"):
        services.reject_honor_proposal_by_principal(
            cert, decided_on=date(2026, 5, 31), reason="Uygun değil."
        )
    cert.refresh_from_db()
    assert cert.status == HonorCertificateStatus.AWARDED
    # Kurul kararıyla aynı gün verilebilir.
    services.approve_honor_proposal_by_principal(cert, decided_on=date(2026, 6, 1))


def test_mudur_onayi_gelecek_tarihli_olamaz() -> None:
    cert = _awarded()
    tomorrow = timezone.localdate() + timedelta(days=1)
    with pytest.raises(ValueError, match="ileri bir tarih"):
        services.approve_honor_proposal_by_principal(cert, decided_on=tomorrow)
    with pytest.raises(ValueError, match="ileri bir tarih"):
        services.reject_honor_proposal_by_principal(cert, decided_on=tomorrow, reason="x")
    cert.refresh_from_db()
    assert cert.status == HonorCertificateStatus.AWARDED


# ---------------------------------------------------------------------------
# 76 + 13.11 denetimi — toplantı tarihi
# ---------------------------------------------------------------------------
def test_gelecek_tarihli_toplantida_karar_verilemez() -> None:
    """Toplantı ileri tarihe planlanabilir; yapılmamış toplantının kararı yazılamaz."""
    year, first, _second = _current_year()
    services.create_honor_board(school_year_id=year.pk, chair_id=PersonnelFactory().pk)
    cert = services.propose_honor_certificate(
        student_id=StudentFactory().pk,
        proposer_role=HonorProposerRole.TEACHER,
        school_term_id=first.pk,
        criteria=[HonorCriterion.ATTENDANCE],
    )
    today = timezone.localdate()
    planned = services.create_council_meeting(
        school_year_id=year.pk,
        council_type="HONOR",
        meeting_date=today + timedelta(days=2),
        attendees=[_row("Onur Başkanı", chair=True), _row("Öğrenci Üye")],
    )
    item = services.add_agenda_items(planned, honor_certificate_ids=[cert.pk])[0]
    for outcome in ("FAVORABLE", "UNFAVORABLE"):
        with pytest.raises(ValueError, match="Toplantı tarihi"):
            services.decide_agenda_item(item, outcome=outcome, decision_text="gerekçe")
    cert.refresh_from_db()
    assert cert.status == HonorCertificateStatus.PROPOSED
    # Tarih bugüne çekilince karar verilir.
    services.update_council_meeting(planned, meeting_date=today)
    services.decide_agenda_item(item, outcome="FAVORABLE")


def test_odk_toplanti_tarihi_ders_yili_penceresinde_olmali() -> None:
    """Pencere: yıl başlangıcı ≤ tarih < SONRAKİ ders yılının başlangıcı.

    Eski hâli (`..._ders_yili_icinde_olmali`) üst sınırı ders yılı BİTİŞİNE bağlıyordu;
    gözden geçirme (14.11.2026) bunu kusur buldu: haziran sonu / yaz / eylül başında
    toplanan kurulun kararı biten yıla sayılır (`decisions_in_school_year` ile aynı
    pencere) ve karar defterine yazılabilmelidir. Bitişten sonrası artık REDDEDİLMEZ.
    """
    year = SchoolYearFactory()  # 08.09.2025 - 26.06.2026
    committee = committee_for(year)
    rows = [_chair_row(committee)]

    def _create(on: date) -> CouncilMeeting:
        meeting: CouncilMeeting = services.create_council_meeting(
            school_year_id=year.pk, council_type="DISCIPLINE", meeting_date=on, attendees=rows
        )
        return meeting

    with pytest.raises(ValueError, match="başlangıcından"):
        _create(year.start_date - timedelta(days=1))
    # Sonraki ders yılı tanımlı değilken üst sınır yok: yaz tarihli toplantı kaydedilir.
    summer = _create(date(2026, 7, 15))
    assert summer.school_year_id == year.pk
    meeting = _odk_meeting(year, rows)
    services.update_council_meeting(meeting, meeting_date=year.end_date + timedelta(days=30))

    # Sonraki ders yılı tanımlanınca üst sınır onun başlangıcıdır (o gün dahil DEĞİL).
    following = SchoolYearFactory(
        name="2026-2027",
        start_date=date(2026, 9, 7),
        end_date=date(2027, 6, 18),
        is_active=False,
    )
    _create(following.start_date - timedelta(days=3))  # eylül başı — biten yılın toplantısı
    with pytest.raises(ValueError, match="2026-2027 ders yılına düşüyor"):
        _create(following.start_date)
    with pytest.raises(ValueError, match="ders yılına düşüyor"):
        services.update_council_meeting(meeting, meeting_date=date(2026, 10, 1))


def test_yaz_tarihli_dosya_gorusme_tutanagi_kaydedilir() -> None:
    """Ders yılı bitişinden sonra toplanan kurulun dosya görüşme tutanağı (karar defteri)
    kaydedilebilir; ileri tarihli dosya görüşme tutanağı yine reddedilir (ayrı kural)."""
    from apps.disiplin.models import PenaltyType

    case = _referred_case(date(2026, 6, 15))
    year = SchoolYear.objects.get(is_active=True)
    committee = committee_for(year)
    student_id = case.case_students.values_list("student_id", flat=True)[0]
    decide(
        case,
        student_id=student_id,
        decision_date=date(2026, 6, 29),
        penalty_type=PenaltyType.REPRIMAND,
        penalty_detail="Kınama.",
    )
    kwargs: dict[str, Any] = {
        "school_year_id": year.pk,
        "council_type": "DISCIPLINE",
        "minutes_type": "CASE_REVIEW",
        "discipline_case_id": case.pk,
        "attendees": [_chair_row(committee)],
    }
    meeting = services.create_council_meeting(meeting_date=date(2026, 6, 29), **kwargs)
    assert meeting.meeting_date > year.end_date
    with pytest.raises(ValueError, match="ileri bir tarihle"):
        services.create_council_meeting(
            meeting_date=timezone.localdate() + timedelta(days=1), **kwargs
        )


def test_onur_kurulu_tanimli_degilken_uygun_gorus_verilemez() -> None:
    year = SchoolYearFactory()
    ensure_terms(year)
    cert = _propose(StudentFactory().pk)
    meeting = services.create_council_meeting(
        school_year_id=year.pk,
        council_type="HONOR",
        meeting_date=date(2026, 5, 25),
        attendees=[_row("Onur Başkanı", chair=True), _row("Öğrenci Üye")],
    )
    item = services.add_agenda_items(meeting, honor_certificate_ids=[cert.pk])[0]
    with pytest.raises(ValueError, match="Onur Kurulu tanımlı değil"):
        services.decide_agenda_item(item, outcome="FAVORABLE")
    cert.refresh_from_db()
    assert cert.status == HonorCertificateStatus.PROPOSED
    services.create_honor_board(school_year_id=year.pk, chair_id=PersonnelFactory().pk)
    services.decide_agenda_item(item, outcome="FAVORABLE")


# ---------------------------------------------------------------------------
# 39 — ileri tarihli temsilci değişikliği (md. 178/1)
# ---------------------------------------------------------------------------
def test_ileri_tarihli_temsilci_degisikligi_mevcut_temsilciyi_pasiflestirmez() -> None:
    from apps.disiplin.serializers import HonorGeneralAssemblyMemberSerializer

    year, _first, second = _current_year()
    board = services.create_honor_board(school_year_id=year.pk, chair_id=PersonnelFactory().pk)
    current = StudentFactory(class_level=10, class_section="A")
    incoming = StudentFactory(class_level=10, class_section="A")
    old = services.add_general_assembly_member(school_year_id=year.pk, student_id=current.pk)
    new = services.add_general_assembly_member(
        school_year_id=year.pk,
        student_id=incoming.pk,
        effective_from=second.start_date,
        replaced_member_id=old.pk,
    )
    old.refresh_from_db()
    assert old.effective_until == second.start_date - timedelta(days=1)

    # 2. dönem başına dek görevdeki temsilci eskisidir.
    assert HonorGeneralAssemblyMemberSerializer(old).data["is_active"] is True
    assert HonorGeneralAssemblyMemberSerializer(new).data["is_active"] is False
    active = selectors.honor_general_assembly_members(school_year_id=year.pk, active_only=True)
    assert [m.pk for m in active] == [old.pk]
    prefill = services.prefill_attendees("HONOR", "GENERAL_ASSEMBLY")
    assert [p["member_student_id"] for p in prefill[1:]] == [current.pk]

    # Görevdeki temsilci Onur Kuruluna seçilebilir; göreve başlamamış olan seçilemez.
    with pytest.raises(ValueError, match="aktif Onur Genel Kurulu"):
        services.add_honor_board_member(board, student_id=incoming.pk)
    services.add_honor_board_member(board, student_id=current.pk)


def test_bitmis_temsilcilik_yeniden_sonlandirilamaz_ve_donemler_cakisamaz() -> None:
    year, _first, _second = _current_year()
    today = timezone.localdate()
    student = StudentFactory(class_level=9, class_section="B")
    member = services.add_general_assembly_member(school_year_id=year.pk, student_id=student.pk)
    services.end_general_assembly_membership(member, effective_until=today, reason="Nakil")
    with pytest.raises(ValueError, match="zaten"):
        services.end_general_assembly_membership(member, effective_until=today, reason="Başka")
    member.refresh_from_db()
    assert member.end_reason == "Nakil"

    other = StudentFactory(class_level=9, class_section="B")
    with pytest.raises(ValueError, match="sonra olmalı"):
        services.add_general_assembly_member(
            school_year_id=year.pk, student_id=other.pk, effective_from=year.start_date
        )
    services.add_general_assembly_member(
        school_year_id=year.pk, student_id=other.pk, effective_from=today + timedelta(days=1)
    )


def _planned_change() -> tuple[SchoolYear, Any, Any, SchoolTerm]:
    """10/A'da görevdeki temsilci + 2. dönem başında göreve başlayacak yeni temsilci."""
    year, _first, second = _current_year()
    old = services.add_general_assembly_member(
        school_year_id=year.pk, student_id=StudentFactory(class_level=10, class_section="A").pk
    )
    new = services.add_general_assembly_member(
        school_year_id=year.pk,
        student_id=StudentFactory(class_level=10, class_section="A").pk,
        effective_from=second.start_date,
        replaced_member_id=old.pk,
    )
    old.refresh_from_db()
    return year, old, new, second


def test_bitisi_gelecekte_olan_temsilcilik_erkene_cekilebilir() -> None:
    """md. 181: ceza alan temsilcinin görevi, planlanan bitişi beklemeden sonlandırılır.

    Bitişi GELECEKTE kayıtlı görev yalnız daha erken bir tarihe çekilir; bitmiş görev
    kilitlidir (gözden geçirme 14.11.2026 — tek yönlü kapan, §7.6).
    """
    _year, old, _new, second = _planned_change()
    today = timezone.localdate()
    planned_end = second.start_date - timedelta(days=1)
    assert old.effective_until == planned_end
    for not_earlier in (planned_end, planned_end + timedelta(days=5)):
        with pytest.raises(ValueError, match="daha erken"):
            services.end_general_assembly_membership(
                old, effective_until=not_earlier, reason="Ceza aldı."
            )
    services.end_general_assembly_membership(
        old, effective_until=today, reason="Ceza aldı (md. 181)."
    )
    old.refresh_from_db()
    assert old.effective_until == today and old.end_reason == "Ceza aldı (md. 181)."
    # Artık bitmiş görev: yeniden sonlandırılamaz.
    with pytest.raises(ValueError, match="zaten"):
        services.end_general_assembly_membership(
            old, effective_until=today - timedelta(days=1), reason="Başka"
        )


def test_planlanan_temsilci_degisikligi_iptal_edilebilir() -> None:
    """Henüz göreve başlamamış temsilcilik iptal edilir; önceki temsilci süresiz devam eder."""
    from rest_framework.test import APIClient

    from apps.disiplin.models import HonorGeneralAssemblyMember

    year, old, new, second = _planned_change()
    other = StudentFactory(class_level=10, class_section="A")
    # Planlanan değişiklik varken ikinci değişiklik reddedilir; ileti GERÇEK yolu gösterir.
    with pytest.raises(ValueError, match="planlanan değişikliği iptal"):
        services.add_general_assembly_member(
            school_year_id=year.pk,
            student_id=other.pk,
            effective_from=second.start_date,
            replaced_member_id=new.pk,
        )
    # Göreve başlamış temsilcilik iptal edilemez (görevi sonlandırılır).
    with pytest.raises(ValueError, match="göreve başlamış"):
        services.cancel_planned_general_assembly_change(old)

    url = f"/api/v1/honor/general-assembly/{new.pk}/cancel-planned/"
    client = APIClient()
    assert client.post(url).status_code == 204
    assert client.post(url).status_code == 404  # soft-delete edildi
    assert not HonorGeneralAssemblyMember.objects.filter(pk=new.pk).exists()
    old.refresh_from_db()
    assert old.effective_until is None and old.end_reason == ""

    # Doğru öğrenciyle yeniden kaydedilebilir.
    again = services.add_general_assembly_member(
        school_year_id=year.pk,
        student_id=other.pk,
        effective_from=second.start_date,
        replaced_member_id=old.pk,
    )
    assert again.replaced_member_id == old.pk


def test_planlanan_degisiklik_iptali_erkene_cekilmis_bitise_dokunmaz() -> None:
    """Önceki temsilcinin görevi ayrıca (ör. md. 181) erkene çekildiyse iptal onu diriltmez."""
    _year, old, new, _second = _planned_change()
    today = timezone.localdate()
    services.end_general_assembly_membership(old, effective_until=today, reason="Ceza aldı.")
    services.cancel_planned_general_assembly_change(new)
    old.refresh_from_db()
    assert old.effective_until == today and old.end_reason == "Ceza aldı."


# ---------------------------------------------------------------------------
# 81, 82 — Onur Kurulu başkan/yedek, ikinci başkan yedeği
# ---------------------------------------------------------------------------
def test_onur_kurulu_baskani_mevcut_baskan_yedegi_yapilamaz() -> None:
    year = SchoolYearFactory()
    substitute = PersonnelFactory()
    board = services.create_honor_board(
        school_year_id=year.pk, chair_id=PersonnelFactory().pk, substitute_chair_id=substitute.pk
    )
    with pytest.raises(ValueError, match="aynı kişi olamaz"):
        services.set_honor_board_chair(board, substitute.pk)
    board.refresh_from_db()
    assert board.chair_id != substitute.pk


def test_ikinci_baskan_yedegi_sira_bagimsiz_eklenir() -> None:
    """md. 180/1: genel kurul bir öğrenciyi de ikinci başkanlık YEDEK üyeliğine seçer."""
    year = SchoolYearFactory()
    board = services.create_honor_board(school_year_id=year.pk, chair_id=PersonnelFactory().pk)

    def temsilci(level: int, section: str) -> int:
        s = StudentFactory(class_level=level, class_section=section)
        services.add_general_assembly_member(school_year_id=year.pk, student_id=s.pk)
        return int(s.pk)

    services.add_honor_board_member(board, student_id=temsilci(12, "A"), is_second_chair=True)
    # Asıl ikinci başkan varken yedeği eklenebilir.
    yedek = services.add_honor_board_member(
        board, student_id=temsilci(11, "B"), is_second_chair=True, is_substitute=True
    )
    assert yedek.is_second_chair and yedek.is_substitute
    # İkinci bir asıl ikinci başkan ve ikinci bir yedek ikinci başkan olamaz.
    with pytest.raises(ValueError, match="yalnız bir aktif ikinci başkan"):
        services.add_honor_board_member(board, student_id=temsilci(11, "A"), is_second_chair=True)
    with pytest.raises(ValueError, match="yalnız bir ikinci başkan yedeği"):
        services.add_honor_board_member(
            board, student_id=temsilci(11, "C"), is_second_chair=True, is_substitute=True
        )


# ---------------------------------------------------------------------------
# 83 — başkan atfı kurula göre
# ---------------------------------------------------------------------------
def test_baskan_iletisi_kurula_gore_madde_atfi_verir() -> None:
    year = SchoolYearFactory()
    ensure_terms(year)
    with pytest.raises(ValueError, match=r"md\. 182") as honor_error:
        services.create_council_meeting(
            school_year_id=year.pk,
            council_type="HONOR",
            meeting_date=date(2026, 5, 25),
            attendees=[_row("Öğrenci Üye")],
        )
    assert "188" not in str(honor_error.value)
    committee = committee_for(year)
    with pytest.raises(ValueError, match=r"md\. 188"):
        _odk_meeting(year, [_row(committee.chair.full_name)])


# ---------------------------------------------------------------------------
# 8, 12, 13 — dosya görüşme toplantısı
# ---------------------------------------------------------------------------
def _meeting_members(year: SchoolYear) -> list[int]:
    committee = committee_for(year)
    return list(committee.members.values_list("id", flat=True))


def test_kurula_sevk_edilmemis_dosyaya_toplanti_kaydedilemez() -> None:
    year = SchoolYearFactory()
    ids = _meeting_members(year)
    case = services.create_case(
        petition_date=date(2026, 5, 18),
        petitioner_name="A",
        petitioner_role="IDARE",
        summary="x",
        student_ids=[StudentFactory().pk],
    )
    with pytest.raises(ValueError, match="sevk edilmemiş"):
        services.record_meeting(case, meeting_date=date(2026, 5, 20), attendee_member_ids=ids)
    assert case.meetings.count() == 0


def test_toplanti_kurula_sevk_tarihinden_once_olamaz() -> None:
    case = _referred_case(date(2026, 5, 19))
    ids = _meeting_members(SchoolYear.objects.get(is_active=True))
    with pytest.raises(ValueError, match="sevk tarihinden"):
        services.record_meeting(case, meeting_date=date(2026, 5, 18), attendee_member_ids=ids)
    services.record_meeting(case, meeting_date=date(2026, 5, 19), attendee_member_ids=ids)


def test_kapali_dosyaya_toplanti_kaydedilemez_ve_silinemez() -> None:
    case = _referred_case()
    ids = _meeting_members(SchoolYear.objects.get(is_active=True))
    meeting = services.record_meeting(case, meeting_date=date(2026, 5, 20), attendee_member_ids=ids)
    case.closed_at = timezone.now()
    case.save(update_fields=["closed_at"])
    with pytest.raises(ValueError, match="Dosya kapalı"):
        services.record_meeting(case, meeting_date=date(2026, 5, 21), attendee_member_ids=ids)
    with pytest.raises(ValueError, match="Dosya kapalı"):
        services.delete_meeting(meeting)
    assert case.meetings.count() == 1


def test_yanlis_girilen_toplanti_silinebilir() -> None:
    """§7.6 tek yönlü kapan: yanlış girilen toplantı kaydı düzeltilebilmeli."""
    from rest_framework.test import APIClient

    case = _referred_case()
    ids = _meeting_members(SchoolYear.objects.get(is_active=True))
    first = services.record_meeting(case, meeting_date=date(2026, 5, 20), attendee_member_ids=ids)
    second = services.record_meeting(case, meeting_date=date(2026, 5, 22), attendee_member_ids=ids)
    services.delete_meeting(second)
    assert [m.pk for m in selectors.meetings_for_case(case)] == [first.pk]

    client = APIClient()
    url = f"/api/v1/discipline/cases/{case.pk}/meeting/{first.pk}/"
    assert client.delete(url).status_code == 204
    assert client.delete(url).status_code == 404
    assert selectors.meetings_for_case(case).count() == 0
