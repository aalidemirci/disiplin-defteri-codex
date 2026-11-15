"""S7 / S8 açık kalemleri — kullanıcı kararları 15.11.2026 (K1, K4-K11).

K1  izinli başkan döndükten sonra çağrı / ifade evrakı (Form-3, 4-6, 7-8, 9, 10) işlem
    tarihine bakar; şikâyetçi / zarar gören başkanda tarih aranmaz.
K4  Form-12 imza ızgarası uzatma günündeki dosya toplantısına katılanları basar.
K5  vekâletli toplantıda katılmayan başkanın adı kayda yazılır; karar defteri onu basar.
K6  Form-10'da çağrılan yedek üyenin görevi "<görev> (Yedek Üye)".
K7  ileri tarihli toplantıya karar bağlanamaz.
K8  yeter sayı toplantı anındaki üye tam sayısından hesaplanır.
K9  dosya görüşme tutanağı ↔ kararların bağlı olduğu dosya toplantısı uyum uyarısı.
K10 md. 197 iadesinden sonra ilk görüşme tarihi saklanır.
K11 sevk öncesinde kalan eski (bağsız) silinmiş karar geri yüklenmez.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, timedelta
from typing import Any

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone
from rest_framework.test import APIClient

from apps.disiplin import documents as doc_engine
from apps.disiplin import services
from apps.disiplin.models import (
    CaseStage,
    CouncilMeeting,
    DisciplineCase,
    DisciplineDecision,
    DisciplineMeeting,
    DocumentType,
    ParticipantRole,
    PenaltyType,
    PrincipalDecision,
)
from apps.disiplin.services import council as council_service
from apps.disiplin.services.committee import case_meeting_quorum
from apps.disiplin.tests.factories import PersonnelFactory, legacy_decision
from apps.disiplin.tests.test_s7_vekalet import _html, _Kurul

pytestmark = pytest.mark.django_db

SEVK = date(2026, 5, 19)
T1 = date(2026, 5, 21)
T2 = date(2026, 5, 27)
T3 = date(2026, 6, 3)
_ROLE = "Kurula Başkanlık Eden Öğretmen Üye (md. 188)"
_BASE = "disiplin/documents/"
_FORM10 = f"{_BASE}meeting_call.html"
_FORM12 = f"{_BASE}deadline_extension_record.html"
_FORM13 = f"{_BASE}deadline_extension_petition.html"


@pytest.fixture
def kurul() -> _Kurul:
    """Başkan + 2 asıl öğretmen (t1, t2) + 1 asıl veli (tam sayı 4, yeter sayı 3) + 1 yedek."""
    return _Kurul()


def _present(kurul: _Kurul) -> list[int]:
    return [kurul.t1.pk, kurul.t2.pk, kurul.parent.pk]


def _acting_meeting(case: DisciplineCase, kurul: _Kurul, on: date = T1) -> DisciplineMeeting:
    """Başkan katılmadı; t1 başkanlık etti, yedek üye katıldı."""
    meeting: DisciplineMeeting = services.record_meeting(
        case,
        meeting_date=on,
        attendee_member_ids=[kurul.t1.pk, kurul.t2.pk, kurul.sub.pk],
        chair_absent=True,
        acting_chair_member_id=kurul.t1.pk,
    )
    return meeting


def _decide(case: DisciplineCase, meeting: DisciplineMeeting) -> DisciplineDecision:
    return services.record_decision(
        case,
        student_id=case.students.get().pk,
        penalty_type=PenaltyType.REPRIMAND,
        meeting=meeting,
    )


def _refer_again(case: DisciplineCase, on: date) -> None:
    """Sevki geri alıp `on` tarihiyle yeniden kurula sevk eder."""
    services.revert_stage(case, target_stage=CaseStage.PETITION, reason="Yanlış sevk.")
    case.refresh_from_db()
    services.add_event(
        case,
        CaseStage.DECIDED,
        on,
        override=True,
        override_reason="Rehberlik atlandı.",
        principal_decisions=[PrincipalDecision.DISCIPLINE_COMMITTEE],
    )
    case.refresh_from_db()


def _url(case: DisciplineCase, tail: str) -> str:
    return f"/api/v1/discipline/cases/{case.pk}/{tail}"


# ---------------------------------------------------------------------------
# K1 — dönen başkan: çağrı / ifade evrakı işlem tarihine bakar
# ---------------------------------------------------------------------------
def _call_documents(
    case: DisciplineCase, extra: dict[str, Any]
) -> list[tuple[str, str, dict[str, Any]]]:
    """(ad, şablon, bağlam): Form-3, 4-6, 7-8, 9, 10."""
    witness = case.participants.filter(role=ParticipantRole.WITNESS).first()
    if witness is None:
        witness = services.add_participant(
            case, role=ParticipantRole.WITNESS, person_type="EXTERNAL", external_name="Komşu Tanık"
        )
    return [
        ("form3", "statement_call", doc_engine._statement_call_context(case, witness, extra)),
        ("form4", "statement_record", doc_engine._statement_record_context(case, witness, extra)),
        ("form7", "info_gathering", doc_engine._info_gathering_context(case, witness, extra)),
        ("form9", "defense_call", doc_engine._defense_call_context(case, witness, extra)),
        ("form10", "meeting_call", doc_engine._meeting_call_context(case, extra)),
    ]


def test_k1_izinli_baskan_islem_tarihi_toplantidan_sonraysa_asil_baskan_basilir(
    kurul: _Kurul,
) -> None:
    case = kurul.case()
    _acting_meeting(case, kurul, T1)
    for key, template, ctx in _call_documents(case, {"statement_date": T2}):
        html = _html(f"{_BASE}{template}.html", ctx)
        assert "chair_role" not in ctx, key
        assert ctx["committee"].chair.pk == kurul.chair.pk, key
        assert kurul.chair.full_name in html, key
        assert "md. 188" not in html, key
    # Form-10: başkan döndü — çağrılanlar kurulun KENDİ listesi (başkanlık eden üye yeniden
    # çağrılır, yedek üye tabloda yok).
    call = doc_engine._meeting_call_context(case, {"statement_date": T2})
    assert [m.pk for m in call["members"]] == [
        kurul.t1.pk,
        kurul.t2.pk,
        kurul.parent.pk,
        kurul.sub.pk,
    ]
    assert "(Yedek Üye)" not in _html(_FORM10, call)


@pytest.mark.parametrize("on", [T1, date(2026, 5, 20)], ids=["ayni_gun", "onceki_gun"])
def test_k1_islem_tarihi_toplanti_gunu_ya_da_oncesiyse_baskanlik_eden_basilir(
    kurul: _Kurul, on: date
) -> None:
    case = kurul.case()
    _acting_meeting(case, kurul, T1)
    for key, template, ctx in _call_documents(case, {"statement_date": on}):
        html = _html(f"{_BASE}{template}.html", ctx)
        assert ctx["chair_role"] == _ROLE, key
        assert ctx["committee"].chair.get_full_name() == kurul.t1.member_name, key
        assert kurul.chair.full_name not in html, key


def test_k1_islem_tarihi_verilmediyse_uretim_tarihi_olcuttur(kurul: _Kurul) -> None:
    case = kurul.case()
    _acting_meeting(case, kurul, T1)
    after = doc_engine._meeting_call_context(case, {"statement_date": None, "generated_on": T2})
    assert "chair_role" not in after
    same = doc_engine._meeting_call_context(case, {"statement_date": None, "generated_on": T1})
    assert same["chair_role"] == _ROLE
    # Çağrılan toplantının tarihi verildiyse üretim tarihi ölçüt DEĞİLDİR.
    mixed = doc_engine._meeting_call_context(case, {"statement_date": T1, "generated_on": T3})
    assert mixed["chair_role"] == _ROLE
    # İkisi de yoksa (bağlam doğrudan kurulduysa) eski kural: son toplantı kaydı.
    assert doc_engine._meeting_call_context(case, {})["chair_role"] == _ROLE


def test_k1_sikayetci_baskanda_tarih_aranmaz(kurul: _Kurul) -> None:
    """md. 191/2: şikâyetçi / zarar gören başkan hiçbir oturuma katılamaz."""
    case = kurul.case(petitioner_user_id=kurul.chair.pk)
    _acting_meeting(case, kurul, T1)
    for key, template, ctx in _call_documents(case, {"statement_date": T3, "generated_on": T3}):
        html = _html(f"{_BASE}{template}.html", ctx)
        assert ctx["chair_role"] == _ROLE, key
        assert kurul.chair.full_name not in html, key


def test_k1_dizi_pusulasi_ve_form12_13_etkilenmez(kurul: _Kurul) -> None:
    case = kurul.case()
    _acting_meeting(case, kurul, T1)
    services.create_extension(case, requested_days=5, reason="Tanık dinlenecek.", decided_on=T1)
    ext = doc_engine._deadline_extension_context(case, {"generated_on": T3})
    assert ext["chair_role"] == _ROLE
    assert kurul.chair.full_name not in _html(_FORM12, ext)
    assert kurul.chair.full_name not in _html(_FORM13, ext)
    index = doc_engine._index_sheet_context(case)
    assert index["compiler_name"] == kurul.t1.member_name


def test_k1_gercek_uretimde_uretim_tarihi_baglama_tasinir(
    kurul: _Kurul, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`generate_document`: Form-10'da çağrılan toplantının tarihi (`statement_date`), o
    verilmediyse belgenin üretim tarihi (`generated_on`) işlem tarihidir."""
    case = kurul.case()
    _acting_meeting(case, kurul, T1)
    seen: list[dict[str, Any]] = []

    def _capture(template: str, context: dict[str, Any]) -> tuple[bytes, int]:
        seen.append(context)
        return b"%PDF-", 1

    monkeypatch.setattr(doc_engine, "render_pdf_paged", _capture)
    kwargs: dict[str, Any] = {"document_type": DocumentType.MEETING_CALL, "log": False}
    doc_engine.generate_document(case, generated_on=T2, **kwargs)
    doc_engine.generate_document(case, generated_on=T1, **kwargs)
    doc_engine.generate_document(case, generated_on=T3, statement_date=T1, **kwargs)
    assert "chair_role" not in seen[0]
    assert seen[1]["chair_role"] == _ROLE
    assert seen[2]["chair_role"] == _ROLE


