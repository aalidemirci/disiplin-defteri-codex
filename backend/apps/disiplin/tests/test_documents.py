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
from apps.disiplin.tests.factories import (
    PersonnelFactory,
    SchoolYearFactory,
    StudentFactory,
    approve,
    ensure_terms,
)
from apps.okul.models import Student
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
    approve(d)
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

    # Onur Kurulu toplantısı: teklif gündeme alınır, uygun görülür (md. 183/b).
    ensure_terms(year)
    onur = services.create_council_meeting(
        school_year_id=year.pk,
        council_type="HONOR",
        meeting_date=date(2026, 5, 25),
        attendees=[
            {"person_name": "ONUR BAŞKANI", "attendee_role": "VOTING_MEMBER", "is_chair": True},
            {
                "person_name": "KURUL ÜYESİ",
                "attendee_role": "VOTING_MEMBER",
                "is_chair": False,
                "member_student_id": uye.pk,
            },
        ],
        honor_certificate_ids=[cert.pk],
    )
    services.decide_agenda_item(onur.agenda_items.get(), outcome="FAVORABLE")
    tutanak = client.post(
        "/api/v1/honor/documents/recommendation-record/", {"meeting": onur.pk}, format="json"
    )
    text = _pdf_text(b"".join(tutanak.streaming_content))  # type: ignore[attr-defined]
    assert "ONUR BAŞKANI" in text  # toplantı başkanı imza satırı
    assert "İkinci Başkan" in text  # kurul kaydındaki ikinci başkan işaretlenir
    assert "DİSİPLİN BAŞKANI" in text  # teslim-tesellüm
    # Toplantısız eski kayıt yolu korunur.
    eski = client.post(
        "/api/v1/honor/documents/recommendation-record/",
        {"certificate_ids": [cert.pk]},
        format="json",
    )
    assert eski.status_code == 200

    # Ödül ve Disiplin Kurulu toplantısı: kabul (md. 161/1); kurul = başkan → yeter sayı 1.
    odk = services.create_council_meeting(
        school_year_id=year.pk,
        council_type="DISCIPLINE",
        meeting_date=date(2026, 6, 1),
        attendees=[
            {"person_name": "DİSİPLİN BAŞKANI", "attendee_role": "VOTING_MEMBER", "is_chair": True}
        ],
        honor_certificate_ids=[cert.pk],
    )
    services.decide_agenda_item(odk.agenda_items.get(), outcome="FAVORABLE")
    karar = client.post("/api/v1/honor/documents/award-record/", {"meeting": odk.pk}, format="json")
    text = _pdf_text(b"".join(karar.streaming_content))  # type: ignore[attr-defined]
    assert "DİSİPLİN BAŞKANI" in text
    assert "01.06.2026" in text  # karar tarihi = toplantı tarihi
    yanlis = client.post(
        "/api/v1/honor/documents/award-record/", {"meeting": onur.pk}, format="json"
    )
    assert yanlis.status_code == 400  # çizelge kendi kurulunun toplantısından üretilir

    # Karar defteri gündem maddelerini basar (bilinçli istisna — yalnız ekleme).
    minutes = client.get(f"/api/v1/council/meetings/{odk.pk}/minutes/")
    text = _pdf_text(b"".join(minutes.streaming_content))  # type: ignore[attr-defined]
    assert "GÜNDEM MADDELERİ VE KARARLAR" in text
    assert "ÖRNEK ÖĞRENCİ" in text
    assert "Kabul edildi" in text
    # Genel karar metni yokken boş "KARAR" bölümü ve "oy birliği" cümlesi basılmaz.
    assert "İşbu karar" not in text


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
    # Gündem maddesiz toplantıda OYS çıktısı aynen: ek blok basılmaz.
    assert doc_engine._council_minutes_context(meeting)["agenda_items"] == []
    assert "GÜNDEM MADDELERİ" not in text
    assert "İşbu karar" in text


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


