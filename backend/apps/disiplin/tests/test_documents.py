"""Evrak motoru testleri (F3) — WeasyPrint PDF üretimi + kütük + kilitler.

Kabul (tasarım §11): Türkçe karakter duman testi ("ĞÜŞİÖÇ ığüşiöç") pypdf
metin çıkarmasıyla; Dal A/B kısıtı + Form-16/17 kesinleşme kilidi AYNEN.
Tarihler geçmişte sabittir (kesinleşme hesabı bugüne göre — Mayıs 2026 < bugün).
"""

from __future__ import annotations

from datetime import date
from io import BytesIO

import pytest
from pypdf import PdfReader
from rest_framework.test import APIClient

from apps.disiplin import documents as doc_engine
from apps.disiplin import selectors, services
from apps.disiplin.models import (
    CaseStage,
    DisciplineCase,
    DocumentType,
    GeneratedDocument,
    PenaltyType,
    PrincipalDecision,
)
from apps.disiplin.tests.factories import PersonnelFactory, SchoolYearFactory, StudentFactory
from apps.okul.services import setup as okul_setup

pytestmark = pytest.mark.django_db

TURKCE_DUMAN = "ĞÜŞİÖÇ ığüşiöç İstanbul"


def _pdf_text(pdf_bytes: bytes) -> str:
    reader = PdfReader(BytesIO(pdf_bytes))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


@pytest.fixture
def client() -> APIClient:
    return APIClient()


def _setup_school() -> None:
    okul_setup.update_school_config(
        fields={
            "school_name": "Deneme Anadolu Lisesi",
            "district": "Menteşe",
            "principal_name": "ALİ ÖRNEK",
        }
    )