# ---------------------------------------------------------------------------
# K4 — Form-12 imza ızgarası: uzatma günündeki toplantıya katılanlar
# ---------------------------------------------------------------------------
def _grid_names(ctx: dict[str, Any]) -> list[str]:
    return [m.member_name for m in ctx["members"] if not m.is_substitute]


def test_k4_uzatma_gunundeki_toplantiya_katilanlar_basilir_yedek_dahil(kurul: _Kurul) -> None:
    """Olağan durum (başkan katıldı): veli üye gelmedi, yerine yedek katıldı."""
    case = kurul.case()
    services.record_meeting(
        case, meeting_date=T1, attendee_member_ids=[kurul.t1.pk, kurul.t2.pk, kurul.sub.pk]
    )
    services.create_extension(case, requested_days=5, reason="Tanık dinlenecek.", decided_on=T1)
    ctx = doc_engine._deadline_extension_context(case, {})
    assert _grid_names(ctx) == [kurul.t1.member_name, kurul.t2.member_name, kurul.sub.member_name]
    assert ctx["committee"].chair.pk == kurul.chair.pk
    html = _html(_FORM12, ctx)
    assert kurul.sub.member_name in html
    assert kurul.parent.member_name not in html
    # Kurul kaydı değişmez: üye hâlâ yedek.
    kurul.sub.refresh_from_db()
    assert kurul.sub.is_substitute is True


def test_k4_ayni_tarihli_toplanti_yoksa_kurulun_asil_uyeleri_basilir(kurul: _Kurul) -> None:
    case = kurul.case()
    services.record_meeting(
        case, meeting_date=T2, attendee_member_ids=[kurul.t1.pk, kurul.t2.pk, kurul.sub.pk]
    )
    services.create_extension(case, requested_days=5, reason="Tanık dinlenecek.", decided_on=T1)
    ctx = doc_engine._deadline_extension_context(case, {})
    assert [m.pk for m in ctx["members"]] == [
        kurul.t1.pk,
        kurul.t2.pk,
        kurul.parent.pk,
        kurul.sub.pk,
    ]
    html = _html(_FORM12, ctx)
    assert kurul.parent.member_name in html
    assert kurul.sub.member_name not in html  # şablon yedekleri gizler — eski çıktı


