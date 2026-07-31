"""F2 inceleme bulgularının regresyon pinleri (workflow wf_8007bf44-dca, 29 bulgu).

Her test bir doğrulanmış bulguyu kapatır; numaralar inceleme listesine atıftır.
"""

from __future__ import annotations

from datetime import date

import pytest
from rest_framework.test import APIClient

from apps.disiplin import selectors, services
from apps.disiplin.deadlines import Severity, collect_deadline_items
from apps.disiplin.models import (
    CaseStage,
    CouncilAttendeeRole,
    CouncilType,
    DecisionApprovalStatus,
    DisciplineCase,
    DisciplineDecision,
    PenaltyType,
    PrincipalDecision,
)
from apps.disiplin.tests.factories import SchoolYearFactory, StudentFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def client() -> APIClient:
    return APIClient()


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


def _suspension_decision(case: DisciplineCase, sid: int) -> DisciplineDecision:
    return services.record_decision(
        case,
        student_id=sid,
        penalty_type=PenaltyType.SHORT_TERM_SUSPENSION,
        decision_date=date(2026, 5, 22),
        suspension_days=3,
    )


# ---------------------------------------------------------------------------
# Bulgu 1+3: narrative → enforcement_start_date post-hoc + student_birth_date sicile
# ---------------------------------------------------------------------------
def test_uygulama_baslangici_onay_sonrasi_narrative_ile_girilir(client: APIClient) -> None:
    case, sid = _committee_case()
    d = _suspension_decision(case, sid)
    services.set_decision_approval(
        d, approval_status=DecisionApprovalStatus.APPROVED, approved_on=date(2026, 5, 23)
    )
    services.notify_decision(d, notified_on=date(2026, 5, 23))
    resp = client.post(
        f"/api/v1/discipline/cases/{case.pk}/decisions/{d.pk}/narrative/",
        {"enforcement_start_date": "2026-06-08"},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    d.refresh_from_db()
    assert d.enforcement_start_date == date(2026, 6, 8)
    # null → temizler (OYS _UNSET davranışı)
    client.post(
        f"/api/v1/discipline/cases/{case.pk}/decisions/{d.pk}/narrative/",
        {"enforcement_start_date": None},
        format="json",
    )
    d.refresh_from_db()
    assert d.enforcement_start_date is None


def test_student_birth_date_ogrenci_siciline_yazilir(client: APIClient) -> None:
    case, sid = _committee_case()
    d = _suspension_decision(case, sid)
    resp = client.post(
        f"/api/v1/discipline/cases/{case.pk}/decisions/{d.pk}/narrative/",
        {"student_birth_date": "2009-01-15", "committee_opinion": "Kanaat."},
        format="json",
    )
    assert resp.status_code == 200
    fresh = selectors.get_case(case.pk)
    assert fresh is not None
    student = fresh.case_students.get().student
    assert student.birth_date == date(2009, 1, 15)
    d.refresh_from_db()
    assert d.committee_opinion == "Kanaat."


# ---------------------------------------------------------------------------
# Bulgu 2+5+24: narrative doğrulaması + Django ValidationError sözleşmesi
# ---------------------------------------------------------------------------
def test_narrative_bozuk_tarih_500_degil_400(client: APIClient) -> None:
    case, sid = _committee_case()
    d = _suspension_decision(case, sid)
    resp = client.post(
        f"/api/v1/discipline/cases/{case.pk}/decisions/{d.pk}/narrative/",
        {"incident_date": "31.05.2026"},  # TR görüntü formatı — ISO değil
        format="json",
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "validation_error"


def test_narrative_null_metin_400(client: APIClient) -> None:
    case, sid = _committee_case()
    d = _suspension_decision(case, sid)
    resp = client.post(
        f"/api/v1/discipline/cases/{case.pk}/decisions/{d.pk}/narrative/",
        {"committee_opinion": None},
        format="json",
    )
    assert resp.status_code == 400


def test_narrative_max_length_sinirlanir(client: APIClient) -> None:
    case, sid = _committee_case()
    d = _suspension_decision(case, sid)
    resp = client.post(
        f"/api/v1/discipline/cases/{case.pk}/decisions/{d.pk}/narrative/",
        {"boarding_status": "X" * 5000},  # model sınırı 120
        format="json",
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Bulgu 6+23: decision PATCH kısmi güncelleme
# ---------------------------------------------------------------------------
def test_decision_patch_yalniz_not_uzaklastirmayi_silmez(client: APIClient) -> None:
    case, sid = _committee_case()
    d = _suspension_decision(case, sid)
    resp = client.patch(
        f"/api/v1/discipline/cases/{case.pk}/decisions/{d.pk}/",
        {"notes": "Gerekçe güncellendi."},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    d.refresh_from_db()
    assert d.suspension_days == 3  # kısmi PATCH silmedi
    assert d.notes == "Gerekçe güncellendi."


def test_decision_patch_gecersiz_tarih_400(client: APIClient) -> None:
    case, sid = _committee_case()
    d = _suspension_decision(case, sid)
    resp = client.patch(
        f"/api/v1/discipline/cases/{case.pk}/decisions/{d.pk}/",
        {"decision_date": "sacma"},
        format="json",
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Bulgu 9+10+15+27: case PATCH + pk çözümü + update_case
# ---------------------------------------------------------------------------
def test_case_patch_gecersiz_tarih_400_ve_rol_guncellenir(client: APIClient) -> None:
    case, _sid = _committee_case()
    resp = client.patch(
        f"/api/v1/discipline/cases/{case.pk}/", {"petition_date": "31.05.2026"}, format="json"
    )
    assert resp.status_code == 400
    resp = client.patch(
        f"/api/v1/discipline/cases/{case.pk}/", {"petitioner_role": "OGRETMEN"}, format="json"
    )
    assert resp.status_code == 200
    case.refresh_from_db()
    assert case.petitioner_role == "OGRETMEN"


def test_ust_simge_pk_404(client: APIClient) -> None:
    resp = client.get("/api/v1/discipline/cases/%C2%B2/")  # '²'
    assert resp.status_code == 404


def test_kapali_dosyada_kunye_guncellenemez() -> None:
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
        principal_decisions=[PrincipalDecision.WRITTEN_WARNING],
    )  # otomatik CLOSED
    case.refresh_from_db()
    with pytest.raises(ValueError, match="kapatılmış"):
        services.update_case(case, summary="değişsin")


# ---------------------------------------------------------------------------
# Bulgu 11: ek türü doğrulaması
# ---------------------------------------------------------------------------
def test_gecersiz_ek_turu_400(client: APIClient, tmp_path: object, settings: object) -> None:
    settings.MEDIA_ROOT = tmp_path  # type: ignore[attr-defined]
    case, _sid = _committee_case()
    from io import BytesIO

    upload = BytesIO(b"%PDF-1.4\n%%EOF\n")
    upload.name = "a.pdf"
    resp = client.post(
        f"/api/v1/discipline/cases/{case.pk}/attachments/",
        {"file": upload, "file_type": "UYDURUK"},
        format="multipart",
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Bulgu 7+8+29: deadlines düzeltmeleri
# ---------------------------------------------------------------------------
def test_kurul_bekleyen_kararsiz_dosya_kapatilabilir_listelenmez() -> None:
    _case, _sid = _committee_case()
    items = collect_deadline_items(date(2026, 5, 20))
    assert not any("kapatılabilir" in i.title for i in items)


def test_uzun_tedbirde_iki_esik_ayri_listelenir() -> None:
    case, sid = _committee_case()
    services.create_precaution(
        case, student_id=sid, start_date=date(2026, 5, 20), requested_days=10
    )
    # 27.05: işleme-başlama (25.05 GEÇTİ) + bitiş (02.06 YAKLAŞIYOR) İKİSİ de görünür.
    tedbir = [i for i in collect_deadline_items(date(2026, 5, 27)) if i.statute_ref == "md. 175"]
    assert len(tedbir) == 2
    assert {i.severity for i in tedbir} == {Severity.OVERDUE, Severity.UPCOMING}


def test_son_gun_yaklasiyor_sayilir() -> None:
    """due == today sınırı GEÇTİ değil YAKLAŞIYOR olmalı (son gün hâlâ yetişilebilir)."""
    case, _sid = _committee_case()
    # Kurul son günü 02.06.2026 — o gün panelde YAKLAŞIYOR.
    kurul = [i for i in collect_deadline_items(date(2026, 6, 2)) if i.statute_ref == "md. 192/3"]
    assert kurul[0].severity == Severity.UPCOMING


def test_onayli_uzatma_panele_yansir() -> None:
    case, _sid = _committee_case()
    ext = services.create_extension(
        case, requested_days=5, reason="gecikme", decided_on=date(2026, 5, 25)
    )
    services.approve_extension(ext, approved_on=date(2026, 5, 26))
    # Yeni son gün 09.06 — 28.05'te ufuk (5 iş günü ≈ 04.06) DIŞINDA → görünmez.
    assert [
        i for i in collect_deadline_items(date(2026, 5, 28)) if i.statute_ref == "md. 192/3"
    ] == []
    kurul = [i for i in collect_deadline_items(date(2026, 6, 4)) if i.statute_ref == "md. 192/3"]
    assert kurul[0].due_date == date(2026, 6, 9)


# ---------------------------------------------------------------------------
# Bulgu 22: normal (override'sız) rehberlik akışı
# ---------------------------------------------------------------------------
def test_normal_rehberlik_akisi_overridesiz() -> None:
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
        CaseStage.GUIDANCE_REFERRED,
        date(2026, 5, 19),
        assigned_guidance_name="REHBER HOCA",
    )
    services.add_event(
        case,
        CaseStage.GUIDANCE_RETURNED,
        date(2026, 5, 20),
        guidance_outcome="Görüşme yapıldı; öğrenci pişman.",
    )
    event = services.add_event(
        case,
        CaseStage.DECIDED,
        date(2026, 5, 21),
        principal_decisions=[PrincipalDecision.DISCIPLINE_COMMITTEE],
    )
    assert event.is_override is False  # normal akışta override YOK
    case.refresh_from_db()
    assert case.current_stage == CaseStage.DECIDED


# ---------------------------------------------------------------------------
# Bulgu 25: süre-dışı PENDING itiraz kapanışı bloke eder
# ---------------------------------------------------------------------------
def test_sure_disi_bekleyen_itiraz_kapanisi_bloke_eder() -> None:
    case, sid = _committee_case()
    d = services.record_decision(
        case, student_id=sid, penalty_type=PenaltyType.REPRIMAND, decision_date=date(2026, 5, 22)
    )
    services.notify_decision(d, notified_on=date(2026, 5, 22))
    gec = services.file_appeal(d, filed_on=date(2026, 6, 15), filed_by_role="PARENT")
    assert gec.within_deadline is False
    # Süre-dışı da olsa PENDING itiraz sonuçlanana dek dosya kapatılamaz.
    assert selectors.close_eligible(case, today=date(2026, 7, 1)) == (False, None)


# ---------------------------------------------------------------------------
# Bulgu 26: revert_stage başarı yolu + API ucu
# ---------------------------------------------------------------------------
def test_revert_stage_basari_ve_api(client: APIClient) -> None:
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
        principal_decisions=[PrincipalDecision.WRITTEN_WARNING],
    )  # CLOSED + closed_at dolu
    case.refresh_from_db()
    assert case.closed_at is not None
    resp = client.post(
        f"/api/v1/discipline/cases/{case.pk}/revert-stage/",
        {"target_stage": CaseStage.PETITION, "reason": "Yanlış dosyaya işlendi."},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    case.refresh_from_db()
    assert case.current_stage == CaseStage.PETITION
    assert case.closed_at is None  # temizlendi


# ---------------------------------------------------------------------------
# Bulgu 28: council meeting güncelleme/silme
# ---------------------------------------------------------------------------
def test_council_meeting_guncelle_ve_sil(client: APIClient) -> None:
    year = SchoolYearFactory()
    attendees = [
        {
            "person_name": "BAŞKAN",
            "attendee_role": CouncilAttendeeRole.VOTING_MEMBER,
            "is_chair": True,
        }
    ]
    meeting = services.create_council_meeting(
        school_year_id=year.pk,
        council_type=CouncilType.DISCIPLINE,
        meeting_date=date(2026, 5, 25),
        attendees=attendees,
    )
    yeni_katilimcilar = [
        {
            "person_name": "YENİ BAŞKAN",
            "attendee_role": CouncilAttendeeRole.VOTING_MEMBER,
            "is_chair": True,
        },
        {
            "person_name": "DAVETLİ",
            "attendee_role": CouncilAttendeeRole.NON_VOTING_INVITEE,
            "is_chair": False,
        },
    ]
    resp = client.patch(
        f"/api/v1/council/meetings/{meeting.pk}/",
        {"decision_text": "Düzeltilmiş karar.", "attendees": yeni_katilimcilar},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["decision_text"] == "Düzeltilmiş karar."
    # Model sıralaması attendee_role'a göredir (davetli alfabetik önce) — küme karşılaştır.
    assert {a["person_name"] for a in body["attendees"]} == {"YENİ BAŞKAN", "DAVETLİ"}
    assert client.delete(f"/api/v1/council/meetings/{meeting.pk}/").status_code == 204


# ---------------------------------------------------------------------------
# Bulgu 13+14+16: yüzey düzeltmeleri
# ---------------------------------------------------------------------------
def test_case_options_zarfi(client: APIClient) -> None:
    case, sid = _committee_case()
    services.record_decision(
        case, student_id=sid, penalty_type=PenaltyType.REPRIMAND, decision_date=date(2026, 5, 22)
    )
    body = client.get("/api/v1/council/meetings/case-options/").json()
    assert set(body) == {"cases"}
    assert body["cases"][0]["case_no"] == case.case_no
    assert isinstance(body["cases"][0]["students"], list)


def test_dosya_detayinda_close_eligible_alanlari(client: APIClient) -> None:
    case, _sid = _committee_case()
    body = client.get(f"/api/v1/discipline/cases/{case.pk}/").json()
    assert "close_eligible" in body
    assert "close_eligible_on" in body


def test_karar_tipi_delete_kapali(client: APIClient) -> None:
    resp = client.post(
        "/api/v1/discipline/decision-types/",
        {"code": "KINAMA", "name": "Kınama"},
        format="json",
    )
    dtype_id = resp.json()["id"]
    assert client.delete(f"/api/v1/discipline/decision-types/{dtype_id}/").status_code == 405
