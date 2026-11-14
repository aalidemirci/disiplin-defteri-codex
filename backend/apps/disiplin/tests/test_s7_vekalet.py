"""S7 (kullanıcı kararı, 14.11.2026) — VEKÂLET KAYDI: "başkan katılmadı, yerine … başkanlık etti".

Dayanak (Ortaöğretim Kurumları Yönetmeliği):
- md. 188/1: kurul başkanı müdürün görevlendireceği müdür yardımcısıdır; "Başkan
  bulunmadığında müdürün görevlendireceği öğretmen üyelerden biri kurula başkanlık eder.
  Üyenin başkanlık yaptığı durumlarda yedek üye toplantıya katılır."
- md. 191/2: "Disiplin konusu davranıştan şikâyetçi olan veya zarar gören üye kurula
  katılamaz. Kurula katılmayan üyenin yerine yedek üye toplantıya çağrılır."
- md. 191/1: kurul üyelerin salt çoğunluğuyla toplanır.

Kapsam: dosya toplantısı (`record_meeting`), Ödül ve Disiplin Kurulu toplantısı / dosya
görüşme tutanağı (`create_council_meeting`), imza ızgaraları (EK-1, Form-11, md. 195
tutanağı, karar defteri), yeter sayı, API ve 0017 göçü. Onur Kurulu (md. 182) etkilenmez.

Ek kararlar (kullanıcı, 14.11.2026): K1 başkan hanesi etiketi üç şablonda bağlamdan; K2 aday
yokken ileti; K3 şikâyetçi / zarar gören başkan dosyanın bütün kurul evrakından çıkar; K4 eski
kayıtta boş hane + kalıcı uyarı. Dosyanın sonundaki bölüm. Etiket kararı ("Evet, değişsin"):
Form-3, 4-6, 7-8, 9, 10, 12, 13'te sabit başkan etiketi de bağlamdan (`test_etiket_…`).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from typing import Any

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.template.loader import render_to_string
from django.utils import timezone
from rest_framework.test import APIClient

from apps.disiplin import documents as doc_engine
from apps.disiplin import services
from apps.disiplin.models import (
    CaseStage,
    CouncilMeeting,
    CouncilMeetingAttendee,
    DisciplineCase,
    DisciplineCommittee,
    DisciplineCommitteeMember,
    ParticipantRole,
    PenaltyType,
    PrincipalDecision,
)
from apps.disiplin.services import council as council_service
from apps.disiplin.tests.factories import (
    PersonnelFactory,
    SchoolYearFactory,
    StudentFactory,
    council_meeting,
    legacy_decision,
)
from apps.okul.services import setup as okul_setup

pytestmark = pytest.mark.django_db

_ON = date(2026, 5, 21)


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------
class _Kurul:
    """Başkan + 2 asıl öğretmen + 1 asıl veli (tam sayı 4, yeter sayı 3) + 1 yedek öğretmen."""

    def __init__(self) -> None:
        self.year = SchoolYearFactory()
        okul_setup.update_school_config(
            fields={
                "school_name": "Deneme Anadolu Lisesi",
                "district": "Menteşe",
                "principal_name": "ALİ ÖRNEK",
            }
        )
        self.chair = PersonnelFactory(first_name="BAŞKAN", last_name="MÜDÜRYARDIMCISI")
        self.committee: DisciplineCommittee = services.create_committee(
            school_year_id=self.year.pk, chair_id=self.chair.pk
        )
        self.t1 = self._teacher("İPEK", "ÖĞRETMEN")
        self.t2 = self._teacher("ILGAZ", "ŞAHİN")
        self.parent: DisciplineCommitteeMember = services.add_committee_member(
            self.committee, member_type="PARENT", member_name="HASAN VELİOĞLU"
        )
        self.sub = self._teacher("YEDEK", "ÇAĞRI", is_substitute=True)

    def _teacher(
        self, first: str, last: str, *, is_substitute: bool = False
    ) -> DisciplineCommitteeMember:
        person = PersonnelFactory(first_name=first, last_name=last)
        member: DisciplineCommitteeMember = services.add_committee_member(
            self.committee, member_type="TEACHER", person_id=person.pk, is_substitute=is_substitute
        )
        return member

    def case(self, *, petitioner_user_id: int | None = None) -> DisciplineCase:
        """Kurula sevkli dosya (şikâyetçi personel verilebilir)."""
        case = services.create_case(
            petition_date=date(2026, 5, 18),
            petitioner_name="İdare",
            petitioner_role="OGRETMEN" if petitioner_user_id else "IDARE",
            summary="Koridorda kavga.",
            student_ids=[StudentFactory().pk],
            petitioner_user_id=petitioner_user_id,
        )
        services.add_event(
            case,
            CaseStage.DECIDED,
            date(2026, 5, 19),
            override=True,
            override_reason="atla",
            principal_decisions=[PrincipalDecision.DISCIPLINE_COMMITTEE],
        )
        return case

    def row(self, member: DisciplineCommitteeMember, *, chair: bool = False) -> dict[str, Any]:
        return {
            "person_name": member.member_name,
            "attendee_role": "VOTING_MEMBER",
            "is_chair": chair,
            "title": "Öğretmen" if member.member_user_id else "Veli",
            "member_user_id": member.member_user_id,
        }

    def chair_row(self) -> dict[str, Any]:
        return {
            "person_name": self.chair.full_name,
            "attendee_role": "VOTING_MEMBER",
            "is_chair": True,
            "member_user_id": self.chair.pk,
        }

    def odk(self, attendees: list[dict[str, Any]], **kwargs: Any) -> CouncilMeeting:
        meeting: CouncilMeeting = services.create_council_meeting(
            school_year_id=self.year.pk,
            council_type="DISCIPLINE",
            meeting_date=date(2026, 6, 1),
            attendees=attendees,
            **kwargs,
        )
        return meeting


@pytest.fixture
def kurul() -> _Kurul:
    return _Kurul()


def _html(template: str, context: dict[str, Any]) -> str:
    return " ".join(render_to_string(template, context).split())


_EK1 = "disiplin/documents/ek1_committee_decision.html"
_GRID = "disiplin/documents/_defense_record_committee_grid.html"
_MINUTES = "disiplin/documents/council_meeting_minutes.html"


# ---------------------------------------------------------------------------
# Dosya toplantısı — şikâyetçi / zarar gören başkan (md. 191/2, 188)
# ---------------------------------------------------------------------------
def test_sikayetci_baskanin_dosyasinda_toplanti_vekaletsiz_kaydedilemez(kurul: _Kurul) -> None:
    case = kurul.case(petitioner_user_id=kurul.chair.pk)
    with pytest.raises(ValueError, match="Başkan toplantıya katılmadı") as err:
        services.record_meeting(
            case, meeting_date=_ON, attendee_member_ids=[kurul.t1.pk, kurul.t2.pk, kurul.parent.pk]
        )
    # Eyleme dönük: neden (md. 191/2) ve ne yapılacağı (başkanlık eden öğretmen üye, md. 188).
    assert "md. 191/2" in str(err.value)
    assert "md. 188" in str(err.value)
    assert case.meetings.count() == 0


def test_sikayetci_baskanin_dosyasinda_vekaletle_toplanti_kaydedilir(kurul: _Kurul) -> None:
    case = kurul.case(petitioner_user_id=kurul.chair.pk)
    meeting = services.record_meeting(
        case,
        meeting_date=_ON,
        attendee_member_ids=[kurul.t1.pk, kurul.t2.pk, kurul.parent.pk],
        chair_absent=True,
        acting_chair_member_id=kurul.t1.pk,
    )
    assert meeting.chair_absent is True
    assert meeting.acting_chair_id == kurul.t1.pk


def test_zarar_goren_baskanin_dosyasinda_da_vekalet_gerekir(kurul: _Kurul) -> None:
    case = kurul.case()
    services.add_participant(
        case, role=ParticipantRole.VICTIM, person_type="STAFF", person_id=kurul.chair.pk
    )
    with pytest.raises(ValueError, match="Başkan toplantıya katılmadı"):
        services.record_meeting(
            case, meeting_date=_ON, attendee_member_ids=[kurul.t1.pk, kurul.t2.pk, kurul.parent.pk]
        )


def test_baskan_sikayetci_degilken_de_vekalet_kaydi_girilebilir(kurul: _Kurul) -> None:
    """Başkan izinli/raporlu olabilir (md. 188: "Başkan bulunmadığında")."""
    meeting = services.record_meeting(
        kurul.case(),
        meeting_date=_ON,
        attendee_member_ids=[kurul.t1.pk, kurul.t2.pk, kurul.sub.pk],
        chair_absent=True,
        acting_chair_member_id=kurul.t2.pk,
    )
    assert meeting.acting_chair_id == kurul.t2.pk


def test_baskan_katilmadiysa_baskanlik_eden_secilmelidir(kurul: _Kurul) -> None:
    with pytest.raises(ValueError, match="başkanlık eden"):
        services.record_meeting(
            kurul.case(),
            meeting_date=_ON,
            attendee_member_ids=[kurul.t1.pk, kurul.t2.pk, kurul.parent.pk],
            chair_absent=True,
        )


def test_baskan_katildiysa_baskanlik_eden_verilemez(kurul: _Kurul) -> None:
    with pytest.raises(ValueError, match="Başkan toplantıya katılmadı"):
        services.record_meeting(
            kurul.case(),
            meeting_date=_ON,
            attendee_member_ids=[kurul.t1.pk, kurul.t2.pk],
            acting_chair_member_id=kurul.t1.pk,
        )


@pytest.mark.parametrize("who", ["parent", "sub"])
def test_baskanlik_eden_asil_ogretmen_uye_olmalidir(kurul: _Kurul, who: str) -> None:
    """md. 188: "öğretmen üyelerden biri" — veli üye ve yedek üye başkanlık edemez (dar yorum)."""
    member: DisciplineCommitteeMember = getattr(kurul, who)
    with pytest.raises(ValueError, match="asıl öğretmen üye"):
        services.record_meeting(
            kurul.case(),
            meeting_date=_ON,
            attendee_member_ids=[kurul.t1.pk, kurul.t2.pk, kurul.parent.pk, kurul.sub.pk],
            chair_absent=True,
            acting_chair_member_id=member.pk,
        )


def test_baskanlik_eden_katilanlar_arasinda_olmalidir(kurul: _Kurul) -> None:
    with pytest.raises(ValueError, match="katılanlar arasında"):
        services.record_meeting(
            kurul.case(),
            meeting_date=_ON,
            attendee_member_ids=[kurul.t2.pk, kurul.parent.pk, kurul.sub.pk],
            chair_absent=True,
            acting_chair_member_id=kurul.t1.pk,
        )


def test_sikayetci_ogretmen_uye_baskanlik_edemez(kurul: _Kurul) -> None:
    """md. 191/2: şikâyetçi üye kurula katılamaz — başkanlık da edemez."""
    case = kurul.case(petitioner_user_id=kurul.t1.member_user_id)
    with pytest.raises(ValueError, match="md. 191/2"):
        services.record_meeting(
            case,
            meeting_date=_ON,
            attendee_member_ids=[kurul.t1.pk, kurul.t2.pk, kurul.parent.pk],
            chair_absent=True,
            acting_chair_member_id=kurul.t1.pk,
        )


def test_baskanlik_edebilecek_uye_yoksa_ileti_durumu_ve_dayanagi_soyler(kurul: _Kurul) -> None:
    """Uygun asıl öğretmen üye yoksa ileti durumu ve yönetmeliğin yolunu (md. 186-187) söyler;
    kurula öğretmen üye eklemeyi ÖNERMEZ (K2 — bkz. `test_k2_…`)."""
    services.remove_committee_member(kurul.t1)
    services.remove_committee_member(kurul.t2)
    case = kurul.case(petitioner_user_id=kurul.chair.pk)
    with pytest.raises(ValueError, match="asıl öğretmen üye yok") as err:
        services.record_meeting(
            case, meeting_date=_ON, attendee_member_ids=[kurul.parent.pk, kurul.sub.pk]
        )
    assert "md. 186" in str(err.value)
    options = services.acting_chair_options(kurul.committee, case)
    assert options["chair_conflicted"] is True
    assert options["eligible"] == []


# ---------------------------------------------------------------------------
# Yeter sayı — md. 191/1
# ---------------------------------------------------------------------------
def test_baskan_katilmadiysa_yeter_sayida_baskan_sayilmaz(kurul: _Kurul) -> None:
    """Kurul 4 kişi → en az 3. Başkan yoksa iki üye yetmez; yedekle üç olur."""
    case = kurul.case()
    with pytest.raises(ValueError, match="yeter sayısı"):
        services.record_meeting(
            case,
            meeting_date=_ON,
            attendee_member_ids=[kurul.t1.pk, kurul.t2.pk],
            chair_absent=True,
            acting_chair_member_id=kurul.t1.pk,
        )
    meeting = services.record_meeting(
        case,
        meeting_date=_ON,
        attendee_member_ids=[kurul.t1.pk, kurul.t2.pk, kurul.sub.pk],
        chair_absent=True,
        acting_chair_member_id=kurul.t1.pk,
    )
    assert meeting.attendees.count() == 3
    # Kurul tam sayısı değişmez.
    assert services.committee_quorum(kurul.committee, 3) == {
        "full": 4,
        "required": 3,
        "present": 3,
        "ok": True,
    }


def test_vekaletsiz_toplantida_baskan_sayilmaya_devam_eder(kurul: _Kurul) -> None:
    """Eski davranış: başkan katıldıysa iki üye + başkan = 3 → yeter sayı var."""
    meeting = services.record_meeting(
        kurul.case(), meeting_date=_ON, attendee_member_ids=[kurul.t1.pk, kurul.t2.pk]
    )
    assert meeting.chair_absent is False
    assert meeting.acting_chair_id is None


# ---------------------------------------------------------------------------
# İmza ızgaraları — EK-1, Form-11, md. 195 tutanağı
# ---------------------------------------------------------------------------
def _vekaletli_dosya(kurul: _Kurul) -> DisciplineCase:
    case = kurul.case(petitioner_user_id=kurul.chair.pk)
    services.record_meeting(
        case,
        meeting_date=_ON,
        attendee_member_ids=[kurul.t1.pk, kurul.t2.pk, kurul.sub.pk],
        chair_absent=True,
        acting_chair_member_id=kurul.t1.pk,
    )
    return case


def test_ek1_vekaletli_toplantida_katilmayan_baskani_basmaz(kurul: _Kurul) -> None:
    case = _vekaletli_dosya(kurul)
    student = case.students.get()
    ctx = doc_engine._ek1_context(case, student)
    html = _html(_EK1, ctx)
    assert kurul.chair.full_name not in html
    # Başkan hanesinde başkanlık eden öğretmen üye; md. 188 ifadesi hane ETİKETİNDE (K1).
    assert "Kurula Başkanlık Eden Öğretmen Üye (md. 188)" in html
    assert "Başkan (Müdür Yrd.)" not in html
    # Başkanlık eden üye, üye hanelerinde ikinci kez basılmaz; diğer katılanlar basılır.
    assert html.count(kurul.t1.member_name) == 1
    assert kurul.t2.member_name in html
    assert kurul.sub.member_name in html
    assert kurul.parent.member_name not in html  # katılmadı


@pytest.mark.parametrize(
    "builder", [doc_engine._ek1_context, None], ids=["ek1", "form11_md195_izgarasi"]
)
def test_vekaletli_toplantida_izgara_baglami(kurul: _Kurul, builder: Any) -> None:
    case = _vekaletli_dosya(kurul)
    if builder is None:
        ctx = doc_engine._committee_signers_context(case)
        html = _html(_GRID, ctx)
        assert kurul.chair.full_name not in html
        assert "Kurula Başkanlık Eden Öğretmen Üye (md. 188)" in html
    else:
        ctx = builder(case, case.students.get())
    names = [m.member_name for m in ctx["members"]]
    assert sorted(names) == sorted([kurul.t2.member_name, kurul.sub.member_name])
    assert kurul.t1.member_name in ctx["committee"].chair.get_full_name()
    # Vekil yalnız başkan alanını değiştirir; kurulun diğer alanları aynen devredilir.
    assert ctx["committee"].school_year_id == kurul.committee.school_year_id


def test_vekaletsiz_toplantida_izgara_hic_degismez(kurul: _Kurul) -> None:
    """Vekâlet kaydı olmayan toplantıda bağlam eski hâliyle: gerçek kurul + katılanlar."""
    case = kurul.case()
    services.record_meeting(
        case, meeting_date=_ON, attendee_member_ids=[kurul.t1.pk, kurul.t2.pk, kurul.parent.pk]
    )
    for ctx in (
        doc_engine._ek1_context(case, case.students.get()),
        doc_engine._committee_signers_context(case),
    ):
        assert isinstance(ctx["committee"], DisciplineCommittee)
        assert sorted(m.member_name for m in ctx["members"]) == sorted(
            [kurul.t1.member_name, kurul.t2.member_name, kurul.parent.member_name]
        )
        html = _html(_GRID, ctx)
        assert kurul.chair.full_name in html
        assert "md. 188" not in html
        assert "Başkan (Müdür Yrd.)" in html


def test_toplanti_kaydi_olmayan_dosyada_izgara_hic_degismez(kurul: _Kurul) -> None:
    """Eski kayıt / toplantısız dosya: kurulun başkanı ve üyeleri (yedek şablonda gizli)."""
    case = kurul.case()
    ctx = doc_engine._committee_signers_context(case)
    assert isinstance(ctx["committee"], DisciplineCommittee)
    assert len(ctx["members"]) == 4
    html = _html(_GRID, ctx)
    assert kurul.chair.full_name in html
    assert kurul.sub.member_name not in html


def test_son_toplanti_vekaletsizse_onceki_vekalet_izgaraya_tasinmaz(kurul: _Kurul) -> None:
    """Izgara SON toplantı kaydına dayanır (mevcut kural); vekâlet de o kayıttan okunur."""
    case = kurul.case()
    services.record_meeting(
        case,
        meeting_date=_ON,
        attendee_member_ids=[kurul.t1.pk, kurul.t2.pk, kurul.sub.pk],
        chair_absent=True,
        acting_chair_member_id=kurul.t1.pk,
    )
    services.record_meeting(
        case, meeting_date=date(2026, 5, 25), attendee_member_ids=[kurul.t1.pk, kurul.t2.pk]
    )
    ctx = doc_engine._committee_signers_context(case)
    assert isinstance(ctx["committee"], DisciplineCommittee)


# ---------------------------------------------------------------------------
# Ödül ve Disiplin Kurulu toplantısı (karar defteri)
# ---------------------------------------------------------------------------
def test_odk_toplantisinda_baskan_katilmadi_kaydi_ve_yeter_sayi(kurul: _Kurul) -> None:
    meeting = kurul.odk(
        [kurul.row(kurul.t1, chair=True), kurul.row(kurul.t2), kurul.row(kurul.sub)],
        chair_absent=True,
    )
    assert meeting.chair_absent is True
    quorum = council_service.meeting_quorum(meeting)
    assert quorum == {"full": 4, "required": 3, "present": 3, "ok": True}

    short = kurul.odk([kurul.row(kurul.t1, chair=True), kurul.row(kurul.t2)], chair_absent=True)
    assert council_service.meeting_quorum(short) == {
        "full": 4,
        "required": 3,
        "present": 2,
        "ok": False,
    }


def test_odk_toplantisinda_baskan_isaretli_kisi_kurul_baskani_olmalidir(kurul: _Kurul) -> None:
    """Vekâlet kaydı yokken öğretmen üye "başkan" işaretlenemez; ileti kutuyu gösterir."""
    with pytest.raises(ValueError, match="Başkan toplantıya katılmadı"):
        kurul.odk([kurul.row(kurul.t1, chair=True), kurul.row(kurul.t2), kurul.row(kurul.parent)])


def test_odk_vekalette_kurul_baskani_katilimci_yazilamaz(kurul: _Kurul) -> None:
    rows = [kurul.row(kurul.t1, chair=True), kurul.row(kurul.t2), kurul.row(kurul.parent)]
    absent_chair = {**kurul.chair_row(), "is_chair": False}
    invited_chair = {**absent_chair, "attendee_role": "NON_VOTING_INVITEE"}
    for extra in (absent_chair, invited_chair):
        with pytest.raises(ValueError, match="katılımcı listesinde"):
            kurul.odk([*rows, extra], chair_absent=True)


@pytest.mark.parametrize("who", ["parent", "sub"])
def test_odk_vekalette_baskanlik_eden_asil_ogretmen_uye_olmalidir(kurul: _Kurul, who: str) -> None:
    member: DisciplineCommitteeMember = getattr(kurul, who)
    others = [m for m in (kurul.t1, kurul.t2, kurul.parent, kurul.sub) if m.pk != member.pk]
    with pytest.raises(ValueError, match="asıl öğretmen üye"):
        kurul.odk(
            [kurul.row(member, chair=True), *[kurul.row(m) for m in others[:2]]],
            chair_absent=True,
        )


def _case_with_decision(kurul: _Kurul, *, petitioner_user_id: int | None) -> DisciplineCase:
    case = kurul.case(petitioner_user_id=petitioner_user_id)
    # S8 ÖNCESİ kayıt taklidi: bu testler "toplantı kaydı yok / S7 öncesi toplantı" durumlarını
    # sınar; yeni yolda karar toplantısız girilemez (bkz. test_s8_toplanti_zorunlu.py).
    legacy_decision(
        case,
        student_id=case.students.get().pk,
        decision_date=date(2026, 5, 29),
        penalty_type=PenaltyType.REPRIMAND,
        penalty_detail="Kınama.",
    )
    return case


def test_dosya_gorusme_tutanaginda_sikayetci_baskan_vekalet_ister(kurul: _Kurul) -> None:
    case = _case_with_decision(kurul, petitioner_user_id=kurul.chair.pk)
    kwargs: dict[str, Any] = {"minutes_type": "CASE_REVIEW", "discipline_case_id": case.pk}
    with pytest.raises(ValueError, match="Başkan toplantıya katılmadı") as err:
        kurul.odk([kurul.chair_row(), kurul.row(kurul.t1), kurul.row(kurul.t2)], **kwargs)
    assert "md. 191/2" in str(err.value)
    meeting = kurul.odk(
        [kurul.row(kurul.t1, chair=True), kurul.row(kurul.t2), kurul.row(kurul.sub)],
        chair_absent=True,
        **kwargs,
    )
    assert meeting.chair_absent is True


def test_dosya_gorusme_tutanaginda_sikayetci_ogretmen_baskanlik_edemez(kurul: _Kurul) -> None:
    case = _case_with_decision(kurul, petitioner_user_id=kurul.t1.member_user_id)
    with pytest.raises(ValueError, match="asıl öğretmen üye"):
        kurul.odk(
            [kurul.row(kurul.t1, chair=True), kurul.row(kurul.t2), kurul.row(kurul.sub)],
            chair_absent=True,
            minutes_type="CASE_REVIEW",
            discipline_case_id=case.pk,
        )


def test_katilimci_duzeltmesinde_vekalet_kaydi_eklenir_ve_kaldirilir(kurul: _Kurul) -> None:
    meeting = kurul.odk([kurul.chair_row(), kurul.row(kurul.t1), kurul.row(kurul.t2)])
    acting = [kurul.row(kurul.t1, chair=True), kurul.row(kurul.t2), kurul.row(kurul.sub)]
    # Kutu işaretlenmeden öğretmen üye başkan yapılamaz.
    with pytest.raises(ValueError, match="Başkan toplantıya katılmadı"):
        services.update_council_meeting(meeting, attendees=acting)
    services.update_council_meeting(meeting, attendees=acting, chair_absent=True)
    meeting.refresh_from_db()
    assert meeting.chair_absent is True
    # Yalnız katılımcı düzeltmesi vekâlet kaydını korur.
    services.update_council_meeting(meeting, attendees=acting)
    meeting.refresh_from_db()
    assert meeting.chair_absent is True
    # Kutu kaldırılırsa başkan yeniden katılımcı ve başkan olmalıdır.
    with pytest.raises(ValueError, match="Başkan toplantıya katılmadı"):
        services.update_council_meeting(meeting, chair_absent=False)
    services.update_council_meeting(
        meeting,
        attendees=[kurul.chair_row(), kurul.row(kurul.t1), kurul.row(kurul.t2)],
        chair_absent=False,
    )
    meeting.refresh_from_db()
    assert meeting.chair_absent is False


def test_eski_kayitta_baskani_degismeyen_toplanti_duzeltilebilir(kurul: _Kurul) -> None:
    """S7 öncesi kaydedilmiş, öğretmen üyenin "başkan" işaretlendiği toplantı: başkan satırı
    aynı kaldıkça düzeltme engellenmez (eski kayıt kilitlenmez — §7.6)."""
    meeting = kurul.odk([kurul.chair_row(), kurul.row(kurul.t1), kurul.row(kurul.t2)])
    CouncilMeetingAttendee.objects.filter(meeting=meeting).update(is_chair=False)
    CouncilMeetingAttendee.objects.filter(
        meeting=meeting, member_user_id=kurul.t1.member_user_id
    ).update(is_chair=True)
    services.update_council_meeting(
        meeting,
        attendees=[
            {**kurul.chair_row(), "is_chair": False},
            kurul.row(kurul.t1, chair=True),
            kurul.row(kurul.t2),
            kurul.row(kurul.parent),
        ],
    )
    assert meeting.attendees.count() == 4


def test_karar_defteri_vekaletli_toplantida_baskanlik_edeni_md188_unvaniyla_basar(
    kurul: _Kurul,
) -> None:
    meeting = kurul.odk(
        [kurul.row(kurul.t1, chair=True), kurul.row(kurul.t2), kurul.row(kurul.sub)],
        chair_absent=True,
    )
    ctx = doc_engine._council_minutes_context(meeting)
    assert ctx["chair"].person_name == kurul.t1.member_name
    assert ctx["chair"].title == "Kurula Başkanlık Eden Öğretmen Üye (md. 188)"
    assert ctx["signer_rows"][0][0] is ctx["chair"]
    html = _html(_MINUTES, ctx)
    # Katılmayan başkan katılanlar tablosunda ve imza ızgarasında yoktur; adı yalnız
    # "toplantıya katılmamış" cümlesinde geçer (K1).
    assert html.count(kurul.chair.full_name) == 1
    assert html.count("Kurula Başkanlık Eden Öğretmen Üye (md. 188)") == 2  # tablo + imza
    # Kayıt değişmez: unvan yalnız bağlamda eklenir.
    assert meeting.attendees.get(is_chair=True).title == "Öğretmen"


def test_karar_defteri_vekaletsiz_toplantida_hic_degismez(kurul: _Kurul) -> None:
    meeting = kurul.odk([kurul.chair_row(), kurul.row(kurul.t1), kurul.row(kurul.t2)])
    ctx = doc_engine._council_minutes_context(meeting)
    assert isinstance(ctx["chair"], CouncilMeetingAttendee)
    assert all(isinstance(a, CouncilMeetingAttendee) for a in ctx["voting_members"])
    assert "md. 188" not in _html(_MINUTES, ctx)


# ---------------------------------------------------------------------------
# Onur Kurulu (md. 182) — kapsam dışı, etkilenmez
# ---------------------------------------------------------------------------
def test_onur_kurulu_toplantisi_etkilenmez_ve_vekalet_kaydi_kabul_etmez(kurul: _Kurul) -> None:
    meeting = council_meeting(kurul.year, council_type="HONOR", on=date(2026, 5, 25))
    assert meeting.chair_absent is False
    assert council_service.meeting_quorum(meeting) is None
    ctx = doc_engine._council_minutes_context(meeting)
    assert isinstance(ctx["chair"], CouncilMeetingAttendee)
    rows = [
        {"person_name": "Onur Başkanı", "attendee_role": "VOTING_MEMBER", "is_chair": True},
        {"person_name": "Öğrenci Üye", "attendee_role": "VOTING_MEMBER", "is_chair": False},
    ]
    with pytest.raises(ValueError, match="yalnız Ödül ve Disiplin Kurulu"):
        services.create_council_meeting(
            school_year_id=kurul.year.pk,
            council_type="HONOR",
            meeting_date=date(2026, 5, 26),
            attendees=rows,
            chair_absent=True,
        )
    with pytest.raises(ValueError, match="yalnız Ödül ve Disiplin Kurulu"):
        services.update_council_meeting(meeting, chair_absent=True)
    # Onur Kurulunda başkan satırı serbest kalır (kurul başkanı eşleşmesi aranmaz).
    services.update_council_meeting(meeting, attendees=rows)


# ---------------------------------------------------------------------------
# API — tipler serializer ile birebir
# ---------------------------------------------------------------------------
def test_api_dosya_toplantisi_vekalet_alanlari(kurul: _Kurul) -> None:
    case = kurul.case(petitioner_user_id=kurul.chair.pk)
    client = APIClient()
    url = f"/api/v1/discipline/cases/{case.pk}/meeting/"
    body = {
        "meeting_date": "2026-05-21",
        "attendee_member_ids": [kurul.t1.pk, kurul.t2.pk, kurul.sub.pk],
    }
    rejected = client.post(url, body, format="json")
    assert rejected.status_code == 400
    assert "Başkan toplantıya katılmadı" in str(rejected.json())
    created = client.post(
        url, {**body, "chair_absent": True, "acting_chair_member_id": kurul.t1.pk}, format="json"
    )
    assert created.status_code == 201
    data = created.json()
    assert data["chair_absent"] is True
    assert data["acting_chair"] == kurul.t1.pk
    assert data["acting_chair_name"] == kurul.t1.member_name
    listed = client.get(url).json()
    assert listed[0]["acting_chair_name"] == kurul.t1.member_name


def test_api_baskanlik_secenekleri(kurul: _Kurul) -> None:
    client = APIClient()
    url = "/api/v1/discipline/committee/acting-chair-options/"
    plain = client.get(url).json()
    assert plain == {
        "chair": kurul.chair.pk,
        "chair_name": kurul.chair.full_name,
        "chair_conflicted": False,
        "eligible": [
            {
                "member_id": m.pk,
                "member_user": m.member_user_id,
                "member_name": m.member_name,
                "title": m.title,
            }
            for m in (kurul.t1, kurul.t2)
        ],
    }
    case = kurul.case(petitioner_user_id=kurul.chair.pk)
    services.add_participant(
        case, role=ParticipantRole.VICTIM, person_type="STAFF", person_id=kurul.t2.member_user_id
    )
    for_case = client.get(url, {"case": case.pk}).json()
    assert for_case["chair_conflicted"] is True
    assert [e["member_id"] for e in for_case["eligible"]] == [kurul.t1.pk]
    assert client.get(url, {"case": 999999}).status_code == 404


def test_api_kurul_toplantisi_vekalet_alani(kurul: _Kurul) -> None:
    client = APIClient()
    body = {
        "school_year": kurul.year.pk,
        "council_type": "DISCIPLINE",
        "meeting_date": "2026-06-01",
        "attendees": [kurul.row(kurul.t1, chair=True), kurul.row(kurul.t2), kurul.row(kurul.sub)],
    }
    assert client.post("/api/v1/council/meetings/", body, format="json").status_code == 400
    created = client.post(
        "/api/v1/council/meetings/", {**body, "chair_absent": True}, format="json"
    )
    assert created.status_code == 201
    data = created.json()
    assert data["chair_absent"] is True
    assert data["quorum"]["present"] == 3
    patched = client.patch(
        f"/api/v1/council/meetings/{data['id']}/",
        {
            "chair_absent": False,
            "attendees": [kurul.chair_row(), kurul.row(kurul.t1), kurul.row(kurul.t2)],
        },
        format="json",
    )
    assert patched.status_code == 200
    assert patched.json()["chair_absent"] is False


# ---------------------------------------------------------------------------
# Göç 0017 — eski şema → göç → doğrula → geri al
# ---------------------------------------------------------------------------
_BEFORE = [("disiplin", "0016_decision_prior_penalties_compiled")]
_AFTER = [("disiplin", "0017_meeting_chair_absence")]


@pytest.fixture
def old_schema() -> Iterator[Any]:
    """Veritabanını S7 öncesi şemaya indirir; test bitince en güncel şemaya çıkarır."""
    executor = MigrationExecutor(connection)
    executor.migrate(_BEFORE)
    try:
        yield executor.loader.project_state(_BEFORE).apps
    finally:
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())


def _migrate(target: list[tuple[str, str]]) -> Any:
    executor = MigrationExecutor(connection)
    executor.migrate(target)
    return executor.loader.project_state(target).apps


@pytest.mark.django_db(transaction=True)
def test_s7_goc_mevcut_toplantilari_baskan_katildi_kabul_eder(old_schema: Any) -> None:
    year = old_schema.get_model("okul", "SchoolYear").objects.create(
        name="2025-2026", start_date=date(2025, 9, 8), end_date=date(2026, 6, 26), is_active=True
    )
    case = old_schema.get_model("disiplin", "DisciplineCase").objects.create(
        case_no="2025-2026-0001",
        petition_date=date(2026, 3, 2),
        petitioner_name="İdare",
        petitioner_role="IDARE",
        summary="Eski sürümden kalan dosya.",
    )
    old_meeting = old_schema.get_model("disiplin", "DisciplineMeeting").objects.create(
        case=case, meeting_date=date(2026, 3, 9), notes="Eski toplantı."
    )
    old_council = old_schema.get_model("disiplin", "CouncilMeeting").objects.create(
        school_year=year, council_type="DISCIPLINE", meeting_no=1, meeting_date=date(2026, 3, 9)
    )

    new_apps = _migrate(_AFTER)
    meeting = new_apps.get_model("disiplin", "DisciplineMeeting").objects.get(pk=old_meeting.pk)
    assert meeting.chair_absent is False
    assert meeting.acting_chair_id is None
    assert meeting.notes == "Eski toplantı."
    council = new_apps.get_model("disiplin", "CouncilMeeting").objects.get(pk=old_council.pk)
    assert council.chair_absent is False

    # Geri alınabilir: sütunlar düşer, toplantı kayıtları kalır.
    back = _migrate(_BEFORE)
    assert (
        back.get_model("disiplin", "DisciplineMeeting")
        .objects.filter(pk=old_meeting.pk, notes="Eski toplantı.")
        .exists()
    )
    assert back.get_model("disiplin", "CouncilMeeting").objects.filter(pk=old_council.pk).exists()


# ---------------------------------------------------------------------------
# Gözden geçirme düzeltmeleri (14.11.2026)
# ---------------------------------------------------------------------------
_BLANK = "…………………………"


def _eski_toplanti(case: DisciplineCase, members: list[DisciplineCommitteeMember]) -> None:
    """S7 öncesi sürümde kaydedilmiş (vekâlet alanı olmayan) dosya toplantısını taklit eder."""
    from apps.disiplin.models import DisciplineMeeting

    meeting = DisciplineMeeting.objects.create(case=case, meeting_date=_ON)
    meeting.attendees.set(members)


@pytest.mark.parametrize("kayit", ["toplantisiz", "eski_toplanti"])
@pytest.mark.parametrize("engel", ["sikayetci", "zarar_goren"])
def test_vekalet_kaydi_olmayan_dosyada_engelli_baskan_izgarada_basilmaz(
    kurul: _Kurul, kayit: str, engel: str
) -> None:
    """md. 191/2: şikâyetçi / zarar gören başkan, toplantı kaydı (ya da vekâlet kaydı) olmasa
    da EK-1, Form-11 ve md. 195 ızgarasında basılmaz — hane adı elle doldurulmak üzere boştur."""
    if engel == "sikayetci":
        case = kurul.case(petitioner_user_id=kurul.chair.pk)
    else:
        case = kurul.case()
        services.add_participant(
            case, role=ParticipantRole.VICTIM, person_type="STAFF", person_id=kurul.chair.pk
        )
    if kayit == "eski_toplanti":
        _eski_toplanti(case, [kurul.t1, kurul.t2, kurul.parent])
    for template, ctx in (
        (_EK1, doc_engine._ek1_context(case, case.students.get())),
        (_GRID, doc_engine._committee_signers_context(case)),
    ):
        html = _html(template, ctx)
        assert kurul.chair.full_name not in html
        assert _BLANK in html
        assert "md. 188" not in html  # başkanlık eden kayıtlı değil — ad uydurulmaz
        assert kurul.t1.member_name in html
        assert kurul.t2.member_name in html
        # Kurulun diğer alanları aynen devredilir; kayıt değişmez.
        assert ctx["committee"].school_year_id == kurul.committee.school_year_id
    kurul.committee.refresh_from_db()
    assert kurul.committee.chair_id == kurul.chair.pk


def test_baskani_degisen_kurulda_eski_toplanti_arayuzden_duzeltilebilir(kurul: _Kurul) -> None:
    """§7.6: başkan yıl içinde değişti (md. 188; geçmişi tutulmaz). Arayüz `chair_absent`'i
    HER kayıtta gönderir; vekâlet durumu ve başkan satırı değişmiyorsa düzeltme engellenmez."""
    meeting = kurul.odk([kurul.chair_row(), kurul.row(kurul.t1), kurul.row(kurul.t2)])
    new_chair = PersonnelFactory(first_name="YENİ", last_name="BAŞKAN")
    services.set_committee_chair(kurul.committee, new_chair.pk)
    rows = [kurul.chair_row(), kurul.row(kurul.t1), kurul.row(kurul.t2), kurul.row(kurul.parent)]
    response = APIClient().patch(
        f"/api/v1/council/meetings/{meeting.pk}/",
        {"chair_absent": False, "attendees": rows},
        format="json",
    )
    assert response.status_code == 200, response.json()
    assert meeting.attendees.count() == 4
    # Başkan satırı DEĞİŞTİRİLİRSE kural yine uygulanır.
    with pytest.raises(ValueError, match="kurul başkanı değil"):
        services.update_council_meeting(
            meeting,
            attendees=[kurul.row(kurul.t1, chair=True), kurul.row(kurul.t2)],
            chair_absent=False,
        )


def test_baskanlik_eden_kuruldan_cikarilsa_da_vekaletli_toplanti_duzeltilebilir(
    kurul: _Kurul,
) -> None:
    """§7.6: vekâletli toplantıdan sonra başkanlık eden öğretmen kuruldan çıkarıldı; kayıtlı
    başkanlık eden aynı kaldıkça katılımcı düzeltmesi engellenmez."""
    acting = [kurul.row(kurul.t1, chair=True), kurul.row(kurul.t2), kurul.row(kurul.sub)]
    meeting = kurul.odk(acting, chair_absent=True)
    services.remove_committee_member(kurul.t1)
    # Yedek yerine veli yazılır (düzeltme); başkanlık eden satırı aynen kalır.
    services.update_council_meeting(
        meeting,
        attendees=[kurul.row(kurul.t1, chair=True), kurul.row(kurul.t2), kurul.row(kurul.parent)],
        chair_absent=True,
    )
    assert meeting.attendees.filter(person_name=kurul.parent.member_name).exists()
    meeting.refresh_from_db()
    assert meeting.chair_absent is True
    # Başkanlık eden DEĞİŞTİRİLİRSE md. 188 denetimi sürer (yedek başkanlık edemez).
    with pytest.raises(ValueError, match="asıl öğretmen üye"):
        services.update_council_meeting(
            meeting,
            attendees=[kurul.row(kurul.sub, chair=True), kurul.row(kurul.t2)],
            chair_absent=True,
        )


def test_dosya_toplantisinda_yedek_cagrilmadiysa_uyarilir_engellenmez(kurul: _Kurul) -> None:
    """md. 188: "Üyenin başkanlık yaptığı durumlarda yedek üye toplantıya katılır." — UYARI."""
    case = kurul.case()
    without = services.record_meeting(
        case,
        meeting_date=_ON,
        attendee_member_ids=[kurul.t1.pk, kurul.t2.pk, kurul.parent.pk],
        chair_absent=True,
        acting_chair_member_id=kurul.t1.pk,
    )
    warnings = services.meeting_chair_warnings(without)
    assert len(warnings) == 1
    assert "yedek üye" in warnings[0]
    assert "md. 188" in warnings[0]
    with_sub = services.record_meeting(
        case,
        meeting_date=date(2026, 5, 22),
        attendee_member_ids=[kurul.t1.pk, kurul.t2.pk, kurul.sub.pk],
        chair_absent=True,
        acting_chair_member_id=kurul.t1.pk,
    )
    assert services.meeting_chair_warnings(with_sub) == []
    plain = services.record_meeting(
        case, meeting_date=date(2026, 5, 25), attendee_member_ids=[kurul.t1.pk, kurul.t2.pk]
    )
    assert services.meeting_chair_warnings(plain) == []
    listed = APIClient().get(f"/api/v1/discipline/cases/{case.pk}/meeting/").json()
    assert [bool(m["chair_warnings"]) for m in listed] == [False, False, True]


def test_odk_toplantisinda_yedek_cagrilmadiysa_uyarilir_engellenmez(kurul: _Kurul) -> None:
    without = kurul.odk(
        [kurul.row(kurul.t1, chair=True), kurul.row(kurul.t2), kurul.row(kurul.parent)],
        chair_absent=True,
    )
    warnings = council_service.council_chair_warnings(without)
    assert len(warnings) == 1
    assert "yedek üye" in warnings[0]
    with_sub = kurul.odk(
        [kurul.row(kurul.t1, chair=True), kurul.row(kurul.t2), kurul.row(kurul.sub)],
        chair_absent=True,
    )
    assert council_service.council_chair_warnings(with_sub) == []
    plain = kurul.odk([kurul.chair_row(), kurul.row(kurul.t1), kurul.row(kurul.t2)])
    assert council_service.council_chair_warnings(plain) == []
    data = APIClient().get(f"/api/v1/council/meetings/{without.pk}/").json()
    assert data["chair_warnings"] == warnings


def test_dosya_gorusme_tutanagi_dosya_toplantisiyla_celisirse_uyarilir(kurul: _Kurul) -> None:
    """EK-1 dosya toplantısı kaydına, karar defteri tutanağa göre basılır: ikisi farklı
    başkan gösteriyorsa tutanakta UYARILIR (engellenmez)."""
    case = _case_with_decision(kurul, petitioner_user_id=None)
    kwargs: dict[str, Any] = {"minutes_type": "CASE_REVIEW", "discipline_case_id": case.pk}
    acting_t2 = [kurul.row(kurul.t2, chair=True), kurul.row(kurul.t1), kurul.row(kurul.sub)]
    # Dosya toplantısı kaydı yokken karşılaştırılacak bir şey yoktur.
    alone = kurul.odk(acting_t2, chair_absent=True, **kwargs)
    assert council_service.council_chair_warnings(alone) == []

    services.record_meeting(
        case, meeting_date=_ON, attendee_member_ids=[kurul.t1.pk, kurul.t2.pk, kurul.parent.pk]
    )
    absent_here = council_service.council_chair_warnings(alone)
    assert len(absent_here) == 1
    assert "dosyanın son kurul toplantısı kaydında" in absent_here[0]
    present_here = kurul.odk(
        [kurul.chair_row(), kurul.row(kurul.t1), kurul.row(kurul.t2)], **kwargs
    )
    assert council_service.council_chair_warnings(present_here) == []

    services.record_meeting(
        case,
        meeting_date=date(2026, 5, 22),
        attendee_member_ids=[kurul.t1.pk, kurul.t2.pk, kurul.sub.pk],
        chair_absent=True,
        acting_chair_member_id=kurul.t1.pk,
    )
    # Başkan tutanakta katılmış, dosya toplantısında katılmamış.
    assert len(council_service.council_chair_warnings(present_here)) == 1
    # İkisinde de vekâlet var ama başkanlık eden farklı (t2 ≠ t1).
    differs = council_service.council_chair_warnings(alone)
    assert len(differs) == 1
    assert kurul.t1.member_name in differs[0]
    assert kurul.t2.member_name in differs[0]
    same = kurul.odk(
        [kurul.row(kurul.t1, chair=True), kurul.row(kurul.t2), kurul.row(kurul.sub)],
        chair_absent=True,
        **kwargs,
    )
    assert council_service.council_chair_warnings(same) == []


def test_s7_kaynaklarinda_bozuk_kodlama_yok() -> None:
    """Türkçe yorum/docstring UTF-8 kalır (UTF-8 metnin Latin-1 sanılıp yeniden kodlanmış
    kalıntısı — "A-tilde", "A-diaeresis + artı-eksi" çiftleri — olmaz)."""
    from pathlib import Path

    root = Path(doc_engine.__file__).resolve().parent
    marks = (chr(0xC3), chr(0xC5) + chr(0x9F), chr(0xC4) + chr(0xB1))
    bad = [
        f"{path.relative_to(root)}:{no}"
        for path in sorted(root.rglob("*.py"))
        for no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if any(mark in line for mark in marks)
    ]
    assert bad == []


# ---------------------------------------------------------------------------
# Kullanıcının dört ek kararı (14.11.2026) — K1 etiket, K2 ileti, K3 bütün kurul evrakı,
# K4 eski kayıtta boş hane + uyarı; G1/G2 gerilemeleri
# ---------------------------------------------------------------------------
_ROLE = "Kurula Başkanlık Eden Öğretmen Üye (md. 188)"
_FORM10 = "disiplin/documents/meeting_call.html"
_FORM12 = "disiplin/documents/deadline_extension_record.html"
_FORM13 = "disiplin/documents/deadline_extension_petition.html"
_INDEX = "disiplin/documents/index_sheet.html"

# K1 — üç şablonda değişen parçalar: (yeni, S7 öncesi). Vekâletsiz çıktının BAYT BAYT aynı
# kaldığı, yeni parçalar eski hâline çevrilmiş şablonla karşılaştırılarak sabitlenir.
_K1_ROLE_NEW = "<div class=\"role\">{{ chair_role|default:'Başkan (Müdür Yrd.)' }}</div>"
_K1_ROLE_OLD = '<div class="role">Başkan (Müdür Yrd.)</div>'
_K1_FRAGMENTS: dict[str, list[tuple[str, str]]] = {
    _EK1: [(_K1_ROLE_NEW, _K1_ROLE_OLD)],
    _GRID: [(_K1_ROLE_NEW, _K1_ROLE_OLD)],
    _MINUTES: [
        (
            "{% if a.is_chair and not acting_chair %} <strong>(Başkan)</strong>{% endif %}",
            "{% if a.is_chair %} <strong>(Başkan)</strong>{% endif %}",
        ),
        (
            "</table>{% if chair_absence_note %}\n"
            '  <p class="para">{{ chair_absence_note }}</p>{% endif %}\n',
            "</table>\n",
        ),
    ],
}


def _template_source(name: str) -> str:
    from django.template.loader import get_template

    return str(get_template(name).template.source)  # type: ignore[attr-defined]


def _render_pre_s7(
    name: str,
    context: dict[str, Any],
    fragments: dict[str, list[tuple[str, str]]] | None = None,
) -> str:
    """Şablonun S7 öncesi hâliyle (K1 / etiket parçaları geri çevrilmiş) HAM çıktısı."""
    from django.template import engines

    source = _template_source(name)
    for new, old in (fragments or _K1_FRAGMENTS)[name]:
        assert source.count(new) == 1, f"{name}: K1 parçası bulunamadı: {new!r}"
        source = source.replace(new, old)
    return str(engines["django"].from_string(source).render(context))


def test_k1_vekaletsiz_ciktida_uc_sablon_bayt_bayt_ayni(kurul: _Kurul) -> None:
    """K1 izni yalnız vekâletli çıktıyı değiştirir: vekâletsiz toplantıda / toplantısız dosyada
    EK-1, Form-11 / md. 195 ızgarası ve karar defteri S7 öncesi şablonla BAYT BAYT aynıdır."""
    case = _case_with_decision(kurul, petitioner_user_id=None)
    services.record_meeting(
        case, meeting_date=_ON, attendee_member_ids=[kurul.t1.pk, kurul.t2.pk, kurul.parent.pk]
    )
    minutes = kurul.odk(
        [kurul.chair_row(), kurul.row(kurul.t1), kurul.row(kurul.t2)],
        minutes_type="CASE_REVIEW",
        discipline_case_id=case.pk,
    )
    plain_case = kurul.case()  # toplantı kaydı yok
    contexts = [
        (_EK1, doc_engine._ek1_context(case, case.students.get())),
        (_EK1, doc_engine._ek1_context(plain_case, plain_case.students.get())),
        (_GRID, doc_engine._committee_signers_context(case)),
        (_GRID, doc_engine._committee_signers_context(plain_case)),
        (_MINUTES, doc_engine._council_minutes_context(minutes)),
    ]
    for name, ctx in contexts:
        assert "chair_role" not in ctx
        assert not ctx.get("acting_chair")
        assert not ctx.get("chair_absence_note")
        now = render_to_string(name, ctx)
        assert now == _render_pre_s7(name, ctx), name
        assert "md. 188" not in now
    # Değişikliğin yanında karar notu durur (CLAUDE.md §1/3).
    for name in _K1_FRAGMENTS:
        assert "kullanıcı kararı, 14.11.2026 — S7" in _template_source(name)


def test_k1_vekaletli_ek1_ve_izgarada_etiket_md188_ad_satiri_yalin(kurul: _Kurul) -> None:
    case = _vekaletli_dosya(kurul)
    for name, ctx in (
        (_EK1, doc_engine._ek1_context(case, case.students.get())),
        (_GRID, doc_engine._committee_signers_context(case)),
    ):
        assert ctx["chair_role"] == _ROLE
        html = _html(name, ctx)
        assert (
            f'<div class="name">{kurul.t1.member_name}</div> <div class="role">{_ROLE}</div>'
            in html
        )
        assert "Başkan (Müdür Yrd.)" not in html
        assert f"{kurul.t1.member_name} —" not in html  # ifade etikette, ad satırında değil
        assert html.count(_ROLE) == 1


def test_k1_karar_defteri_vekaletli_toplantida_baskan_isareti_yok_ve_cumle_var(
    kurul: _Kurul,
) -> None:
    meeting = kurul.odk(
        [kurul.row(kurul.t1, chair=True), kurul.row(kurul.t2), kurul.row(kurul.sub)],
        chair_absent=True,
    )
    ctx = doc_engine._council_minutes_context(meeting)
    html = _html(_MINUTES, ctx)
    assert "(Başkan)" not in html
    assert html.count(_ROLE) == 2  # katılanlar tablosu (görev) + imza ızgarası
    assert (
        f"Kurul başkanı {kurul.chair.full_name} toplantıya katılmamış; kurula öğretmen üye "
        f"{kurul.t1.member_name} başkanlık etmiştir (md. 188)." in html
    )
    # Gerçek üretim (WeasyPrint): cümle ve md. 188 ifadesi PDF'te, "(Başkan)" işareti yok.
    text = _pdf_text(doc_engine.render_council_meeting_minutes(meeting))
    assert "toplantıya katılmamış" in text
    assert "(md. 188)" in text
    assert "(Başkan)" not in text
    plain = kurul.odk([kurul.chair_row(), kurul.row(kurul.t1), kurul.row(kurul.t2)])
    plain_text = _pdf_text(doc_engine.render_council_meeting_minutes(plain))
    assert "(Başkan)" in plain_text
    assert "md. 188" not in plain_text
    # Tek unvan sabiti: dört belgede aynı ifade.
    assert doc_engine.ACTING_CHAIR_ROLE == _ROLE
    assert not hasattr(doc_engine, "ACTING_CHAIR_ATTENDEE_ROLE")


def test_k1_karar_defteri_cumlesi_baskan_sonradan_baskanlik_eden_olduysa_ad_vermez(
    kurul: _Kurul,
) -> None:
    """Başkan geçmişi tutulmaz: başkanlık eden öğretmen sonradan kurul başkanı yapıldıysa
    tutanak "başkan X katılmamış; kurula X başkanlık etmiştir" demez — başkanın adı yazılmaz."""
    meeting = kurul.odk(
        [kurul.row(kurul.t1, chair=True), kurul.row(kurul.t2), kurul.row(kurul.sub)],
        chair_absent=True,
    )
    assert kurul.t1.member_user_id is not None
    services.set_committee_chair(kurul.committee, kurul.t1.member_user_id)
    meeting = CouncilMeeting.objects.get(pk=meeting.pk)
    html = _html(_MINUTES, doc_engine._council_minutes_context(meeting))
    assert (
        "Kurul başkanı toplantıya katılmamış; kurula öğretmen üye "
        f"{kurul.t1.member_name} başkanlık etmiştir (md. 188)." in html
    )


def _pdf_pages(pdf: bytes) -> list[Any]:
    from io import BytesIO

    from pypdf import PdfReader

    return list(PdfReader(BytesIO(pdf)).pages)


def _pdf_text(pdf: bytes) -> str:
    return " ".join(" ".join((page.extract_text() or "").split()) for page in _pdf_pages(pdf))


def test_k1_vekaletli_ek1_pdf_uzun_adla_sayfa_sayisi_degismez(kurul: _Kurul) -> None:
    """Gerçek üretim (WeasyPrint): md. 188 ifadesi etikete taşındığı için uzun adlı başkanlık
    eden üye dar başkan hanesini taşırmaz — vekâletli EK-1 vekâletsizle aynı sayfa sayısındadır."""
    long_name = kurul._teacher("ABDURRAHMAN GAZİOSMANPAŞA", "KARAOSMANOĞULLARI YILDIRIMTÜRK")
    plain = _case_with_decision(kurul, petitioner_user_id=None)
    services.record_meeting(
        plain, meeting_date=_ON, attendee_member_ids=[kurul.t1.pk, kurul.t2.pk, long_name.pk]
    )
    acting = _case_with_decision(kurul, petitioner_user_id=kurul.chair.pk)
    services.record_meeting(
        acting,
        meeting_date=_ON,
        attendee_member_ids=[kurul.t1.pk, kurul.t2.pk, long_name.pk, kurul.sub.pk],
        chair_absent=True,
        acting_chair_member_id=long_name.pk,
    )
    pages: dict[str, int] = {}
    for key, case in (("plain", plain), ("acting", acting)):
        pdf, _doc = doc_engine.generate_document(
            case,
            document_type="COMMITTEE_DECISION",
            generated_on=date(2026, 5, 29),
            student_id=case.students.get().pk,
            log=False,
        )
        pages[key] = len(_pdf_pages(pdf))
        text = _pdf_text(pdf)
        if key == "acting":
            assert "Kurula Başkanlık Eden" in text
            assert "(md. 188)" in text
            assert kurul.chair.full_name not in text
            assert "Başkan (Müdür Yrd.)" not in text
        else:
            assert "Başkan (Müdür Yrd.)" in text
            assert "md. 188" not in text
    assert pages["acting"] == pages["plain"]


# --- K2 — aday yokken ileti kurul bileşimini bozan çözüm önermez -----------------
def test_k2_aday_yokken_ileti_uye_eklemeyi_onermez_dayanagi_soyler(kurul: _Kurul) -> None:
    services.remove_committee_member(kurul.t1)
    services.remove_committee_member(kurul.t2)
    case = kurul.case(petitioner_user_id=kurul.chair.pk)
    with pytest.raises(ValueError, match="asıl öğretmen üye yok") as err:
        services.record_meeting(
            case, meeting_date=_ON, attendee_member_ids=[kurul.parent.pk, kurul.sub.pk]
        )
    message = str(err.value)
    # md. 185/1 "iki öğretmen" bileşimini büyüten öneri yok; metnin kendi yolu söylenir.
    assert "ekleyin" not in message
    assert "md. 185/1-b" not in message
    assert "md. 186" in message
    assert "md. 187" in message
    assert "md. 188" in message


# --- K3 — şikâyetçi / zarar gören başkan dosyanın bütün kurul evrakından çıkar ------
def _k3_documents(case: DisciplineCase) -> list[tuple[str, str, dict[str, Any]]]:
    """(ad, şablon, bağlam): kurul başkanını basan, `_signing_panel` DIŞI belgeler."""
    student = case.students.get()
    witness = services.add_participant(
        case, role=ParticipantRole.WITNESS, person_type="EXTERNAL", external_name="Komşu Tanık"
    )
    if not case.deadline_extensions.exists():
        services.create_extension(
            case, requested_days=5, reason="Tanık dinlenecek.", decided_on=date(2026, 5, 20)
        )
    base = "disiplin/documents/"
    ext = doc_engine._deadline_extension_context(case, {})
    notice = doc_engine._penalty_notice_context(case, student)
    return [
        ("form10", _FORM10, doc_engine._meeting_call_context(case, {})),
        ("form12", _FORM12, ext),
        ("form13", _FORM13, ext),
        (
            "form3",
            f"{base}statement_call.html",
            doc_engine._statement_call_context(case, witness, {}),
        ),
        (
            "form4",
            f"{base}statement_record.html",
            doc_engine._statement_record_context(case, witness, {}),
        ),
        (
            "form7",
            f"{base}info_gathering.html",
            doc_engine._info_gathering_context(case, witness, {}),
        ),
        ("form9", f"{base}defense_call.html", doc_engine._defense_call_context(case, witness, {})),
        ("dizi", _INDEX, doc_engine._index_sheet_context(case)),
        ("form14", f"{base}penalty_notice.html", notice),
        ("form15", f"{base}penalty_notice_parent.html", notice),
        (
            "form16",
            f"{base}penalty_days_notice.html",
            doc_engine._penalty_days_notice_context(case, student),
        ),
    ]


_K3_NOTICES = {"form14", "form15", "form16"}


def test_k3_sikayetci_baskan_vekaletli_dosyada_butun_kurul_evrakinda_basilmaz(
    kurul: _Kurul,
) -> None:
    """Vekâletli toplantı kaydı varsa başkan hanesinde başkanlık eden üye (md. 188 ifadesiyle);
    ceza tebliğlerinde ("Tebliğ Eden — Müdür Yardımcısı") hane boş kalır."""
    case = _case_with_decision(kurul, petitioner_user_id=kurul.chair.pk)
    services.record_meeting(
        case,
        meeting_date=_ON,
        attendee_member_ids=[kurul.t1.pk, kurul.t2.pk, kurul.sub.pk],
        chair_absent=True,
        acting_chair_member_id=kurul.t1.pk,
    )
    for key, template, ctx in _k3_documents(case):
        html = _html(template, ctx)
        assert kurul.chair.full_name not in html, key
        if key in _K3_NOTICES:
            assert _BLANK in html, key
            assert "md. 188" not in html, key
        elif key == "dizi":
            assert ctx["compiler_name"] == kurul.t1.member_name
            assert ctx["compiler_role"] == f"Düzenleyen / {_ROLE}"
        else:
            # Etiket kararı (14.11.2026): md. 188 ifadesi hane ETİKETİNDE, ad satırı yalın.
            assert _ROLE in html, key
            assert kurul.t1.member_name in html, key
            assert f"{kurul.t1.member_name} —" not in html, key
            assert "Disiplin Kurulu Başkanı" not in html, key
        if key == "form12":
            # Başkanlık eden üye ızgarada bir kez imzalar (başkan hanesi), üye hanesinde değil.
            assert html.count(f'<div class="name">{kurul.t1.member_name}') == 1
    kurul.committee.refresh_from_db()
    assert kurul.committee.chair_id == kurul.chair.pk  # kayıt değişmez


@pytest.mark.parametrize("kayit", ["toplantisiz", "eski_toplanti"])
def test_k3_sikayetci_baskan_vekalet_kaydi_yokken_butun_kurul_evrakinda_bos_hane(
    kurul: _Kurul, kayit: str
) -> None:
    case = _case_with_decision(kurul, petitioner_user_id=None)
    services.add_participant(
        case, role=ParticipantRole.VICTIM, person_type="STAFF", person_id=kurul.chair.pk
    )
    if kayit == "eski_toplanti":
        _eski_toplanti(case, [kurul.t1, kurul.t2, kurul.parent])
    for key, template, ctx in _k3_documents(case):
        html = _html(template, ctx)
        assert kurul.chair.full_name not in html, key
        assert "md. 188" not in html, key  # başkanlık eden kayıtlı değil — ad uydurulmaz
        if key == "dizi":
            assert ctx["compiler_name"] == ""
            assert ctx["compiler_role"] == "Düzenleyen / Disiplin Kurulu Başkanı"
            assert "……" in html
        else:
            assert _BLANK in html, key


@pytest.mark.parametrize("vekalet", [False, True], ids=["vekaletsiz", "izinli_baskan_vekaletli"])
def test_k3_baskan_sikayetci_degilse_kurul_evraki_aynen_kalir(kurul: _Kurul, vekalet: bool) -> None:
    """Başkan şikâyetçi / zarar gören DEĞİLSE bu belgeler (başkan izinli olduğu için vekâletli
    toplantı kaydı olsa bile) kurulun gerçek kaydını basar — bağlam S7 öncesiyle aynı nesnedir."""
    case = _case_with_decision(kurul, petitioner_user_id=None)
    if vekalet:
        services.record_meeting(
            case,
            meeting_date=_ON,
            attendee_member_ids=[kurul.t1.pk, kurul.t2.pk, kurul.sub.pk],
            chair_absent=True,
            acting_chair_member_id=kurul.t1.pk,
        )
    for key, template, ctx in _k3_documents(case):
        html = _html(template, ctx)
        assert "md. 188" not in html, key
        assert kurul.chair.full_name in html, key
        if key == "dizi":
            assert ctx["compiler_name"] == kurul.chair.full_name
            assert ctx["compiler_role"] == "Düzenleyen / Disiplin Kurulu Başkanı"
            continue
        assert isinstance(ctx["committee"], DisciplineCommittee), key
        assert ctx["committee"].pk == kurul.committee.pk
        if "members" in ctx:
            assert [m.pk for m in ctx["members"]] == [
                m.pk for m in kurul.committee.members.all()
            ], key


def test_k3_gercek_uretim_form10_ve_form12_pdf(kurul: _Kurul) -> None:
    """Gerçek üretim (WeasyPrint): şikâyetçi başkanın vekâletli dosyasında Form-10 ve Form-12
    PDF'i başkanı basmaz, başkanlık eden üyeyi md. 188 ifadesiyle basar; sayfa sayısı başkanı
    şikâyetçi olmayan aynı dosyanın çıktısıyla aynıdır (uzun ad satırı taşma yapmaz)."""
    pages: dict[tuple[str, str], int] = {}
    for key, petitioner in (("plain", None), ("acting", kurul.chair.pk)):
        case = _case_with_decision(kurul, petitioner_user_id=petitioner)
        services.record_meeting(
            case,
            meeting_date=_ON,
            attendee_member_ids=[kurul.t1.pk, kurul.t2.pk, kurul.sub.pk],
            chair_absent=True,
            acting_chair_member_id=kurul.t1.pk,
        )
        services.create_extension(
            case, requested_days=5, reason="Tanık dinlenecek.", decided_on=date(2026, 5, 20)
        )
        for document_type in ("MEETING_CALL", "DEADLINE_EXTENSION"):
            pdf, _doc = doc_engine.generate_document(
                case, document_type=document_type, generated_on=date(2026, 5, 20), log=False
            )
            pages[(key, document_type)] = len(_pdf_pages(pdf))
            text = _pdf_text(pdf)
            if key == "acting":
                assert kurul.chair.full_name not in text, document_type
                assert kurul.t1.member_name in text, document_type
                assert "(md. 188)" in text, document_type
            else:
                assert kurul.chair.full_name in text, document_type
                assert "md. 188" not in text, document_type
    for document_type in ("MEETING_CALL", "DEADLINE_EXTENSION"):
        assert pages[("acting", document_type)] == pages[("plain", document_type)]


# --- Etiket kararı (kullanıcı, 14.11.2026 — "Evet, değişsin"): Form-3, 4-6, 7-8, 9, 10, 12,
# 13'te sabit başkan etiketi de vekâlete göre değişir; Form-12/13 gövdesi; Form-10 tablosu ---
_FORM3 = "disiplin/documents/statement_call.html"
_FORM4 = "disiplin/documents/statement_record.html"
_FORM7 = "disiplin/documents/info_gathering.html"
_FORM9 = "disiplin/documents/defense_call.html"
_LABEL_KEYS = ("form10", "form12", "form13", "form3", "form4", "form7", "form9")

_LBL_LONG = (
    "<div class=\"role\">{{ chair_role|default:'Disiplin Kurulu Başkanı (Müdür Yrd.)' }}</div>",
    '<div class="role">Disiplin Kurulu Başkanı (Müdür Yrd.)</div>',
)
_LBL_SHORT = (
    "<div class=\"role\">{{ chair_role|default:'Disiplin Kurulu Başkanı' }}</div>",
    '<div class="role">Disiplin Kurulu Başkanı</div>',
)
_LBL_CELL = (
    "      {{ chair_role|default:'Disiplin Kurulu Başkanı' }}\n    </td>",
    "      Disiplin Kurulu Başkanı\n    </td>",
)
# (yeni, bu karardan önceki) — yedi şablonda değişen bütün parçalar.
_LABEL_FRAGMENTS: dict[str, list[tuple[str, str]]] = {
    _FORM10: [_LBL_LONG],
    _FORM12: [
        _LBL_LONG,
        (
            "  tarihinde {{ chair_presiding|default:'Disiplin Kurulu Başkanı' }}\n",
            "  tarihinde Disiplin Kurulu Başkanı\n",
        ),
    ],
    _FORM13: [
        _LBL_LONG,
        (
            "başlatılan ve {{ chair_office|default:'Disiplin Kurulu Başkanlığım' }} tarafından",
            "başlatılan ve Disiplin Kurulu Başkanlığım tarafından",
        ),
    ],
    _FORM3: [_LBL_CELL],
    _FORM9: [_LBL_CELL],
    _FORM4: [_LBL_SHORT],
    _FORM7: [_LBL_SHORT],
}
_LABEL_CONTEXT_KEYS = ("chair_role", "chair_presiding", "chair_office")


def _label_documents(case: DisciplineCase) -> list[tuple[str, str, dict[str, Any]]]:
    return [doc for doc in _k3_documents(case) if doc[0] in _LABEL_KEYS]


def _sikayetci_vekaletli(kurul: _Kurul) -> DisciplineCase:
    case = _case_with_decision(kurul, petitioner_user_id=kurul.chair.pk)
    services.record_meeting(
        case,
        meeting_date=_ON,
        attendee_member_ids=[kurul.t1.pk, kurul.t2.pk, kurul.sub.pk],
        chair_absent=True,
        acting_chair_member_id=kurul.t1.pk,
    )
    return case


def test_etiket_vekaletli_dosyada_yedi_sablonda_md188_ad_satiri_yalin(kurul: _Kurul) -> None:
    case = _sikayetci_vekaletli(kurul)
    docs = _label_documents(case)
    assert sorted(key for key, _t, _c in docs) == sorted(_LABEL_KEYS)
    name = kurul.t1.member_name
    for key, template, ctx in docs:
        assert ctx["chair_role"] == _ROLE, key
        html = _html(template, ctx)
        assert html.count(_ROLE) == 1, key
        # Eski sabit etiket ve satır içi ek YOK; katılmayan başkan YOK.
        assert "Disiplin Kurulu Başkanı" not in html, key
        assert "Müdür Yrd." not in html, key
        assert f"{name} —" not in html, key
        assert kurul.chair.full_name not in html, key
        if key in ("form3", "form9"):
            assert f"<strong>{name}</strong><br> {_ROLE} </td>" in html, key
        else:
            assert f'<div class="name">{name}</div> <div class="role">{_ROLE}</div>' in html, key
    # Tek sabit: etiket `documents.ACTING_CHAIR_ROLE`; satır içi ek kalktı.
    import inspect

    assert "role_inline" not in inspect.getsource(doc_engine)


def test_etiket_form12_ve_form13_govde_cumlesi_vekalete_gore(kurul: _Kurul) -> None:
    case = _sikayetci_vekaletli(kurul)
    docs = {key: (template, ctx) for key, template, ctx in _label_documents(case)}
    name = kurul.t1.member_name
    form12 = _html(*docs["form12"])
    assert (
        "tarihinde md. 188 gereğince kurula başkanlık eden öğretmen üye "
        f"<strong>{name}</strong> başkanlığında toplanarak" in form12
    )
    form13 = _html(*docs["form13"])
    assert (
        "başlatılan ve md. 188 uyarınca başkanlık ettiğim Disiplin Kurulu tarafından yürütülen "
        "disiplin soruşturması" in form13
    )
    assert "Başkanlığım" not in form13

    # Başkan şikâyetçi değilse gövde eski metindir.
    plain = _case_with_decision(kurul, petitioner_user_id=None)
    plain_docs = {key: (template, ctx) for key, template, ctx in _label_documents(plain)}
    assert (
        f"tarihinde Disiplin Kurulu Başkanı <strong>{kurul.chair.full_name}</strong> "
        "başkanlığında toplanarak" in _html(*plain_docs["form12"])
    )
    assert "Disiplin Kurulu Başkanlığım tarafından yürütülen" in _html(*plain_docs["form13"])


def test_etiket_form10_baskanlik_eden_uye_cagrilanlar_tablosunda_ikinci_kez_yok(
    kurul: _Kurul,
) -> None:
    """Çağrıyı imzalayan kişi kendini çağırmaz (Form-12'deki çift basmama ile aynı kural)."""
    case = _sikayetci_vekaletli(kurul)
    ctx = doc_engine._meeting_call_context(case, {})
    assert kurul.t1.pk not in [m.pk for m in ctx["members"]]
    html = _html(_FORM10, ctx)
    assert html.count(kurul.t1.member_name) == 1  # yalnız imza bloğu
    assert f"<td>{kurul.t1.member_name}</td>" not in html
    assert f"<td>{kurul.t2.member_name}</td>" in html
    assert f"<td>{kurul.parent.member_name}</td>" in html
    # Form-12 ızgarası da tek imza.
    form12 = _html(_FORM12, doc_engine._deadline_extension_context(case, {}))
    assert form12.count(f'<div class="name">{kurul.t1.member_name}</div>') == 1
    # Kurul kaydı değişmez.
    assert kurul.committee.members.filter(pk=kurul.t1.pk).exists()


def test_etiket_form10_vekaletli_dosyada_katilan_yedek_uye_cagrilanlar_tablosunda(
    kurul: _Kurul,
) -> None:
    """md. 188/1 "Üyenin başkanlık yaptığı durumlarda yedek üye toplantıya katılır", md. 191/2
    "yerine yedek üye toplantıya çağrılır": başkanlık eden üye tablodan çıkınca toplantı
    kaydında KATILAN yedek üye çağrılanlar arasında basılır (yalnız bağlam — AYNEN şablon
    yedekleri `is_substitute` ile gizler)."""
    case = _sikayetci_vekaletli(kurul)
    ctx = doc_engine._meeting_call_context(case, {})
    assert [m.pk for m in ctx["members"]] == [kurul.t2.pk, kurul.parent.pk, kurul.sub.pk]
    html = _html(_FORM10, ctx)
    sub = kurul.sub.member_name
    assert html.count(f"<td>{sub}</td>") == 1
    assert f"<td>3</td> <td>{sub}</td>" in html  # sıra numarası boşluksuz sürer
    # Form-12 ızgarası bu kuraldan etkilenmez (kurulun kendi listesi; yedek gizli).
    form12 = _html(_FORM12, doc_engine._deadline_extension_context(case, {}))
    assert sub not in form12
    # Kurul kaydı değişmez: üye hâlâ yedek.
    kurul.sub.refresh_from_db()
    assert kurul.sub.is_substitute is True

    # Toplantıya yedek üye katılmadıysa tabloya ad uydurulmaz.
    without = _case_with_decision(kurul, petitioner_user_id=kurul.chair.pk)
    services.record_meeting(
        without,
        meeting_date=_ON,
        attendee_member_ids=[kurul.t1.pk, kurul.t2.pk, kurul.parent.pk],
        chair_absent=True,
        acting_chair_member_id=kurul.t1.pk,
    )
    assert sub not in _html(_FORM10, doc_engine._meeting_call_context(without, {}))

    # Başkan şikâyetçi değilse (izinli başkan, vekâletli toplantı) tablo AYNEN: yedek yok.
    plain = _case_with_decision(kurul, petitioner_user_id=None)
    services.record_meeting(
        plain,
        meeting_date=_ON,
        attendee_member_ids=[kurul.t1.pk, kurul.t2.pk, kurul.sub.pk],
        chair_absent=True,
        acting_chair_member_id=kurul.t1.pk,
    )
    assert sub not in _html(_FORM10, doc_engine._meeting_call_context(plain, {}))


@pytest.mark.parametrize(
    "durum", ["vekaletsiz", "izinli_baskan_vekaletli", "sikayetci_kayitsiz", "eski_toplanti"]
)
def test_etiket_vekaletli_olmayan_ciktida_yedi_sablon_bayt_bayt_ayni(
    kurul: _Kurul, durum: str
) -> None:
    """Etiket izni yalnız "şikâyetçi / zarar gören başkan + vekâletli toplantı kaydı" çıktısını
    değiştirir. Başkan şikâyetçi değilse (vekâletsiz ya da izinli başkan) ve vekâlet kaydı yokken
    (boş hane, eski sabit etiket) yedi şablonun HAM çıktısı karar öncesi şablonla bayt bayt aynı."""
    conflicted = durum in ("sikayetci_kayitsiz", "eski_toplanti")
    case = _case_with_decision(kurul, petitioner_user_id=kurul.chair.pk if conflicted else None)
    if durum == "izinli_baskan_vekaletli":
        services.record_meeting(
            case,
            meeting_date=_ON,
            attendee_member_ids=[kurul.t1.pk, kurul.t2.pk, kurul.sub.pk],
            chair_absent=True,
            acting_chair_member_id=kurul.t1.pk,
        )
    elif durum == "eski_toplanti":
        _eski_toplanti(case, [kurul.t1, kurul.t2, kurul.parent])
    for key, template, ctx in _label_documents(case):
        for context_key in _LABEL_CONTEXT_KEYS:
            assert context_key not in ctx, (key, context_key)
        # Üye listesi kurulun kendi listesi (kimse çıkarılmaz).
        assert [m.pk for m in ctx["members"]] == [m.pk for m in kurul.committee.members.all()]
        now = render_to_string(template, ctx)
        assert now == _render_pre_s7(template, ctx, _LABEL_FRAGMENTS), key
        assert "md. 188" not in now, key
        # Kurul tanımlı değilken de aynı.
        empty = {**ctx, "committee": None, "members": []}
        assert render_to_string(template, empty) == _render_pre_s7(
            template, empty, _LABEL_FRAGMENTS
        ), key
        if conflicted:
            assert _BLANK in now, key
            assert kurul.chair.full_name not in now, key
        else:
            assert kurul.chair.full_name in now, key
    # Form-7/8'in öğretmen sürümü de aynı.
    witness = case.participants.get(role=ParticipantRole.WITNESS)
    teacher = doc_engine._info_gathering_context(case, witness, {"variant": "teacher"})
    assert render_to_string(_FORM7, teacher) == _render_pre_s7(_FORM7, teacher, _LABEL_FRAGMENTS)
    # Değişikliğin yanında karar notu durur (CLAUDE.md §1/3).
    for template in _LABEL_FRAGMENTS:
        assert "kullanıcı kararı, 14.11.2026 — S7" in _template_source(template)
        assert "text-transform" not in _template_source(template)


def test_etiket_ceza_tebliglerinde_tebligeden_hanesi_degismez(kurul: _Kurul) -> None:
    """Kapsam dışı: ceza tebliğlerinde ("Tebliğ Eden — Müdür Yardımcısı") hane boş kalır."""
    case = _sikayetci_vekaletli(kurul)
    for key, template, ctx in _k3_documents(case):
        if key not in _K3_NOTICES:
            continue
        assert "chair_role" not in ctx, key
        html = _html(template, ctx)
        assert _BLANK in html, key
        assert "md. 188" not in html, key
        assert kurul.t1.member_name not in html, key


def test_etiket_gercek_uretim_yedi_belgede_sayfa_sayisi_degismez(kurul: _Kurul) -> None:
    """Gerçek üretim (WeasyPrint): uzun adlı başkanlık eden üyeyle vekâletli dosyada yedi
    belgenin sayfa sayısı, başkanı şikâyetçi olmayan aynı dosyanın çıktısıyla aynıdır."""
    long_name = kurul._teacher("ABDURRAHMAN GAZİOSMANPAŞA", "KARAOSMANOĞULLARI YILDIRIMTÜRK")
    jobs: list[tuple[str, dict[str, Any]]] = [
        ("MEETING_CALL", {}),
        ("DEADLINE_EXTENSION", {"variant": doc_engine.VARIANT_RECORD}),
        ("DEADLINE_EXTENSION", {"variant": doc_engine.VARIANT_PETITION}),
        ("STATEMENT_CALL", {"participant": True}),
        ("STATEMENT_RECORD", {"participant": True}),
        ("INFO_GATHERING", {"participant": True, "variant": "student"}),
        ("INFO_GATHERING", {"participant": True, "variant": "teacher"}),
        ("DEFENSE_CALL", {"participant": True}),
    ]
    pages: dict[tuple[str, int], int] = {}
    for key, petitioner in (("plain", None), ("acting", kurul.chair.pk)):
        case = _case_with_decision(kurul, petitioner_user_id=petitioner)
        services.record_meeting(
            case,
            meeting_date=_ON,
            attendee_member_ids=[kurul.t1.pk, kurul.t2.pk, long_name.pk, kurul.sub.pk],
            chair_absent=True,
            acting_chair_member_id=long_name.pk,
        )
        services.create_extension(
            case, requested_days=5, reason="Tanık dinlenecek.", decided_on=date(2026, 5, 20)
        )
        accused = case.participants.get(role=ParticipantRole.ACCUSED)
        for index, (document_type, options) in enumerate(jobs):
            kwargs: dict[str, Any] = {"variant": options.get("variant", "")}
            if options.get("participant"):
                kwargs["participant_id"] = accused.pk
            pdf, _doc = doc_engine.generate_document(
                case,
                document_type=document_type,
                generated_on=date(2026, 5, 20),
                log=False,
                **kwargs,
            )
            pages[(key, index)] = len(_pdf_pages(pdf))
            text = _pdf_text(pdf)
            if key == "acting":
                assert kurul.chair.full_name not in text, document_type
                assert long_name.member_name in text, document_type
                assert "Kurula Başkanlık Eden" in text, document_type
                assert "(md. 188)" in text, document_type
                assert "Disiplin Kurulu Başkanı" not in text, document_type
            else:
                assert kurul.chair.full_name in text, document_type
                assert "Disiplin Kurulu Başkanı" in text, document_type
                assert "md. 188" not in text, document_type
    for index, (document_type, _options) in enumerate(jobs):
        assert pages[("acting", index)] == pages[("plain", index)], (document_type, index)


# --- K4 — eski kayıtta boş hane + kalıcı uyarı ------------------------------------
def test_k4_dosya_uyarisi_vekalet_kaydi_olmayan_engelli_baskanda_cikar(kurul: _Kurul) -> None:
    case = kurul.case(petitioner_user_id=kurul.chair.pk)
    url = f"/api/v1/discipline/cases/{case.pk}/"
    warnings = services.case_chair_warnings(case)
    assert len(warnings) == 1
    assert "md. 191/2" in warnings[0]
    assert "Başkan toplantıya katılmadı" in warnings[0]
    assert "başkan hanesi boş basılır" in warnings[0]
    assert APIClient().get(url).json()["chair_warnings"] == warnings

    # S7 öncesi (vekâletsiz) toplantı kaydı uyarıyı kaldırmaz; kayıt kendiliğinden değişmez.
    _eski_toplanti(case, [kurul.t1, kurul.t2, kurul.parent])
    legacy = services.case_chair_warnings(case)
    assert len(legacy) == 1
    assert "yeniden kaydedin" in legacy[0]
    assert "yeniden açın" not in legacy[0]
    old = case.meetings.get()
    assert old.chair_absent is False
    assert old.acting_chair_id is None

    # Kapalı dosyada toplantı kaydı reddedilir: uyarı önce yeniden açmayı söyler (§7.6).
    case.closed_at = timezone.now()
    closed = services.case_chair_warnings(case)
    assert "önce dosyayı yeniden açın" in closed[0]
    assert "yeniden kaydedin" in closed[0]
    case.closed_at = None

    # Vekâletli kayıt girilince uyarı kalkar.
    services.record_meeting(
        case,
        meeting_date=date(2026, 5, 22),
        attendee_member_ids=[kurul.t1.pk, kurul.t2.pk, kurul.sub.pk],
        chair_absent=True,
        acting_chair_member_id=kurul.t1.pk,
    )
    assert services.case_chair_warnings(case) == []
    assert APIClient().get(url).json()["chair_warnings"] == []


def test_k4_dosya_uyarisi_engelli_olmayan_baskanda_ve_sevksiz_dosyada_yoktur(
    kurul: _Kurul,
) -> None:
    assert services.case_chair_warnings(kurul.case()) == []
    unreferred = services.create_case(
        petition_date=date(2026, 5, 18),
        petitioner_name="İdare",
        petitioner_role="OGRETMEN",
        summary="Koridorda kavga.",
        student_ids=[StudentFactory().pk],
        petitioner_user_id=kurul.chair.pk,
    )
    # Kurula sevk edilmemiş dosyada kurul evrakı üretilmez — uyarı gürültü olurdu.
    assert services.case_chair_warnings(unreferred) == []


def test_k4_eski_dosya_gorusme_tutanagi_engelli_baskani_basar_ama_uyarir(kurul: _Kurul) -> None:
    """Son denetimin bulduğu çelişki: S7 öncesi (başkan katıldı) CASE_REVIEW tutanağı, başkanı
    şikâyetçi / zarar gören dosyada karar defterine başkanı OLDUĞU GİBİ basar; EK-1 başkan
    hanesi ise boştur. Kayıt değiştirilmez, tutanak ekranında UYARILIR."""
    case = _case_with_decision(kurul, petitioner_user_id=None)
    minutes = kurul.odk(
        [kurul.chair_row(), kurul.row(kurul.t1), kurul.row(kurul.t2)],
        minutes_type="CASE_REVIEW",
        discipline_case_id=case.pk,
    )
    assert council_service.council_chair_warnings(minutes) == []
    # Başkan sonradan zarar gören olarak eklenir (S7 öncesi kaydın eşdeğeri).
    services.add_participant(
        case, role=ParticipantRole.VICTIM, person_type="STAFF", person_id=kurul.chair.pk
    )
    minutes = CouncilMeeting.objects.get(pk=minutes.pk)
    warnings = council_service.council_chair_warnings(minutes)
    assert len(warnings) == 1
    assert "md. 191/2" in warnings[0]
    assert "Başkan toplantıya katılmadı" in warnings[0]
    data = APIClient().get(f"/api/v1/council/meetings/{minutes.pk}/").json()
    assert data["chair_warnings"] == warnings
    # Karar defteri eski kaydı olduğu gibi basar; EK-1 başkan hanesi boş.
    ctx = doc_engine._council_minutes_context(minutes)
    assert isinstance(ctx["chair"], CouncilMeetingAttendee)
    assert kurul.chair.full_name in _html(_MINUTES, ctx)
    ek1 = _html(_EK1, doc_engine._ek1_context(case, case.students.get()))
    assert kurul.chair.full_name not in ek1
    minutes.refresh_from_db()
    assert minutes.chair_absent is False
    # G1: eski tutanak, başkan satırı aynı kaldıkça vekâlete çevrilmeden düzeltilebilir.
    response = APIClient().patch(
        f"/api/v1/council/meetings/{minutes.pk}/",
        {
            "chair_absent": False,
            "attendees": [
                kurul.chair_row(),
                kurul.row(kurul.t1),
                kurul.row(kurul.t2),
                kurul.row(kurul.parent),
            ],
        },
        format="json",
    )
    assert response.status_code == 200, response.json()
    assert minutes.attendees.count() == 4


# --- G2 — yeter sayı: "katılmayan başkan sayılmaz" bugünkü başkana bakar -----------
def _t1_sonradan_baskan(kurul: _Kurul, *, uyelikten_once_cikti: bool) -> CouncilMeeting:
    rows = [kurul.row(kurul.t1, chair=True), kurul.row(kurul.t2)]
    if not uyelikten_once_cikti:
        rows.append(kurul.row(kurul.sub))
    meeting = kurul.odk(rows, chair_absent=True)
    if uyelikten_once_cikti:
        # Üyelik kaydı toplantı tarihinden ÖNCE silinmiş görünür: satır yalnız "bugünkü
        # başkan" olarak eşleşir (toplantı günü üye olduğu artık kanıtlanamaz).
        from datetime import datetime
        from zoneinfo import ZoneInfo

        DisciplineCommitteeMember.all_objects.filter(pk=kurul.t1.pk).update(
            deleted_at=datetime(2026, 5, 1, 12, tzinfo=ZoneInfo("Europe/Istanbul"))
        )
    assert kurul.t1.member_user_id is not None
    services.set_committee_chair(kurul.committee, kurul.t1.member_user_id)
    fresh: CouncilMeeting = CouncilMeeting.objects.get(pk=meeting.pk)
    return fresh


def test_g2_uye_olarak_katilan_sonradan_baskan_olursa_yeter_sayidan_dusmez(kurul: _Kurul) -> None:
    meeting = _t1_sonradan_baskan(kurul, uyelikten_once_cikti=False)
    detail = council_service.meeting_quorum_detail(meeting)
    assert detail is not None
    assert detail["present"] == 3  # t1 toplantı günü üyeydi — sayılır
    assert detail["ok"] is True
    assert detail["chair_skipped"] == []
    assert detail["unmatched"] == []


def test_g2_sayilmayan_baskan_satiri_nedeniyle_gorunur_ve_duzeltmeyi_engellemez(
    kurul: _Kurul,
) -> None:
    meeting = _t1_sonradan_baskan(kurul, uyelikten_once_cikti=True)
    detail = council_service.meeting_quorum_detail(meeting)
    assert detail is not None
    # Sessizce düşmez: sayılmayan satır nedeniyle ayrı listede görünür.
    assert detail["chair_skipped"] == [kurul.t1.member_name]
    assert detail["unmatched"] == []
    assert detail["present"] == 1
    assert detail["ok"] is False
    assert "chair_skipped" not in (council_service.meeting_quorum(meeting) or {})
    data = APIClient().get(f"/api/v1/council/meetings/{meeting.pk}/").json()
    assert data["quorum"]["chair_skipped"] == [kurul.t1.member_name]
    # Yeni karar için kural aynen sürer; mevcut toplantının düzeltilmesi bu yüzden reddedilmez.
    with pytest.raises(ValueError, match="yeter sayısı"):
        council_service._require_quorum(meeting)
    council_service._require_quorum(meeting, tolerate_chair_skip=True)
    # Gerçekten eksik katılım hoş görülmez.
    for attendee in meeting.attendees.filter(person_name=kurul.t2.member_name):
        attendee.delete()
    with pytest.raises(ValueError, match="yeter sayısı"):
        council_service._require_quorum(meeting, tolerate_chair_skip=True)