@pytest.mark.parametrize("sikayetci", [False, True], ids=["izinli", "sikayetci"])
def test_k4_vekaletli_toplantida_baskanlik_eden_izgarada_bir_kez_basilir(
    kurul: _Kurul, sikayetci: bool
) -> None:
    case = kurul.case(petitioner_user_id=kurul.chair.pk if sikayetci else None)
    _acting_meeting(case, kurul, T1)
    services.create_extension(case, requested_days=5, reason="Tanık dinlenecek.", decided_on=T1)
    ctx = doc_engine._deadline_extension_context(case, {})
    assert ctx["chair_role"] == _ROLE
    assert ctx["committee"].chair.get_full_name() == kurul.t1.member_name
    # Başkanlık eden üye başkan hanesindedir; üye hanelerinde ikinci kez yer almaz.
    assert _grid_names(ctx) == [kurul.t2.member_name, kurul.sub.member_name]
    html = _html(_FORM12, ctx)
    assert html.count(f'<div class="name">{kurul.t1.member_name}</div>') == 1
    assert kurul.chair.full_name not in html


def test_k4_toplantidan_sonra_kuruldan_cikarilan_uye_izgarada_kalir(kurul: _Kurul) -> None:
    case = kurul.case()
    services.record_meeting(case, meeting_date=T1, attendee_member_ids=_present(kurul))
    services.create_extension(case, requested_days=5, reason="Tanık dinlenecek.", decided_on=T1)
    services.remove_committee_member(kurul.parent)
    ctx = doc_engine._deadline_extension_context(case, {})
    assert kurul.parent.member_name in _grid_names(ctx)


# ---------------------------------------------------------------------------
# K5 — katılmayan başkanın adı kayda yazılır
# ---------------------------------------------------------------------------
def test_k5_dosya_toplantisinda_katilmayan_baskanin_adi_kayda_yazilir(kurul: _Kurul) -> None:
    case = kurul.case()
    acting = _acting_meeting(case, kurul, T1)
    assert acting.absent_chair_name == kurul.chair.full_name
    plain = services.record_meeting(case, meeting_date=T2, attendee_member_ids=_present(kurul))
    assert plain.absent_chair_name == ""
    # Başkan sonradan değişse de kayıt aynı kalır.
    services.set_committee_chair(kurul.committee, PersonnelFactory(last_name="YENİBAŞKAN").pk)
    acting.refresh_from_db()
    assert acting.absent_chair_name == kurul.chair.full_name
    client = APIClient()
    rows = {row["id"]: row for row in client.get(_url(case, "meeting/")).json()}
    assert rows[acting.pk]["absent_chair_name"] == kurul.chair.full_name
    assert rows[plain.pk]["absent_chair_name"] == ""


def _acting_rows(kurul: _Kurul) -> list[dict[str, Any]]:
    return [kurul.row(kurul.t1, chair=True), kurul.row(kurul.t2), kurul.row(kurul.sub)]


def test_k5_karar_defteri_cumlesi_kayittaki_adi_basar_baskan_degisse_de(kurul: _Kurul) -> None:
    meeting = kurul.odk(_acting_rows(kurul), chair_absent=True)
    old_name = kurul.chair.full_name
    assert meeting.absent_chair_name == old_name
    new_chair = PersonnelFactory(first_name="SONRADAN", last_name="GELEN")
    services.set_committee_chair(kurul.committee, new_chair.pk)
    meeting = CouncilMeeting.objects.get(pk=meeting.pk)
    note = doc_engine._council_minutes_context(meeting)["chair_absence_note"]
    assert f"Kurul başkanı {old_name} toplantıya katılmamış" in note
    assert new_chair.full_name not in note

    # Alan boşsa (K5 öncesi kayıt) bugünkü davranış: kurulun bugünkü başkanı okunur.
    CouncilMeeting.objects.filter(pk=meeting.pk).update(absent_chair_name="")
    legacy = CouncilMeeting.objects.get(pk=meeting.pk)
    legacy_note = doc_engine._council_minutes_context(legacy)["chair_absence_note"]
    assert f"Kurul başkanı {new_chair.full_name} toplantıya katılmamış" in legacy_note


def test_k5_tutanak_duzenlenirken_ad_kendiliginden_degismez(kurul: _Kurul) -> None:
    meeting = kurul.odk(_acting_rows(kurul), chair_absent=True)
    old_name = kurul.chair.full_name
    services.set_committee_chair(kurul.committee, PersonnelFactory(last_name="YENİBAŞKAN").pk)
    meeting = CouncilMeeting.objects.get(pk=meeting.pk)
    services.update_council_meeting(meeting, notes="Düzeltme.", chair_absent=True)
    meeting.refresh_from_db()
    assert meeting.absent_chair_name == old_name


def test_k5_vekalet_duzenlemede_eklenirse_ad_yazilir_kaldirilirsa_silinir(kurul: _Kurul) -> None:
    present = [kurul.chair_row(), kurul.row(kurul.t1), kurul.row(kurul.t2)]
    meeting = kurul.odk(present)
    assert meeting.absent_chair_name == ""
    services.update_council_meeting(meeting, attendees=_acting_rows(kurul), chair_absent=True)
    meeting.refresh_from_db()
    assert meeting.absent_chair_name == kurul.chair.full_name
    services.update_council_meeting(meeting, attendees=present, chair_absent=False)
    meeting.refresh_from_db()
    assert meeting.absent_chair_name == ""
    body = APIClient().get(f"/api/v1/council/meetings/{meeting.pk}/").json()
    assert body["absent_chair_name"] == ""