def test_uzatilmis_tedbir_bildirimi_uzatmayi_basar() -> None:
    """md. 175/2: uzatılmış tedbirde toplam süre "en fazla 10 iş günü" notuyla çelişmez."""
    case, sid = _committee_case()
    p = services.create_precaution(
        case, student_id=sid, start_date=date(2026, 5, 20), requested_days=10
    )
    pdf_bytes, _ = doc_engine.generate_document(
        case,
        document_type=DocumentType.PRECAUTION_NOTICE,
        generated_on=date(2026, 5, 20),
        student_id=sid,
    )
    assert "en fazla 10 iş günü" in _pdf_text(pdf_bytes)
    services.extend_precaution(p, additional_days=5, mne_notified=True)
    pdf_bytes, _ = doc_engine.generate_document(
        case,
        document_type=DocumentType.PRECAUTION_NOTICE,
        generated_on=date(2026, 5, 27),
        student_id=sid,
    )
    text = " ".join(_pdf_text(pdf_bytes).split())
    assert "15 iş günü" in text
    assert "1 kez uzatıldı" in text


def _appeal_letter_text(case: DisciplineCase, sid: int) -> str:
    pdf_bytes, _ = doc_engine.generate_document(
        case,
        document_type=DocumentType.APPEAL_LETTER,
        generated_on=date(2026, 6, 15),
        student_id=sid,
    )
    return " ".join(_pdf_text(pdf_bytes).split())


def test_form18_itiraz_eden_ve_sure_kayittan() -> None:
    """Form-18: itiraz eden (18+ öğrenci), süre dışı başvuru ve tebliğ tarihi kayıttan;
    itiraz derdestken karar "kesinleşmiş" yazılmaz (md. 169/3)."""
    case, sid = _committee_case()
    d = services.record_decision(
        case, student_id=sid, penalty_type=PenaltyType.REPRIMAND, decision_date=date(2026, 5, 22)
    )
    approve(d)
    services.notify_decision(d, notified_on=date(2026, 5, 22))
    Student.objects.filter(pk=sid).update(birth_date=date(2008, 1, 1))
    services.file_appeal(
        d, filed_on=date(2026, 6, 10), filed_by_role="STUDENT_ADULT", filed_by_name="EMRE CAN"
    )
    text = _appeal_letter_text(case, sid)
    assert "18 yaşını tamamlamış öğrenci EMRE CAN" in text
    assert "geçtikten sonra" in text
    assert "22.05.2026 tarihinde usulüne uygun" in text
    assert "kesinleşmiştir" not in text
    assert "tarafımdan onaylanmıştır" in text
    assert "ilçe öğrenci disiplin kurulunca" in text  # kınama → md. 169/3-a


def test_form18_mudur_itirazi_orantililik_gorusu_basmaz() -> None:
    case, sid = _committee_case()
    d = services.record_decision(
        case, student_id=sid, penalty_type=PenaltyType.REPRIMAND, decision_date=date(2026, 5, 22)
    )
    approve(d)
    services.notify_decision(d, notified_on=date(2026, 5, 22))
    services.file_appeal(d, filed_on=date(2026, 5, 25), filed_by_role="PRINCIPAL")
    text = _appeal_letter_text(case, sid)
    assert "Okul müdürü olarak tarafımdan" in text
    assert "içerisinde" in text
    assert "orantılı" not in text
    assert "itiraz yazısı" in text