def _committee_case(summary: str = "x") -> tuple[DisciplineCase, int]:
    SchoolYearFactory()
    _setup_school()
    s = StudentFactory(first_name="EMRE CAN", last_name="YILMAZ", class_level=10, class_section="A")
    case = services.create_case(
        petition_date=date(2026, 5, 18),
        petitioner_name="İdare",
        petitioner_role="IDARE",
        summary=summary,
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
# EK-1 + Türkçe duman testi (tasarım §11 kabulü)
# ---------------------------------------------------------------------------
def test_ek1_pdf_turkce_duman_ve_kutuk() -> None:
    case, sid = _committee_case()
    year = SchoolYearFactory()
    chair = PersonnelFactory(first_name="MÜDÜR", last_name="YARDIMCISI")
    services.create_committee(school_year_id=year.pk, chair_id=chair.pk)
    services.record_decision(
        case,
        student_id=sid,
        penalty_type=PenaltyType.REPRIMAND,
        decision_date=date(2026, 5, 22),
        penalty_detail=TURKCE_DUMAN,
    )
    pdf_bytes, record = doc_engine.generate_document(
        case,
        document_type=DocumentType.COMMITTEE_DECISION,
        generated_on=date(2026, 5, 22),
        student_id=sid,
    )
    text = _pdf_text(pdf_bytes)
    assert "ĞÜŞİÖÇ" in text and "ığüşiöç" in text  # Türkçe glifler kayıpsız
    assert "EMRE CAN YILMAZ" in text
    assert "Deneme Anadolu Lisesi".upper() in text.upper()
    assert "Menteşe KAYMAKAMLIĞI" in text  # antet kimliği sihirbazdan
    assert record is not None
    assert record.document_type == DocumentType.COMMITTEE_DECISION
    assert record.page_count >= 1
    assert record.sort_order == 90  # kanonik sıra


def test_veli_tebligi_guardian_alanlarindan() -> None:
    """Form-15 (veli sürümü) sorumlu veli adını guardian_* alanlarından basar."""
    case, sid = _committee_case()
    student = selectors.get_case(case.pk).case_students.get().student  # type: ignore[union-attr]
    student.guardian_name = "AYŞE YILMAZ"
    student.guardian_kinship = "ANNE"
    student.save(update_fields=["guardian_name", "guardian_kinship"])
    services.record_decision(
        case, student_id=sid, penalty_type=PenaltyType.REPRIMAND, decision_date=date(2026, 5, 22)
    )
    pdf_bytes, _record = doc_engine.generate_document(
        case,
        document_type=DocumentType.PENALTY_NOTICE,
        generated_on=date(2026, 5, 23),
        recipient=doc_engine.RECIPIENT_PARENT,
        student_id=sid,
    )
    text = _pdf_text(pdf_bytes)
    assert "AYŞE YILMAZ" in text
    assert "2025-2026/0001" in text


# ---------------------------------------------------------------------------
# Dal A/B kısıtı + Form-16/17 kesinleşme kilidi (AYNEN korunmalı)
# ---------------------------------------------------------------------------
def test_dal_a_kurul_formu_uretilemez() -> None:
    SchoolYearFactory()
    _setup_school()
    s = StudentFactory()
    case = services.create_case(
        petition_date=date(2026, 5, 18),
        petitioner_name="İdare",
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
    )  # Dal A — kurula sevk YOK
    accused = case.participants.get()
    with pytest.raises(ValueError, match="kurula sevk edilmedi"):
        doc_engine.generate_document(
            case,
            document_type=DocumentType.STATEMENT_CALL,
            generated_on=date(2026, 5, 20),
            participant_id=accused.pk,
        )
    # Dal A'da izinli: müdür uyarısı yazısı (Form-02) — gerekçeyle üretilir.
    pdf_bytes, _record = doc_engine.generate_document(
        case,
        document_type=DocumentType.WARNING_LETTER,
        generated_on=date(2026, 5, 20),
        student_id=s.pk,
        behavior_summary="Sınıf düzenini bozdu (md. 157/7).",
    )
    assert "157" in _pdf_text(pdf_bytes)


def test_uyari_yazisi_gerekce_zorunlu() -> None:
    case, sid = _committee_case()
    with pytest.raises(ValueError, match="kısa açıklaması zorunludur"):
        doc_engine.generate_document(
            case,
            document_type=DocumentType.WARNING_LETTER,
            generated_on=date(2026, 5, 20),
            student_id=sid,
        )


def test_form16_kesinlesme_kilidi() -> None:
    case, sid = _committee_case()
    d = services.record_decision(
        case,
        student_id=sid,
        penalty_type=PenaltyType.SHORT_TERM_SUSPENSION,
        decision_date=date(2026, 5, 22),
        suspension_days=3,
    )
    # Tebliğsiz → kesin değil → Form-16 üretilemez.
    with pytest.raises(ValueError, match="kesinleşmeden"):
        doc_engine.generate_document(
            case,
            document_type=DocumentType.PENALTY_DAYS_NOTICE,
            generated_on=date(2026, 5, 23),
            student_id=sid,
        )
    # Tebliğ + itiraz süresi (29.05.2026) bugünden önce doldu → kesin → üretilir.
    services.notify_decision(d, notified_on=date(2026, 5, 22))
    d.refresh_from_db()
    from apps.disiplin.services.decisions import update_decision_narrative

    # Uygulama başlangıcı kesinleşme sonrası girilir (md. 164/2 — narrative yolu).
    update_decision_narrative(d, fields={}, enforcement_start_date=date(2026, 6, 8))
    pdf_bytes, _record = doc_engine.generate_document(
        case,
        document_type=DocumentType.PENALTY_DAYS_NOTICE,
        generated_on=date(2026, 6, 8),
        student_id=sid,
    )
    text = _pdf_text(pdf_bytes)
    assert "08.06.2026" in text  # uygulama başlangıcı (iş günü hesabıyla basılır)


# ---------------------------------------------------------------------------
# Dizi pusulası + kütük API'si
# ---------------------------------------------------------------------------
def test_dizi_pusulasi_kategorili_ve_toplam_sayfali() -> None:
    case, sid = _committee_case()
    doc_engine.generate_document(
        case,
        document_type=DocumentType.WARNING_LETTER,
        generated_on=date(2026, 5, 20),
        student_id=sid,
        behavior_summary="Uyarı gerekçesi.",
    )
    pdf_bytes, record = doc_engine.generate_document(
        case, document_type=DocumentType.INDEX_SHEET, generated_on=date(2026, 5, 25), log=False
    )
    text = _pdf_text(pdf_bytes)
    assert "Müdür Uyarısı" in text  # kategori başlığı
    assert record is None  # fihrist kapağı kütüğe YAZILMAZ (OYS paritesi)


def test_document_log_api_crud_ve_reorder(client: APIClient) -> None:
    case, sid = _committee_case()
    # Elle/harici evrak kaydı (örn. taranmış dilekçe 2 sayfa).
    resp = client.post(
        f"/api/v1/discipline/cases/{case.pk}/documents/",
        {
            "document_type": "OTHER",
            "title": "Dilekçe (taranmış)",
            "generated_on": "2026-05-18",
            "page_count": 2,
        },
        format="json",
    )
    assert resp.status_code == 201, resp.content
    doc1 = resp.json()["id"]
    resp = client.post(
        f"/api/v1/discipline/cases/{case.pk}/documents/",
        {
            "document_type": "OTHER",
            "title": "Delil fotoğrafı",
            "generated_on": "2026-05-18",
            "parent_document": doc1,
        },
        format="json",
    )
    assert resp.status_code == 201
    alt = resp.json()["id"]

    # Zaman çizelgesi: ana evrak + altında alt evrak.
    timeline = client.get(f"/api/v1/discipline/cases/{case.pk}/documents/").json()
    assert len(timeline) == 1
    assert timeline[0]["sub_documents"][0]["id"] == alt

    # Alt evrak varken ana silinemez (sözleşmeli 400).
    resp = client.delete(f"/api/v1/discipline/cases/{case.pk}/documents/{doc1}/")
    assert resp.status_code == 400
    assert client.delete(f"/api/v1/discipline/cases/{case.pk}/documents/{alt}/").status_code == 204
    # Geri yükle + başlık düzelt.
    assert (
        client.post(f"/api/v1/discipline/cases/{case.pk}/documents/{alt}/restore/").status_code
        == 200
    )
    resp = client.patch(
        f"/api/v1/discipline/cases/{case.pk}/documents/{alt}/",
        {"title": "Delil fotoğrafı (renkli)"},
        format="json",
    )
    assert resp.json()["title"] == "Delil fotoğrafı (renkli)"


def test_documents_generate_api_pdf_ve_kutuk(client: APIClient) -> None:
    case, sid = _committee_case()
    services.record_decision(
        case, student_id=sid, penalty_type=PenaltyType.REPRIMAND, decision_date=date(2026, 5, 22)
    )
    resp = client.post(
        f"/api/v1/discipline/cases/{case.pk}/documents/generate/",
        {
            "document_type": DocumentType.COMMITTEE_DECISION,
            "generated_on": "2026-05-22",
            "student": sid,
        },
        format="json",
    )
    assert resp.status_code == 200, getattr(resp, "content", b"")[:300]
    assert resp["Content-Type"] == "application/pdf"
    assert "X-Document-Id" in resp
    body = b"".join(resp.streaming_content)  # type: ignore[attr-defined]
    assert body.startswith(b"%PDF")
    record = GeneratedDocument.objects.get(case=case)
    assert record.stored_pdf_size == len(body)
    assert record.stored_filename == f"{case.case_no}-{DocumentType.COMMITTEE_DECISION}.pdf"

    archived = client.get(f"/api/v1/discipline/cases/{case.pk}/documents/{record.pk}/download/")
    assert archived.status_code == 200
    assert b"".join(archived.streaming_content) == body  # type: ignore[attr-defined]

    assert (
        client.delete(f"/api/v1/discipline/cases/{case.pk}/documents/{record.pk}/").status_code
        == 204
    )
    deleted_copy = client.get(f"/api/v1/discipline/cases/{case.pk}/documents/{record.pk}/download/")
    assert deleted_copy.status_code == 200
    assert b"".join(deleted_copy.streaming_content) == body  # type: ignore[attr-defined]


def test_pdf_kopyasi_olmayan_eski_kutuk_kaydi_404(client: APIClient) -> None:
    case, _sid = _committee_case()
    record = services.log_generated_document(
        case,
        document_type=DocumentType.OTHER,
        title="Eski metadata kaydı",
        generated_on=date(2026, 5, 22),
    )
    response = client.get(f"/api/v1/discipline/cases/{case.pk}/documents/{record.pk}/download/")
    assert response.status_code == 404
    assert "saklanmış PDF" in response.json()["message"]


# ---------------------------------------------------------------------------
# Onur evrakları + karar defteri tutanağı
# ---------------------------------------------------------------------------
def test_onur_evraklari_uc_pdf(client: APIClient) -> None:
    year = SchoolYearFactory()
    _setup_school()
    chair = PersonnelFactory(first_name="ONUR", last_name="BAŞKANI")
    board = services.create_honor_board(school_year_id=year.pk, chair_id=chair.pk)
    uye = StudentFactory(
        first_name="KURUL",
        last_name="ÜYESİ",
        class_level=11,
        class_section="A",
    )
    assembly_member = services.add_general_assembly_member(
        school_year_id=year.pk,
        student_id=uye.pk,
        effective_from=year.start_date,
    )
    services.add_honor_board_member(
        board,
        student_id=uye.pk,
        grade_level=11,
        is_second_chair=True,
        assembly_member_id=assembly_member.pk,
    )
    komite_baskani = PersonnelFactory(first_name="DİSİPLİN", last_name="BAŞKANI")
    services.create_committee(school_year_id=year.pk, chair_id=komite_baskani.pk)

    aday = StudentFactory(first_name="ÖRNEK", last_name="ÖĞRENCİ", class_level=10)
    cert = services.propose_honor_certificate(
        student_id=aday.pk,
        proposer_role="TEACHER",
        criteria=["MANNERS"],
        justification="Görgü kurallarında örneklik (ĞÜŞİÖÇ).",
        proposer_name="AYŞE ÖĞRETMEN",
    )

    blank = client.get("/api/v1/honor/documents/proposal-form-blank/")
    assert blank.status_code == 200
    assert b"".join(blank.streaming_content).startswith(b"%PDF")  # type: ignore[attr-defined]

    dolu = client.post(
        "/api/v1/honor/documents/proposal-form/",
        {"certificate_ids": [cert.pk]},
        format="json",
    )
    text = _pdf_text(b"".join(dolu.streaming_content))  # type: ignore[attr-defined]
    assert "ÖRNEK ÖĞRENCİ" in text
    assert "ĞÜŞİÖÇ" in text

    services.recommend_honor_certificate(cert, recommended_on=date(2026, 5, 25))
    tutanak = client.post(
        "/api/v1/honor/documents/recommendation-record/",
        {"certificate_ids": [cert.pk]},
        format="json",
    )
    text = _pdf_text(b"".join(tutanak.streaming_content))  # type: ignore[attr-defined]
    assert "ONUR BAŞKANI" in text  # kurul başkanı imza satırı

    services.award_honor_certificate(cert, awarded_on=date(2026, 6, 1))
    karar = client.post(
        "/api/v1/honor/documents/award-record/",
        {"certificate_ids": [cert.pk]},
        format="json",
    )
    assert b"".join(karar.streaming_content).startswith(b"%PDF")  # type: ignore[attr-defined]


def test_karar_defteri_tutanagi_pdf(client: APIClient) -> None:
    year = SchoolYearFactory()
    _setup_school()
    meeting = services.create_council_meeting(
        school_year_id=year.pk,
        council_type="DISCIPLINE",
        meeting_date=date(2026, 5, 25),
        attendees=[
            {"person_name": "KURUL BAŞKANI", "attendee_role": "VOTING_MEMBER", "is_chair": True},
            {"person_name": "ÜYE ÖĞRETMEN", "attendee_role": "VOTING_MEMBER", "is_chair": False},
        ],
        agenda="Genel değerlendirme",
        decision_text="Oy birliğiyle karar verildi (ığüşiöç).",
    )
    resp = client.get(f"/api/v1/council/meetings/{meeting.pk}/minutes/")
    assert resp.status_code == 200
    text = _pdf_text(b"".join(resp.streaming_content))  # type: ignore[attr-defined]
    assert "ÖDÜL VE DİSİPLİN KURULU TOPLANTI TUTANAĞI" in text
    assert "ığüşiöç" in text
    assert "T001" in text


# ---------------------------------------------------------------------------
# F3 kısa inceleme bulguları (wf_b232ba05-0a7) — regresyon pinleri
# ---------------------------------------------------------------------------
def test_generate_ucundan_dizi_pusulasi_reddedilir(client: APIClient) -> None:
    """Bulgu 1/6: fihrist kapağı generate ucundan üretilmez; kütüğe kendini yazamaz."""
    case, _sid = _committee_case()
    resp = client.post(
        f"/api/v1/discipline/cases/{case.pk}/documents/generate/",
        {"document_type": "INDEX_SHEET", "generated_on": "2026-05-25"},
        format="json",
    )
    assert resp.status_code == 400
    assert "index-sheet" in resp.json()["message"]


def test_index_sheet_ucu_kutuge_yazmadan_uretir(client: APIClient) -> None:
    """Bulgu 2: GET documents/index-sheet — log=False fihrist yolu."""
    case, sid = _committee_case()
    services.record_decision(
        case, student_id=sid, penalty_type=PenaltyType.REPRIMAND, decision_date=date(2026, 5, 22)
    )
    client.post(
        f"/api/v1/discipline/cases/{case.pk}/documents/generate/",
        {"document_type": "COMMITTEE_DECISION", "generated_on": "2026-05-22", "student": sid},
        format="json",
    )
    before = GeneratedDocument.objects.filter(case=case).count()
    resp = client.get(f"/api/v1/discipline/cases/{case.pk}/documents/index-sheet/")
    assert resp.status_code == 200
    assert resp["Content-Disposition"].startswith("inline")
    assert b"".join(resp.streaming_content).startswith(b"%PDF")  # type: ignore[attr-defined]
    assert GeneratedDocument.objects.filter(case=case).count() == before  # kütük DEĞİŞMEDİ


def test_generate_log_parametresi_istemciden_kapatilamaz(client: APIClient) -> None:
    """Bulgu 4/8: resmî belge daima kütüğe yazılır — log=false yok sayılır."""
    case, sid = _committee_case()
    services.record_decision(
        case, student_id=sid, penalty_type=PenaltyType.REPRIMAND, decision_date=date(2026, 5, 22)
    )
    resp = client.post(
        f"/api/v1/discipline/cases/{case.pk}/documents/generate/",
        {
            "document_type": "COMMITTEE_DECISION",
            "generated_on": "2026-05-22",
            "student": sid,
            "log": False,
        },
        format="json",
    )
    assert resp.status_code == 200
    assert GeneratedDocument.objects.filter(case=case).count() == 1  # yine yazıldı


def test_onur_tutanagi_durum_kapisi(client: APIClient) -> None:
    """Bulgu 3: recommendation yalnız RECOMMENDED, award yalnız AWARDED belgeyi kabul eder."""
    SchoolYearFactory()
    _setup_school()
    student = StudentFactory()
    cert = services.propose_honor_certificate(
        student_id=student.pk, proposer_role="TEACHER", criteria=["MANNERS"]
    )
    resp = client.post(
        "/api/v1/honor/documents/recommendation-record/",
        {"certificate_ids": [cert.pk]},
        format="json",
    )
    assert resp.status_code == 400
    assert "md. 161" in resp.json()["message"]
    resp = client.post(
        "/api/v1/honor/documents/award-record/", {"certificate_ids": [cert.pk]}, format="json"
    )
    assert resp.status_code == 400


def test_certificate_ids_liste_dogrulamasi(client: APIClient) -> None:
    """Bulgu 10: null/sayı/string 500 değil sözleşmeli 400."""
    for bozuk in (None, 12, "12"):
        resp = client.post(
            "/api/v1/honor/documents/proposal-form/", {"certificate_ids": bozuk}, format="json"
        )
        assert resp.status_code == 400, bozuk


def test_document_patch_dogrulamalari(client: APIClient) -> None:
    """Bulgu 7: negatif page_count / metin-dışı title sözleşmeli 400."""
    case, _sid = _committee_case()
    resp = client.post(
        f"/api/v1/discipline/cases/{case.pk}/documents/",
        {"document_type": "OTHER", "title": "Ek", "generated_on": "2026-05-18"},
        format="json",
    )
    doc_id = resp.json()["id"]
    assert (
        client.patch(
            f"/api/v1/discipline/cases/{case.pk}/documents/{doc_id}/",
            {"page_count": -3},
            format="json",
        ).status_code
        == 400
    )
    assert (
        client.patch(
            f"/api/v1/discipline/cases/{case.pk}/documents/{doc_id}/",
            {"title": ["liste"]},
            format="json",
        ).status_code
        == 400
    )


def test_reorder_dogrulamalari(client: APIClient) -> None:
    """Bulgu 9: document_ids anahtarı (OYS) + liste-dışı gövde 400."""
    case, _sid = _committee_case()
    resp = client.post(
        f"/api/v1/discipline/cases/{case.pk}/documents/",
        {"document_type": "OTHER", "title": "Ek", "generated_on": "2026-05-18"},
        format="json",
    )
    doc_id = resp.json()["id"]
    assert (
        client.patch(
            f"/api/v1/discipline/cases/{case.pk}/documents/reorder/",
            {"document_ids": None},
            format="json",
        ).status_code
        == 400
    )
    resp = client.patch(
        f"/api/v1/discipline/cases/{case.pk}/documents/reorder/",
        {"document_ids": [doc_id]},
        format="json",
    )
    assert resp.status_code == 200
    assert resp.json()[0]["sort_order"] == 10