# ---------------------------------------------------------------------------
# K6 — Form-10 yedek üye ibaresi
# ---------------------------------------------------------------------------
def test_k6_form10_cagrilan_yedek_uyenin_gorevi_yedek_uye_ibaresi_tasir(kurul: _Kurul) -> None:
    case = kurul.case(petitioner_user_id=kurul.chair.pk)
    _acting_meeting(case, kurul, T1)
    html = _html(_FORM10, doc_engine._meeting_call_context(case, {}))
    assert f"<td>{kurul.sub.member_name}</td> <td>Öğretmen (Yedek Üye)</td>" in html
    assert html.count("(Yedek Üye)") == 1
    # Kendi görev/unvanı olan yedek üyede ibare unvana eklenir.
    type(kurul.sub).objects.filter(pk=kurul.sub.pk).update(title="Rehber Öğretmen")
    titled = _html(_FORM10, doc_engine._meeting_call_context(case, {}))
    assert "<td>Rehber Öğretmen (Yedek Üye)</td>" in titled
    # Asıl üyelerin satırı değişmez.
    assert f"<td>{kurul.t2.member_name}</td> <td>Öğretmen</td>" in titled


def test_k6_vekaletsiz_dosyada_form10_ciktisinda_ibare_yok(kurul: _Kurul) -> None:
    case = kurul.case()
    services.record_meeting(
        case, meeting_date=T1, attendee_member_ids=[kurul.t1.pk, kurul.t2.pk, kurul.sub.pk]
    )
    html = _html(_FORM10, doc_engine._meeting_call_context(case, {}))
    assert "(Yedek Üye)" not in html
    assert kurul.sub.member_name not in html


# ---------------------------------------------------------------------------
# K7 — ileri tarihli toplantıya karar bağlanamaz
# ---------------------------------------------------------------------------
def test_k7_ileri_tarihli_toplanti_kaydedilir_ama_karar_baglanamaz(kurul: _Kurul) -> None:
    case = kurul.case()
    future = timezone.localdate() + timedelta(days=3)
    meeting = services.record_meeting(
        case, meeting_date=future, attendee_member_ids=_present(kurul)
    )
    with pytest.raises(ValueError, match="henüz gelmedi") as err:
        _decide(case, meeting)
    assert f"{future:%d.%m.%Y}" in str(err.value)
    assert "silip" in str(err.value)  # eyleme dönük: kayıt düzeltilebilir (§7.6)
    assert not DisciplineDecision.all_objects.filter(case=case).exists()


def test_k7_bugunku_toplantiya_karar_baglanir(kurul: _Kurul) -> None:
    case = kurul.case()
    today = timezone.localdate()
    meeting = services.record_meeting(case, meeting_date=today, attendee_member_ids=_present(kurul))
    assert _decide(case, meeting).decision_date == today


def test_k7_karar_ileri_tarihli_toplantiya_tasinamaz(kurul: _Kurul) -> None:
    case = kurul.case()
    decision = _decide(
        case, services.record_meeting(case, meeting_date=T1, attendee_member_ids=_present(kurul))
    )
    future = timezone.localdate() + timedelta(days=3)
    later = services.record_meeting(case, meeting_date=future, attendee_member_ids=_present(kurul))
    with pytest.raises(ValueError, match="henüz gelmedi"):
        services.update_decision(decision, penalty_type=PenaltyType.REPRIMAND, meeting=later)
    decision.refresh_from_db()
    assert decision.decision_date == T1

    # Aynı tarihli bağlama (rebind) da ileri tarihli toplantıya yapılamaz.
    other = kurul.case()
    old = legacy_decision(
        other,
        student_id=other.students.get().pk,
        penalty_type=PenaltyType.REPRIMAND,
        decision_date=future,
    )
    same_day = services.record_meeting(
        other, meeting_date=future, attendee_member_ids=_present(kurul)
    )
    with pytest.raises(ValueError, match="henüz gelmedi"):
        services.rebind_decision_meeting(old, same_day)


def test_k7_api_toplantida_ileri_tarih_bilgisi_ve_ileti(kurul: _Kurul) -> None:
    case = kurul.case()
    past = services.record_meeting(case, meeting_date=T1, attendee_member_ids=_present(kurul))
    future = services.record_meeting(
        case,
        meeting_date=timezone.localdate() + timedelta(days=1),
        attendee_member_ids=_present(kurul),
    )
    client = APIClient()
    rows = {row["id"]: row for row in client.get(_url(case, "meeting/")).json()}
    assert rows[past.pk]["is_future"] is False
    assert rows[future.pk]["is_future"] is True
    resp = client.post(
        _url(case, "decisions/"),
        {
            "student": case.students.get().pk,
            "penalty_type": PenaltyType.REPRIMAND,
            "meeting": future.pk,
        },
        format="json",
    )
    assert resp.status_code == 400
    assert "henüz gelmedi" in resp.json()["message"]


def test_k7_ileri_tarihli_toplantiya_bagli_silinmis_karar_geri_yuklenmez(kurul: _Kurul) -> None:
    """Geri yükleme fiilen yeniden bağlamadır: yapılmamış toplantının kararı canlanmaz.

    Yol yalnız K7 ÖNCESİ girilip silinmiş kayıtta açıktır (burada ORM ile taklit edilir).
    Tek yönlü kapan değil (§7.6): toplantı günü gelince karar geri yüklenir.
    """
    case = kurul.case()
    meeting = services.record_meeting(case, meeting_date=T1, attendee_member_ids=_present(kurul))
    decision = _decide(case, meeting)
    services.delete_decision(decision)
    future = timezone.localdate() + timedelta(days=3)
    DisciplineMeeting.objects.filter(pk=meeting.pk).update(meeting_date=future)
    DisciplineDecision.all_objects.filter(pk=decision.pk).update(decision_date=future)

    decision.refresh_from_db()
    with pytest.raises(ValueError, match="henüz gelmedi") as err:
        services.restore_decision(decision)
    assert f"{future:%d.%m.%Y}" in str(err.value)
    assert "geri yüklenemez" in str(err.value)
    client = APIClient()
    (row,) = client.get(_url(case, "decisions/deleted/")).json()
    assert "henüz gelmedi" in row["restore_blocked_reason"]
    assert client.post(_url(case, f"decisions/{decision.pk}/restore/")).status_code == 400

    # Toplantı günü geldi: geri yüklenir.
    today = timezone.localdate()
    DisciplineMeeting.objects.filter(pk=meeting.pk).update(meeting_date=today)
    DisciplineDecision.all_objects.filter(pk=decision.pk).update(decision_date=today)
    decision.refresh_from_db()
    (row,) = client.get(_url(case, "decisions/deleted/")).json()
    assert row["restore_blocked_reason"] == ""
    services.restore_decision(decision)
    decision.refresh_from_db()
    assert decision.deleted_at is None