def test_form18_md197_ilce_kararinda_itiraz_il_kurulunda() -> None:
    """md. 169/4, 202/1-b: ilçe kurulunun bağladığı karara itiraz il kurulunda."""
    case, sid = _committee_case()
    d = services.record_decision(
        case, student_id=sid, penalty_type=PenaltyType.REPRIMAND, decision_date=date(2026, 5, 20)
    )
    services.record_principal_review(d, action="RETURN", reason="a", decided_on=date(2026, 5, 21))
    services.record_principal_review(d, action="REFER", reason="b", decided_on=date(2026, 5, 26))
    services.set_decision_approval(d, approval_status="APPROVED", approved_on=date(2026, 6, 5))
    services.notify_decision(d, notified_on=date(2026, 6, 8))
    services.file_appeal(d, filed_on=date(2026, 6, 9), filed_by_role="PARENT")
    text = _appeal_letter_text(case, sid)
    assert "197. maddesi uyarınca gönderildiği ilçe" in text
    assert "il öğrenci disiplin kurulunca" in text
    assert "169. maddesi 3. fıkrası (a)" not in text


def test_form15_17_savunma_ifadesi_yalniz_savunma_tutanagiyla() -> None:
    """md. 194/1: "savunması alınmış" ancak savunma tutanağı (Form-11) kaydı varsa basılır."""
    from apps.disiplin.models import DisciplineParticipant, ParticipantRole

    case, sid = _committee_case()
    d = services.record_decision(
        case,
        student_id=sid,
        penalty_type=PenaltyType.SHORT_TERM_SUSPENSION,
        decision_date=date(2026, 5, 22),
        suspension_days=2,
    )
    approve(d)
    services.notify_decision(d, notified_on=date(2026, 5, 22))
    from apps.disiplin.services.decisions import update_decision_narrative

    update_decision_narrative(d, fields={}, enforcement_start_date=date(2026, 6, 8))

    def texts() -> list[str]:
        out = []
        for doc_type in (DocumentType.PENALTY_NOTICE, DocumentType.PENALTY_DAYS_NOTICE):
            pdf_bytes, _ = doc_engine.generate_document(
                case,
                document_type=doc_type,
                recipient=doc_engine.RECIPIENT_PARENT,
                generated_on=date(2026, 6, 8),
                student_id=sid,
                log=False,
            )
            out.append(" ".join(_pdf_text(pdf_bytes).split()))
        return out

    for text in texts():
        assert "savunması alınmış" not in text
        assert "sonucunda; olayla ilgili bilgi ve belgeler incelenmiştir" in text

    participant = DisciplineParticipant.objects.filter(
        case=case, student_id=sid, role=ParticipantRole.ACCUSED
    ).first() or services.add_participant(
        case, role=ParticipantRole.ACCUSED, person_type="STUDENT", person_id=sid
    )
    doc_engine.generate_document(
        case,
        document_type=DocumentType.DEFENSE_RECORD,
        generated_on=date(2026, 5, 21),
        participant_id=participant.pk,
    )
    for text in texts():
        assert "öğrencinin savunması alınmış, olayla ilgili" in text


def test_form12_oylama_esasi_secilir() -> None:
    """md. 191/1: kurul oy çoğunluğuyla karar alır — Form-12 hep "oy birliği" basmaz."""
    case, _sid = _committee_case()

    def text(vote_basis: str = "") -> str:
        pdf_bytes, _ = doc_engine.generate_document(
            case,
            document_type=DocumentType.DEADLINE_EXTENSION,
            generated_on=date(2026, 5, 25),
            vote_basis=vote_basis,
            log=False,
        )
        return " ".join(_pdf_text(pdf_bytes).split())

    assert "oy birliği ile karar verilmiştir" in text()
    majority = text("MAJORITY")
    assert "oy çoğunluğu ile karar verilmiştir" in majority
    assert "oy birliği" not in majority
    with pytest.raises(ValueError, match="oylama esası"):
        text("HEPSI")


def test_generate_ucu_oylama_esasini_iletir(client: APIClient) -> None:
    case, _sid = _committee_case()
    resp = client.post(
        f"/api/v1/discipline/cases/{case.pk}/documents/generate/",
        {
            "document_type": DocumentType.DEADLINE_EXTENSION,
            "generated_on": "2026-05-25",
            "vote_basis": "MAJORITY",
        },
        format="json",
    )
    assert resp.status_code == 200
    pdf = b"".join(resp.streaming_content)  # type: ignore[attr-defined]
    assert "oy çoğunluğu ile" in " ".join(_pdf_text(pdf).split())