# ---------------------------------------------------------------------------
# K8 — yeter sayıda toplantı anındaki üye tam sayısı
# ---------------------------------------------------------------------------
def test_k8_kurul_sonradan_buyuse_de_eski_toplanti_yeterli_kalir(kurul: _Kurul) -> None:
    case = kurul.case()
    meeting = services.record_meeting(case, meeting_date=T1, attendee_member_ids=_present(kurul))
    assert meeting.quorum_full == 4
    for _ in range(4):
        services.add_committee_member(
            kurul.committee, member_type="TEACHER", person_id=PersonnelFactory().pk
        )
    quorum = case_meeting_quorum(DisciplineMeeting.objects.get(pk=meeting.pk))
    assert quorum == {"full": 4, "required": 3, "present": 4, "ok": True}
    assert _decide(case, meeting).meeting_id == meeting.pk  # karar bağlanabilir


def test_k8_alan_bossa_eski_davranis_guncel_uye_sayisi(kurul: _Kurul) -> None:
    case = kurul.case()
    meeting = services.record_meeting(case, meeting_date=T1, attendee_member_ids=_present(kurul))
    DisciplineMeeting.objects.filter(pk=meeting.pk).update(quorum_full=None)
    for _ in range(4):
        services.add_committee_member(
            kurul.committee, member_type="TEACHER", person_id=PersonnelFactory().pk
        )
    quorum = case_meeting_quorum(DisciplineMeeting.objects.get(pk=meeting.pk))
    assert quorum["full"] == 8
    assert quorum["ok"] is False


def test_k8_vekaletli_toplantida_tam_sayi_degismez(kurul: _Kurul) -> None:
    meeting = _acting_meeting(kurul.case(), kurul, T1)
    assert meeting.quorum_full == 4
    assert case_meeting_quorum(meeting) == {"full": 4, "required": 3, "present": 3, "ok": True}


# ---------------------------------------------------------------------------
# K9 — karar defteri tutanağı ↔ kararların bağlı olduğu dosya toplantısı
# ---------------------------------------------------------------------------
def _minutes(
    kurul: _Kurul, case: DisciplineCase, on: date, attendees: list[dict[str, Any]], **kw: Any
) -> CouncilMeeting:
    meeting: CouncilMeeting = services.create_council_meeting(
        school_year_id=kurul.year.pk,
        council_type="DISCIPLINE",
        meeting_date=on,
        attendees=attendees,
        minutes_type="CASE_REVIEW",
        discipline_case_id=case.pk,
        **kw,
    )
    return meeting


def _full_rows(kurul: _Kurul) -> list[dict[str, Any]]:
    return [
        kurul.chair_row(),
        kurul.row(kurul.t1),
        kurul.row(kurul.t2),
        {"person_name": kurul.parent.member_name, "attendee_role": "VOTING_MEMBER"},
    ]


def test_k9_tutanak_bagli_toplantiyla_uyusuyorsa_uyari_yok(kurul: _Kurul) -> None:
    case = kurul.case()
    _decide(
        case, services.record_meeting(case, meeting_date=T1, attendee_member_ids=_present(kurul))
    )
    minutes = _minutes(kurul, case, T1, _full_rows(kurul))
    assert council_service.council_chair_warnings(minutes) == []


def test_k9_tarih_uyusmuyorsa_uyarilir_kayit_engellenmez(kurul: _Kurul) -> None:
    case = kurul.case()
    _decide(
        case, services.record_meeting(case, meeting_date=T1, attendee_member_ids=_present(kurul))
    )
    minutes = _minutes(kurul, case, T2, _full_rows(kurul))  # kayıt ENGELLENMEZ
    warnings = council_service.council_chair_warnings(minutes)
    assert len(warnings) == 1
    assert "27.05.2026" in warnings[0] and "21.05.2026" in warnings[0]
    assert "kararların bağlı olduğu" in warnings[0]
    body = APIClient().get(f"/api/v1/council/meetings/{minutes.pk}/").json()
    assert body["chair_warnings"] == warnings


def test_k9_oy_hakki_olan_katilimcilar_uyusmuyorsa_adlariyla_uyarilir(kurul: _Kurul) -> None:
    case = kurul.case()
    _decide(
        case, services.record_meeting(case, meeting_date=T1, attendee_member_ids=_present(kurul))
    )
    rows = [kurul.chair_row(), kurul.row(kurul.t1), kurul.row(kurul.t2), kurul.row(kurul.sub)]
    # Oy hakkı olmayan davetli (md. 185/6) karşılaştırmaya girmez.
    rows.append({"person_name": "Davetli Kişi", "attendee_role": "NON_VOTING_INVITEE"})
    minutes = _minutes(kurul, case, T1, rows)
    warnings = council_service.council_chair_warnings(minutes)
    assert len(warnings) == 1
    assert kurul.sub.member_name in warnings[0]  # tutanakta var, toplantı kaydında yok
    assert kurul.parent.member_name in warnings[0]  # toplantı kaydında var, tutanakta yok
    assert kurul.t1.member_name not in warnings[0]
    assert "Davetli Kişi" not in warnings[0]


def test_k9_vekaletli_bagli_toplantiyla_uyusan_tutanakta_uyari_yok(kurul: _Kurul) -> None:
    case = kurul.case()
    _decide(case, _acting_meeting(case, kurul, T1))
    minutes = _minutes(kurul, case, T1, _acting_rows(kurul), chair_absent=True)
    assert council_service.council_chair_warnings(minutes) == []


def test_k9_karari_bagsiz_eski_dosyada_uyari_yok(kurul: _Kurul) -> None:
    case = kurul.case()
    legacy_decision(
        case,
        student_id=case.students.get().pk,
        penalty_type=PenaltyType.REPRIMAND,
        decision_date=T1,
    )
    services.record_meeting(case, meeting_date=T1, attendee_member_ids=_present(kurul))
    rows = [kurul.chair_row(), kurul.row(kurul.t1), kurul.row(kurul.sub)]
    minutes = _minutes(kurul, case, T2, rows)
    assert council_service.council_chair_warnings(minutes) == []


def test_k9_md197_ikinci_gorusmeden_sonra_ilk_gorusmenin_tutanagi_uyari_almaz(
    kurul: _Kurul,
) -> None:
    """Karar ikinci toplantıya taşınınca (K10) İLK görüşmenin tutanağı doğru kayıt olarak kalır."""
    case = kurul.case()
    first = services.record_meeting(case, meeting_date=T1, attendee_member_ids=_present(kurul))
    decision = _decide(case, first)
    first_minutes = _minutes(kurul, case, T1, _full_rows(kurul))
    assert council_service.council_chair_warnings(first_minutes) == []

    services.record_principal_review(
        decision, action="RETURN", reason="Ceza ağır bulundu.", decided_on=date(2026, 5, 25)
    )
    services.set_decision_approval(decision, approval_status="PENDING")
    decision.refresh_from_db()
    second = services.record_meeting(case, meeting_date=T2, attendee_member_ids=_present(kurul))
    services.update_decision(decision, penalty_type=PenaltyType.REPRIMAND, meeting=second)

    assert council_service.council_chair_warnings(first_minutes) == []
    second_minutes = _minutes(kurul, case, T2, _full_rows(kurul))
    assert council_service.council_chair_warnings(second_minutes) == []
    # İlk / ikinci görüşme dışındaki tarih hâlâ uyarılır; ileti yalnız BAĞLI toplantıyı anar.
    (warning,) = council_service.council_chair_warnings(
        _minutes(kurul, case, T3, _full_rows(kurul))
    )
    assert "27.05.2026" in warning and "21.05.2026" not in warning

    # İlk görüşme tutanağının katılımcıları İLK toplantı kaydıyla karşılaştırılır.
    rows = [kurul.chair_row(), kurul.row(kurul.t1), kurul.row(kurul.t2), kurul.row(kurul.sub)]
    services.update_council_meeting(first_minutes, attendees=rows)
    first_minutes.refresh_from_db()
    (mismatch,) = council_service.council_chair_warnings(first_minutes)
    assert "ilk görüşüldüğü" in mismatch and "21.05.2026" in mismatch
    assert kurul.sub.member_name in mismatch

    # İlk toplantı kaydı sonradan silinse de ilk karar tarihi (K10) tarih uyarısını önler.
    services.delete_meeting(first)
    assert council_service.council_chair_warnings(first_minutes) == []


# ---------------------------------------------------------------------------
# K10 — md. 197: ilk görüşme tarihi saklanır
# ---------------------------------------------------------------------------
def _returned(kurul: _Kurul) -> tuple[DisciplineCase, DisciplineDecision, DisciplineMeeting]:
    """T1'de karar; müdür kurula iade etti; karar yeniden görüşme için beklemeye alındı."""
    case = kurul.case()
    first = services.record_meeting(case, meeting_date=T1, attendee_member_ids=_present(kurul))
    decision = _decide(case, first)
    services.record_principal_review(
        decision, action="RETURN", reason="Ceza ağır bulundu.", decided_on=date(2026, 5, 25)
    )
    services.set_decision_approval(decision, approval_status="PENDING")
    decision.refresh_from_db()
    return case, decision, first


def test_k10_iade_edilen_karar_ilk_tasimada_ilk_gorusmeyi_saklar_sonra_ezmez(
    kurul: _Kurul,
) -> None:
    case, decision, first = _returned(kurul)
    assert decision.first_decision_date is None
    second = services.record_meeting(case, meeting_date=T2, attendee_member_ids=_present(kurul))
    services.update_decision(decision, penalty_type=PenaltyType.REPRIMAND, meeting=second)
    decision.refresh_from_db()
    assert decision.decision_date == T2  # yürürlükteki karar tarihi
    assert decision.first_decision_date == T1
    assert decision.first_meeting_id == first.pk

    third = services.record_meeting(case, meeting_date=T3, attendee_member_ids=_present(kurul))
    services.update_decision(decision, penalty_type=PenaltyType.REPRIMAND, meeting=third)
    decision.refresh_from_db()
    assert decision.decision_date == T3
    assert decision.first_decision_date == T1  # EZİLMEZ
    assert decision.first_meeting_id == first.pk
    # Sonraki düzenlemeler de boşaltmaz.
    services.update_decision(decision, penalty_type=PenaltyType.REPRIMAND, notes="Not.")
    decision.refresh_from_db()
    assert decision.first_decision_date == T1

    (row,) = APIClient().get(_url(case, "decisions/")).json()["decisions"]
    assert row["first_decision_date"] == "2026-05-21"
    assert row["first_meeting"] == first.pk
    assert row["decision_date"] == "2026-06-03"


def test_k10_iade_edilmemis_karar_tasinirken_ilk_gorusme_yazilmaz(kurul: _Kurul) -> None:
    case = kurul.case()
    first = services.record_meeting(case, meeting_date=T1, attendee_member_ids=_present(kurul))
    decision = _decide(case, first)
    second = services.record_meeting(case, meeting_date=T2, attendee_member_ids=_present(kurul))
    services.update_decision(decision, penalty_type=PenaltyType.REPRIMAND, meeting=second)
    decision.refresh_from_db()
    assert decision.decision_date == T2
    assert decision.first_decision_date is None
    assert decision.first_meeting_id is None