def test_ek1_cezasiz_kararda_md197_iade_kutusu() -> None:
    """md. 197: müdür uygun bulmadığı her kararı (cezasız dahil) bir kez kurula iade eder."""
    case, sid = _committee_case()
    services.record_decision(
        case, student_id=sid, penalty_type=PenaltyType.NO_PENALTY, decision_date=date(2026, 5, 22)
    )
    pdf_bytes, _ = doc_engine.generate_document(
        case,
        document_type=DocumentType.COMMITTEE_DECISION,
        generated_on=date(2026, 5, 22),
        student_id=sid,
        log=False,
    )
    text = " ".join(_pdf_text(pdf_bytes).split())
    assert "GÖRÜLMÜŞTÜR" in text
    assert "YENİDEN GÖRÜŞÜLMESİ HUSUSUNDA" in text
    assert "gerektirmez (md. 191)" not in text
    assert "UYGUNDUR" not in text


# ---------------------------------------------------------------------------
# M2 Grup 1 — süreç yazıları (kullanıcı kararı 27.09.2026)
# ---------------------------------------------------------------------------
def _letter_text(case: DisciplineCase, sid: int, document_type: str, variant: str = "") -> str:
    pdf_bytes, _ = doc_engine.generate_document(
        case,
        document_type=document_type,
        generated_on=date(2026, 6, 1),
        student_id=sid,
        variant=variant,
        log=False,
    )
    return " ".join(_pdf_text(pdf_bytes).split())


def test_md197_iade_ve_ilceye_gonderme_yazilari() -> None:
    case, sid = _committee_case()
    d = services.record_decision(
        case, student_id=sid, penalty_type=PenaltyType.REPRIMAND, decision_date=date(2026, 5, 20)
    )
    with pytest.raises(ValueError, match="iade edilmemiş"):
        _letter_text(case, sid, DocumentType.RETURN_LETTER)
    services.record_principal_review(
        d, action="RETURN", reason="Savunma alınmadan karar verilmiş.", decided_on=date(2026, 5, 21)
    )
    text = _letter_text(case, sid, DocumentType.RETURN_LETTER)
    assert "Savunma alınmadan karar verilmiş." in text
    assert "bir defa daha görüşülmek üzere" in text
    assert "ALİ ÖRNEK" in text  # müdür imzası (kurulum sihirbazı)
    with pytest.raises(ValueError, match="ilçe kuruluna gönderilmemiş"):
        _letter_text(case, sid, DocumentType.DISTRICT_REFERRAL_LETTER)

    services.record_principal_review(
        d, action="REFER", reason="Ceza fiille orantısız.", decided_on=date(2026, 5, 26)
    )
    text = _letter_text(case, sid, DocumentType.DISTRICT_REFERRAL_LETTER)
    assert "Savunma alınmadan karar verilmiş." in text  # iade gerekçesi
    assert "Ceza fiille orantısız." in text  # görüş ve teklifler
    assert "İlçeye sevk:" not in text  # iç işaret basılmaz
    assert "görüşülmek ve karara bağlanmak üzere" in text


def test_md169_1_onaya_sevk_yazisi_yalniz_ilce_il_onayli_cezada() -> None:
    case, sid = _committee_case()
    services.record_decision(
        case, student_id=sid, penalty_type=PenaltyType.REPRIMAND, decision_date=date(2026, 5, 20)
    )
    with pytest.raises(ValueError, match="ilçe/il kurulu onayına"):
        _letter_text(case, sid, DocumentType.APPROVAL_REQUEST_LETTER)
    d = case.decisions.get()
    services.update_decision(
        d, penalty_type=PenaltyType.SCHOOL_CHANGE, decision_date=date(2026, 5, 20)
    )
    text = _letter_text(case, sid, DocumentType.APPROVAL_REQUEST_LETTER)
    assert "(b) bendi uyarınca ilçe öğrenci disiplin kurulunun" in text
    services.update_decision(d, penalty_type=PenaltyType.EXPULSION, decision_date=date(2026, 5, 20))
    text = _letter_text(case, sid, DocumentType.APPROVAL_REQUEST_LETTER)
    assert "(c) bendi uyarınca il öğrenci disiplin kurulunun" in text