def test_k10_tarih_degismeyen_baglamada_ilk_gorusme_yazilmaz(kurul: _Kurul) -> None:
    """İade edilmiş karar AYNI tarihli toplantıya bağlanırsa / taşınırsa ikinci görüşme yoktur.

    Kayıt tamamlama (eski kararın o günkü toplantıya bağlanması) ya da yanlış kaydın aynı
    tarihli doğrusuna taşınması "ilk görüşme" izi üretmez; iz gerçek ikinci görüşmede yazılır
    ve ilk toplantı o an bağlı olan (düzeltilmiş) kayıttır.
    """
    case = kurul.case()
    old = legacy_decision(
        case,
        student_id=case.students.get().pk,
        penalty_type=PenaltyType.REPRIMAND,
        decision_date=T1,
    )
    services.record_principal_review(
        old, action="RETURN", reason="Ceza ağır bulundu.", decided_on=date(2026, 5, 25)
    )
    services.set_decision_approval(old, approval_status="PENDING")
    old.refresh_from_db()
    wrong = services.record_meeting(case, meeting_date=T1, attendee_member_ids=_present(kurul))
    services.update_decision(old, penalty_type=PenaltyType.REPRIMAND, meeting=wrong)
    old.refresh_from_db()
    assert old.meeting_id == wrong.pk
    assert old.first_decision_date is None and old.first_meeting_id is None

    # Yanlış kaydedilmiş toplantıdan aynı tarihli doğru kayda taşıma: yine iz yok.
    right = services.record_meeting(
        case, meeting_date=T1, attendee_member_ids=[kurul.t1.pk, kurul.t2.pk]
    )
    services.update_decision(old, penalty_type=PenaltyType.REPRIMAND, meeting=right)
    old.refresh_from_db()
    assert old.meeting_id == right.pk
    assert old.first_decision_date is None and old.first_meeting_id is None

    # Gerçek ikinci görüşme: ilk tarih ve o an bağlı (düzeltilmiş) toplantı yazılır.
    second = services.record_meeting(case, meeting_date=T2, attendee_member_ids=_present(kurul))
    services.update_decision(old, penalty_type=PenaltyType.REPRIMAND, meeting=second)
    old.refresh_from_db()
    assert old.decision_date == T2
    assert old.first_decision_date == T1
    assert old.first_meeting_id == right.pk


def test_k10_kurula_iade_yazisi_ilk_kararin_tarihini_basar(kurul: _Kurul) -> None:
    case, decision, _first = _returned(kurul)
    student = case.students.get()

    def _letter(document_type: str) -> dict[str, Any]:
        ctx = doc_engine._build_context(case, document_type, student, None, {})
        doc_engine._apply_md197_dates(ctx, document_type)
        return ctx

    before = _letter(DocumentType.RETURN_LETTER)
    assert before["decision"].decision_date == T1  # taşınmadan önce: karar tarihi

    second = services.record_meeting(case, meeting_date=T2, attendee_member_ids=_present(kurul))
    services.update_decision(decision, penalty_type=PenaltyType.REPRIMAND, meeting=second)
    ctx = _letter(DocumentType.RETURN_LETTER)
    assert ctx["decision"].decision_date == T1  # kurulun İLK kararının tarihi
    assert ctx["decision"].returned_at == date(2026, 5, 25)
    html = _html(f"{_BASE}return_letter.html", {**ctx, "generated_at": timezone.now()})
    assert "21.05.2026 tarihli" in html
    assert "27.05.2026" not in html
    # Kayıt DEĞİŞMEZ; öteki belgeler yürürlükteki karar tarihini kullanır.
    decision.refresh_from_db()
    assert decision.decision_date == T2
    ek1 = doc_engine._build_context(case, DocumentType.COMMITTEE_DECISION, student, None, {})
    assert ek1["decision"].decision_date == T2
    referral = _letter(DocumentType.DISTRICT_REFERRAL_LETTER)
    assert referral["decision"].decision_date == T2


# ---------------------------------------------------------------------------
# K11 — sevk öncesinde kalan eski (bağsız) silinmiş karar geri yüklenmez
# ---------------------------------------------------------------------------
def test_k11_sevk_oncesinde_kalan_eski_silinmis_karar_geri_yuklenmez(kurul: _Kurul) -> None:
    case = kurul.case()
    sid = case.students.get().pk
    old = legacy_decision(
        case, student_id=sid, penalty_type=PenaltyType.REPRIMAND, decision_date=T1
    )
    services.delete_decision(old)
    _refer_again(case, date(2026, 6, 1))

    old.refresh_from_db()
    with pytest.raises(ValueError, match="sevk tarihinden") as err:
        services.restore_decision(old)
    assert "21.05.2026" in str(err.value) and "01.06.2026" in str(err.value)
    assert "geri yüklenemez" in str(err.value)
    assert "yeniden girin" in str(err.value)  # eyleme dönük
    old.refresh_from_db()
    assert old.deleted_at is not None

    client = APIClient()
    (row,) = client.get(_url(case, "decisions/deleted/")).json()
    assert "sevk tarihinden" in row["restore_blocked_reason"]
    assert client.post(_url(case, f"decisions/{old.pk}/restore/")).status_code == 400
    # Çıkış var (§7.6): sevkten sonraki toplantıya yeni karar girilir.
    later = services.record_meeting(case, meeting_date=T3, attendee_member_ids=_present(kurul))
    assert _decide(case, later).decision_date == T3


def test_k11_ayni_sevkte_silinen_eski_karar_geri_yuklenir(kurul: _Kurul) -> None:
    case = kurul.case()
    old = legacy_decision(
        case,
        student_id=case.students.get().pk,
        penalty_type=PenaltyType.REPRIMAND,
        decision_date=T1,
    )
    services.delete_decision(old)
    (row,) = APIClient().get(_url(case, "decisions/deleted/")).json()
    assert row["restore_blocked_reason"] == ""
    old.refresh_from_db()
    services.restore_decision(old)
    old.refresh_from_db()
    assert old.deleted_at is None and old.meeting_id is None


def test_k11_canli_eski_karar_yeniden_sevkten_etkilenmez(kurul: _Kurul) -> None:
    """Canlı (silinmemiş) eski karar kendiliğinden değiştirilmez; listede neden alanı boştur."""
    case = kurul.case()
    old = legacy_decision(
        case,
        student_id=case.students.get().pk,
        penalty_type=PenaltyType.REPRIMAND,
        decision_date=T1,
    )
    (row,) = APIClient().get(_url(case, "decisions/")).json()["decisions"]
    assert row["id"] == old.pk
    assert row["restore_blocked_reason"] == ""
    assert DisciplineDecision.objects.filter(pk=old.pk, decision_date=T1).exists()


# ---------------------------------------------------------------------------
# Göç 0018 — yalnız şema: eski kayıtlar değişmez, geri alınabilir
# ---------------------------------------------------------------------------
_BEFORE = [("disiplin", "0017_meeting_chair_absence")]
_AFTER = [("disiplin", "0018_acik_kalemler")]


@pytest.fixture
def old_schema() -> Iterator[Any]:
    """Veritabanını 0018 öncesi şemaya indirir; test bitince en güncel şemaya çıkarır."""
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
def test_goc_0018_eski_kayitlari_degistirmez_ve_geri_alinir(old_schema: Any) -> None:
    year = old_schema.get_model("okul", "SchoolYear").objects.create(
        name="2025-2026", start_date=date(2025, 9, 8), end_date=date(2026, 6, 26), is_active=True
    )
    student = old_schema.get_model("okul", "Student").objects.create(
        first_name="DENEME", last_name="ÖĞRENCİ", student_number="901", class_level=10
    )
    case = old_schema.get_model("disiplin", "DisciplineCase").objects.create(
        case_no="2025-2026-0001",
        petition_date=date(2026, 3, 2),
        petitioner_name="İdare",
        petitioner_role="IDARE",
        summary="Eski sürümden kalan dosya.",
    )
    old_meeting = old_schema.get_model("disiplin", "DisciplineMeeting").objects.create(
        case=case, meeting_date=date(2026, 3, 9), chair_absent=True, notes="Eski toplantı."
    )
    old_council = old_schema.get_model("disiplin", "CouncilMeeting").objects.create(
        school_year=year,
        council_type="DISCIPLINE",
        meeting_no=1,
        meeting_date=date(2026, 3, 9),
        chair_absent=True,
    )
    old_decision = old_schema.get_model("disiplin", "DisciplineDecision").objects.create(
        case=case,
        student=student,
        meeting=old_meeting,
        penalty_type="REPRIMAND",
        decision_date=date(2026, 3, 9),
        approval_authority="PRINCIPAL",
        first_returned_at=date(2026, 3, 11),
    )

    new_apps = _migrate(_AFTER)
    meeting = new_apps.get_model("disiplin", "DisciplineMeeting").objects.get(pk=old_meeting.pk)
    assert meeting.absent_chair_name == ""  # ad uydurulmaz
    assert meeting.quorum_full is None  # sayı uydurulmaz
    assert meeting.chair_absent is True and meeting.notes == "Eski toplantı."
    council = new_apps.get_model("disiplin", "CouncilMeeting").objects.get(pk=old_council.pk)
    assert council.absent_chair_name == ""
    decision = new_apps.get_model("disiplin", "DisciplineDecision").objects.get(pk=old_decision.pk)
    assert decision.first_decision_date is None and decision.first_meeting_id is None
    assert decision.decision_date == date(2026, 3, 9)
    assert decision.meeting_id == old_meeting.pk

    # Geri alınabilir: sütunlar düşer, kayıtlar kalır.
    back = _migrate(_BEFORE)
    assert (
        back.get_model("disiplin", "DisciplineMeeting")
        .objects.filter(pk=old_meeting.pk, notes="Eski toplantı.")
        .exists()
    )
    assert (
        back.get_model("disiplin", "DisciplineDecision").objects.filter(pk=old_decision.pk).exists()
    )


# ---------------------------------------------------------------------------
# Son denetim düzeltmeleri (16.11.2026)
# ---------------------------------------------------------------------------
def test_k9_kurul_baskani_degisince_temiz_tutanak_yanlis_uyari_almaz(kurul: _Kurul) -> None:
    """Vekâletsiz toplantıda o günkü başkan kayıtta tutulmaz: başkan satırı karşılaştırılmaz."""
    case = kurul.case()
    _decide(
        case, services.record_meeting(case, meeting_date=T1, attendee_member_ids=_present(kurul))
    )
    minutes = _minutes(kurul, case, T1, _full_rows(kurul))
    assert council_service.council_chair_warnings(minutes) == []
    kurul.committee.chair = PersonnelFactory(first_name="YENİ", last_name="BAŞKANOĞLU")
    kurul.committee.save()
    minutes.refresh_from_db()
    assert council_service.council_chair_warnings(minutes) == []


def test_k9_tutanak_vekaletli_toplanti_kaydi_vekaletsizse_uyarilir(kurul: _Kurul) -> None:
    case = kurul.case()
    _decide(
        case,
        services.record_meeting(
            case, meeting_date=T1, attendee_member_ids=[kurul.t1.pk, kurul.t2.pk, kurul.sub.pk]
        ),
    )
    minutes = _minutes(kurul, case, T1, _acting_rows(kurul), chair_absent=True)
    warnings = [w for w in council_service.council_chair_warnings(minutes) if "uyuşmuyor" in w]
    assert len(warnings) == 1
    assert "tutanakta başkan katılmadı olarak, toplantı kaydında katıldı olarak" in warnings[0]


def test_uzatma_gunu_vekaletli_son_toplanti_olagan_form12_o_gunun_baskanlik_edenini_basar(
    kurul: _Kurul,
) -> None:
    """İzinli başkan: T1 vekâletli, T2 olağan toplantı; T1'deki uzatma T1'in heyetiyle basılır."""
    case = kurul.case()
    _acting_meeting(case, kurul, T1)
    services.record_meeting(case, meeting_date=T2, attendee_member_ids=_present(kurul))
    services.create_extension(case, requested_days=5, reason="Tanık dinlenecek.", decided_on=T1)
    ctx = doc_engine._deadline_extension_context(case, {})
    assert ctx["chair_role"] == _ROLE
    assert ctx["committee"].chair.get_full_name() == kurul.t1.member_name
    assert _grid_names(ctx) == [kurul.t2.member_name, kurul.sub.member_name]
    html = _html(_FORM12, ctx)
    assert kurul.chair.full_name not in html
    assert html.count(f'<div class="name">{kurul.t1.member_name}</div>') == 1
    assert kurul.chair.full_name not in _html(_FORM13, ctx)