def test_md175_mem_bilgilendirme_ve_uzatma_onayi_yazisi() -> None:
    case, sid = _committee_case()
    with pytest.raises(ValueError, match="tedbir"):
        _letter_text(case, sid, DocumentType.PRECAUTION_MEM_LETTER, "info")
    p = services.create_precaution(
        case, student_id=sid, start_date=date(2026, 5, 20), requested_days=5
    )
    info = _letter_text(case, sid, DocumentType.PRECAUTION_MEM_LETTER, "info")
    assert "20.05.2026" in info and "5 iş günü" in info
    ext = _letter_text(case, sid, DocumentType.PRECAUTION_MEM_LETTER, "extension")
    assert "1. kez" in ext and "OLUR" in ext
    services.extend_precaution(p, additional_days=3, mne_notified=True)
    services.extend_precaution(p, additional_days=3, mne_notified=True)
    with pytest.raises(ValueError, match="iki kez"):
        _letter_text(case, sid, DocumentType.PRECAUTION_MEM_LETTER, "extension")


def test_md192_3_form13_mudur_olur_blogu() -> None:
    case, _sid = _committee_case()
    pdf_bytes, _ = doc_engine.generate_document(
        case,
        document_type=DocumentType.DEADLINE_EXTENSION,
        generated_on=date(2026, 5, 25),
        variant="petition",
        log=False,
    )
    text = " ".join(_pdf_text(pdf_bytes).split())
    assert "OLUR" in text and "ALİ ÖRNEK" in text


def test_surec_yazilari_kutuge_ve_kategoriye_girer() -> None:
    case, sid = _committee_case()
    services.create_precaution(case, student_id=sid, start_date=date(2026, 5, 20), requested_days=5)
    _pdf, record = doc_engine.generate_document(
        case,
        document_type=DocumentType.PRECAUTION_MEM_LETTER,
        generated_on=date(2026, 5, 20),
        student_id=sid,
        variant="info",
    )
    assert record is not None
    assert record.title == "Tedbir Millî Eğitim Müdürlüğü Yazısı (md. 175)"
    assert record.sort_order == 6  # tedbir bildiriminin (5) hemen ardı
    groups = doc_engine.categorized_documents([record])
    assert groups[0]["label"] == "Tedbir / Süre Uzatma"


# ---------------------------------------------------------------------------
# M2 Grup 2 — tutanaklar (kullanıcı kararı 27.09.2026)
# ---------------------------------------------------------------------------
def _warning_only_case() -> tuple[DisciplineCase, int]:
    SchoolYearFactory()
    _setup_school()
    s = StudentFactory(
        first_name="EMRE CAN",
        last_name="YILMAZ",
        class_level=10,
        class_section="A",
        guardian_name="AYŞE YILMAZ",
        guardian_kinship="ANNE",
    )
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
    )
    services.issue_warning(case, student_id=s.pk, warning_date=date(2026, 5, 19), summary="geç")
    return case, s.pk


def test_md157_7b_veli_davet_gorusme_gelmedi_dal_a_da_uretilir() -> None:
    from apps.okul.models import ClassResponsibility, Personnel, SchoolYear

    case, sid = _warning_only_case()
    rehber = Personnel.objects.create(first_name="REHBER", last_name="ÖĞRETMEN")
    ClassResponsibility.objects.create(
        school_year=SchoolYear.objects.get(is_active=True),
        class_level=10,
        class_section="A",
        guidance_teacher=rehber,
    )

    def text(variant: str) -> str:
        pdf_bytes, _ = doc_engine.generate_document(
            case,
            document_type=DocumentType.PARENT_MEETING,
            generated_on=date(2026, 5, 25),
            student_id=sid,
            variant=variant,
            statement_date=date(2026, 5, 27),
            statement_time="10:00",
            log=False,
        )
        return " ".join(_pdf_text(pdf_bytes).split())

    invite = text("invite")
    assert "VELİ DAVET YAZISI" in invite and "AYŞE YILMAZ" in invite
    assert "27.05.2026" in invite and "19.05.2026 tarihinde yazılı olarak uyarılmış" in invite
    meeting = text("meeting")
    assert "VELİ GÖRÜŞME TUTANAĞI" in meeting and "REHBER ÖĞRETMEN" in meeting
    no_show = text("no_show")
    assert "gelmemiştir" in no_show


def test_md157_7d_veli_gorusmesi_nakil_imhasinda_silinir() -> None:
    from apps.disiplin.selectors import purge as purge_selectors

    case, sid = _warning_only_case()
    doc_engine.generate_document(
        case,
        document_type=DocumentType.PARENT_MEETING,
        generated_on=date(2026, 5, 25),
        student_id=sid,
        variant="meeting",
    )
    docs = purge_selectors.warning_letter_documents(case_id=case.pk, student_id=sid)
    assert [d.document_type for d in docs] == [DocumentType.PARENT_MEETING]


def test_md158_3_arama_tutanagi_ve_md195_tespit_tutanagi() -> None:
    from apps.disiplin.models import DisciplineParticipant, ParticipantRole

    case, sid = _committee_case()
    pdf_bytes, record = doc_engine.generate_document(
        case,
        document_type=DocumentType.SEARCH_RECORD,
        generated_on=date(2026, 5, 20),
        statement_place="10/A sınıfı dolapları",
    )
    text = " ".join(_pdf_text(pdf_bytes).split())
    assert "ARAMA TUTANAĞI" in text and "İki nüsha" in text
    assert "10/A sınıfı dolapları" in text and "ONAYLANDI" in text
    assert record is not None and record.student_id is None

    participant = DisciplineParticipant.objects.filter(
        case=case, student_id=sid, role=ParticipantRole.ACCUSED
    ).first() or services.add_participant(
        case, role=ParticipantRole.ACCUSED, person_type="STUDENT", person_id=sid
    )
    pdf_bytes, _ = doc_engine.generate_document(
        case,
        document_type=DocumentType.NON_COMPLIANCE_RECORD,
        generated_on=date(2026, 5, 21),
        participant_id=participant.pk,
        log=False,
    )
    text = " ".join(_pdf_text(pdf_bytes).split())
    assert "EMRE CAN YILMAZ" in text
    assert "dosyada bulunan bilgi ve belgelere göre karar verilir" in text


def test_md157_7a_form01_degerlendirme_ve_oneri_formu() -> None:
    """M2 Grup 3: Form-01 Dal A'da üretilir; önceki ceza yoksa "Yok" basar, uyarı özeti dolu."""
    case, sid = _warning_only_case()
    pdf_bytes, record = doc_engine.generate_document(
        case,
        document_type=DocumentType.GUIDANCE_ASSESSMENT,
        generated_on=date(2026, 5, 19),
        student_id=sid,
    )
    text = " ".join(_pdf_text(pdf_bytes).split())
    assert "REHBERLİK DEĞERLENDİRME VE ÖNERİ FORMU" in text
    assert "Yok (md. 157/7" in text and "geç" in text
    assert record is not None and record.sort_order == 8
    from apps.disiplin.selectors import purge as purge_selectors

    docs = purge_selectors.warning_letter_documents(case_id=case.pk, student_id=sid)
    assert [d.document_type for d in docs] == [DocumentType.GUIDANCE_ASSESSMENT]
