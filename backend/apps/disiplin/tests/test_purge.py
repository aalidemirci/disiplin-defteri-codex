"""md. 157/7 imha aracı testleri (F5-D2) — kapsam, tutanak, iki aşamalı onay, hard delete.

Mevzuat dayanağı (docs/mevzuat/ortaogretim-yonetmeligi-disiplin-md157-206.md):
md. 157/7-ç "Yazılı uyarı ile veli görüşmesine ilişkin bilgiler e-Okul sistemine
işlenmez", md. 157/7-d "Sosyal sorumluluk programı çalışmasına ilişkin belgeler
hariç diğer belgeler DERS YILI SONUNDA ya da öğrencinin NAKİL OLDUĞU TARİHTEN
İTİBAREN 5 İŞ GÜNÜ içinde imha edilir."

Kırmızı çizgi: KURUL KARARLI (Dal B) dosyalar aracın DIŞINDADIR — servis reddeder.
Silme bilinçli hard delete'tir (soft-delete istisnası); `all_objects`'te de kalmaz.
Öğrenci sicili ASLA silinmez (PROTECT).
"""

from __future__ import annotations

from datetime import date
from io import BytesIO
from typing import Any

import pytest
from pypdf import PdfReader
from rest_framework.test import APIRequestFactory

from apps.disiplin import selectors, services, views_purge
from apps.disiplin.models import (
    CaseStage,
    DisciplineCase,
    DisciplineEvent,
    DisciplineParticipant,
    DisciplineWarning,
    DocumentType,
    GeneratedDocument,
    PenaltyType,
    PrincipalDecision,
)
from apps.disiplin.selectors import purge as purge_selectors
from apps.disiplin.services import purge as purge_service
from apps.disiplin.tests.factories import PersonnelFactory, SchoolYearFactory, StudentFactory
from apps.okul.models import Student
from apps.okul.services import setup as okul_setup

pytestmark = pytest.mark.django_db

TURKCE_DUMAN = "ĞÜŞİÖÇ ığüşiöç İstanbul"


def _pdf_text(pdf_bytes: bytes) -> str:
    reader = PdfReader(BytesIO(pdf_bytes))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _setup_school() -> None:
    SchoolYearFactory()
    okul_setup.update_school_config(
        fields={
            "school_name": "Deneme Anadolu Lisesi",
            "district": "Menteşe",
            "principal_name": "ALİ ÖRNEK",
        }
    )


def _warning_case(
    *, last_name: str = "YILMAZ", warn: bool = True, student: Student | None = None
) -> tuple[DisciplineCase, Student]:
    """Dal A dosyası: müdür YAZILI UYARI verir → dosya otomatik kapanır (md. 157/7)."""
    s = student or StudentFactory(first_name="EMRE CAN", last_name=last_name)
    case = services.create_case(
        petition_date=date(2026, 3, 2),
        petitioner_name="İdare",
        petitioner_role="IDARE",
        summary="Sınıf içinde uygunsuz davranış.",
        student_ids=[s.pk],
    )
    services.add_event(
        case,
        CaseStage.DECIDED,
        date(2026, 3, 5),
        override=True,
        override_reason="Rehberlik atlandı.",
        principal_decisions=[PrincipalDecision.WRITTEN_WARNING],
    )
    if warn:
        services.issue_warning(
            case,
            student_id=s.pk,
            warning_date=date(2026, 3, 5),
            summary=f"Kusurlu davranışa dikkat çekildi. {TURKCE_DUMAN}",
        )
        services.log_generated_document(
            case,
            document_type=DocumentType.WARNING_LETTER,
            title="Müdür Uyarısı Yazısı (Form-02)",
            generated_on=date(2026, 3, 5),
            student_id=s.pk,
        )
    case.refresh_from_db()
    return case, s


def _committee_case() -> tuple[DisciplineCase, Student]:
    """Dal B dosyası: kurula sevk + kurul kararı (imha aracının DIŞINDA)."""
    s = StudentFactory(first_name="ELİF", last_name="KAYA")
    case = services.create_case(
        petition_date=date(2026, 3, 2),
        petitioner_name="İdare",
        petitioner_role="IDARE",
        summary="Kurulluk fiil.",
        student_ids=[s.pk],
    )
    services.add_event(
        case,
        CaseStage.DECIDED,
        date(2026, 3, 5),
        override=True,
        override_reason="Rehberlik atlandı.",
        principal_decisions=[PrincipalDecision.DISCIPLINE_COMMITTEE],
    )
    year = SchoolYearFactory()
    chair = PersonnelFactory(first_name="MÜDÜR", last_name="YARDIMCISI")
    services.create_committee(school_year_id=year.pk, chair_id=chair.pk)
    services.record_decision(
        case,
        student_id=s.pk,
        penalty_type=PenaltyType.REPRIMAND,
        decision_date=date(2026, 3, 10),
    )
    # KAPALI Dal B dosyası: "kapanmış olmak" imha için YETMEZ — kurul kararı engeldir.
    services.close_case(case, override=True, override_reason="Test kapanışı.")
    case.refresh_from_db()
    return case, s


# ---------------------------------------------------------------------------
# Kapsam: Dal A listelenir, Dal B REDDEDİLİR
# ---------------------------------------------------------------------------
def test_dal_a_uyari_dosyasi_imha_kapsaminda() -> None:
    _setup_school()
    case, student = _warning_case()

    assert purge_selectors.case_purge_blockers(case) == []
    items = purge_selectors.purgeable_case_items()
    assert [i.case_id for i in items] == [case.pk]
    item = items[0]
    assert item.case_no == case.case_no
    assert item.students == (student.full_name,)
    assert item.warning_count == 1
    assert item.warning_letter_count == 1


def test_dal_b_kurul_kararli_dosya_kapsam_disi() -> None:
    _setup_school()
    case, _s = _committee_case()

    blockers = purge_selectors.case_purge_blockers(case)
    assert blockers, "Kurul kararlı dosya imha kapsamına GİREMEZ (md. 163-170)."
    assert purge_selectors.BLOCKER_HAS_DECISION in blockers
    assert purge_selectors.BLOCKER_COMMITTEE_REFERRAL in blockers
    assert not purge_selectors.is_purgeable_case(case)
    assert purge_selectors.purgeable_case_items() == []


def test_dal_b_karar_soft_delete_edilse_de_kapsam_disi() -> None:
    """Karar çöp kutusuna atılmış olsa da dosya Dal B'dir — imha edilemez."""
    _setup_school()
    case, student = _committee_case()
    decision = selectors.decisions_for_case(case).first()
    assert decision is not None
    services.delete_decision(decision)

    assert not purge_selectors.is_purgeable_case(case)


def test_acik_dosya_kapsam_disi() -> None:
    _setup_school()
    student = StudentFactory(last_name="AÇIK")
    case = services.create_case(
        petition_date=date(2026, 3, 2),
        petitioner_name="İdare",
        petitioner_role="IDARE",
        summary="Henüz karara bağlanmadı.",
        student_ids=[student.pk],
    )
    assert not purge_selectors.is_purgeable_case(case)
    assert purge_selectors.purgeable_case_items() == []


def test_onizleme_ogrenci_listesini_ve_toplamlari_dondurur() -> None:
    _setup_school()
    case, student = _warning_case()
    _committee_case()  # Dal B — önizlemede GÖRÜNMEZ

    preview = purge_service.preview()
    assert [c.case_id for c in preview.cases] == [case.pk]
    assert preview.totals["cases"] == 1
    assert preview.totals["warnings"] == 1
    assert preview.totals["documents"] == 1
    assert [s.student_id for s in preview.students] == [student.pk]


# ---------------------------------------------------------------------------
# Tutanak (kalıcı tek iz)
# ---------------------------------------------------------------------------
def test_tutanak_pdf_turkce_metin_ve_mevzuat_dayanagi() -> None:
    _setup_school()
    case, student = _warning_case()

    record = purge_service.issue_record(
        case_ids=[case.pk], purge_date=date(2026, 6, 26), confirmed=True
    )
    text = _pdf_text(record.pdf_bytes)

    assert "İMHA TUTANAĞI" in text
    assert "Deneme Anadolu Lisesi".upper() in text.upper()
    assert "Menteşe KAYMAKAMLIĞI" in text  # antet kimliği sihirbazdan
    assert "157" in text  # mevzuat dayanağı (md. 157/7-d)
    assert student.full_name in text
    assert case.case_no in text
    assert "26.06.2026" in text
    assert "ALİ ÖRNEK" in text  # imza bloğu — okul müdürü
    assert record.token


def test_tutanak_diske_kalici_yazilir() -> None:
    from django.conf import settings

    _setup_school()
    case, _student = _warning_case()

    record = purge_service.issue_record(case_ids=[case.pk], confirmed=True)
    stored = settings.MEDIA_ROOT / record.stored_path
    assert stored.exists()
    assert stored.read_bytes() == record.pdf_bytes


def test_tutanak_onaysiz_uretilemez() -> None:
    _setup_school()
    case, _student = _warning_case()
    with pytest.raises(ValueError, match="onay"):
        purge_service.issue_record(case_ids=[case.pk], confirmed=False)


def test_tutanak_bos_kapsamda_uretilemez() -> None:
    _setup_school()
    with pytest.raises(ValueError, match="edilecek kayıt seçilmedi"):
        purge_service.issue_record(case_ids=[], confirmed=True)


def test_tutanak_dal_b_dosyayi_reddeder() -> None:
    _setup_school()
    case, _s = _committee_case()
    with pytest.raises(ValueError, match="Dal B"):
        purge_service.issue_record(case_ids=[case.pk], confirmed=True)


# ---------------------------------------------------------------------------
# İki aşamalı onay
# ---------------------------------------------------------------------------
def test_tutanaksiz_imha_yapilamaz() -> None:
    """İkinci onay TUTANAK ÜRETİLDİKTEN SONRA gelir — jetonsuz uygulama reddedilir."""
    _setup_school()
    case, _student = _warning_case()
    with pytest.raises(ValueError, match="tutanağı üretilmeden"):
        purge_service.execute(token="", confirmed=True)
    assert DisciplineCase.objects.filter(pk=case.pk).exists()


def test_ikinci_onay_zorunlu() -> None:
    _setup_school()
    case, _student = _warning_case()
    record = purge_service.issue_record(case_ids=[case.pk], confirmed=True)
    with pytest.raises(ValueError, match="onay"):
        purge_service.execute(token=record.token, confirmed=False)
    assert DisciplineCase.objects.filter(pk=case.pk).exists()


def test_bozuk_jeton_reddedilir() -> None:
    _setup_school()
    case, _student = _warning_case()
    purge_service.issue_record(case_ids=[case.pk], confirmed=True)
    with pytest.raises(ValueError, match="tutanağı üretilmeden"):
        purge_service.execute(token="uydurma-jeton", confirmed=True)
    assert DisciplineCase.objects.filter(pk=case.pk).exists()


def test_jeton_tek_kullanimlik_degil_ama_kapsam_yeniden_dogrulanir() -> None:
    """Jeton üretildikten sonra dosya Dal B'ye dönerse imha reddedilir (yeniden doğrulama)."""
    _setup_school()
    case, student = _warning_case()
    record = purge_service.issue_record(case_ids=[case.pk], confirmed=True)

    # Aynı dosyaya kurul kararı işlenirse kapsam bozulur.
    year = SchoolYearFactory()
    chair = PersonnelFactory(first_name="MÜDÜR", last_name="YARDIMCISI")
    services.create_committee(school_year_id=year.pk, chair_id=chair.pk)
    services.record_decision(
        case,
        student_id=student.pk,
        penalty_type=PenaltyType.REPRIMAND,
        decision_date=date(2026, 3, 10),
    )

    with pytest.raises(ValueError, match="kapsam|Dal B|kurul"):
        purge_service.execute(token=record.token, confirmed=True)
    assert DisciplineCase.objects.filter(pk=case.pk).exists()


# ---------------------------------------------------------------------------
# Hard delete — kayıtlar GERÇEKTEN gider, öğrenci KALIR
# ---------------------------------------------------------------------------
def test_imha_kayitlari_gercekten_siler_ogrenciyi_silmez() -> None:
    _setup_school()
    case, student = _warning_case()
    case_id = case.pk

    record = purge_service.issue_record(case_ids=[case_id], confirmed=True)
    result = purge_service.execute(token=record.token, confirmed=True)

    assert result.purged_cases == 1
    assert result.purged_warnings == 1
    assert result.purged_documents == 1
    # Soft-delete DEĞİL: all_objects'te de yok.
    assert not DisciplineCase.all_objects.filter(pk=case_id).exists()
    assert not DisciplineWarning.all_objects.filter(case_id=case_id).exists()
    assert not GeneratedDocument.all_objects.filter(case_id=case_id).exists()
    assert not DisciplineEvent.all_objects.filter(case_id=case_id).exists()
    assert not DisciplineParticipant.all_objects.filter(case_id=case_id).exists()
    # Öğrenci sicili PROTECT — imha edilmez.
    assert Student.objects.filter(pk=student.pk).exists()


def test_imha_sonrasi_dal_b_dosyalar_dokunulmaz() -> None:
    _setup_school()
    dal_a, _s1 = _warning_case(last_name="ADAL")
    dal_b, _s2 = _committee_case()

    record = purge_service.issue_record(case_ids=[dal_a.pk], confirmed=True)
    purge_service.execute(token=record.token, confirmed=True)

    assert not DisciplineCase.all_objects.filter(pk=dal_a.pk).exists()
    assert DisciplineCase.objects.filter(pk=dal_b.pk).exists()


def test_imha_ek_dosyalarini_diskten_de_siler() -> None:
    from apps.disiplin import file_storage

    _setup_school()
    case, _student = _warning_case()
    png = bytes.fromhex("89504e470d0a1a0a0000000d49484452") + b"\x00" * 64
    attachment, _dup = services.add_attachment(
        case=case, file_bytes=png, original_filename="dilekce.png", file_type="PETITION_SCAN"
    )
    path = file_storage.absolute_path(attachment.file_path)
    assert path.exists()

    record = purge_service.issue_record(case_ids=[case.pk], confirmed=True)
    result = purge_service.execute(token=record.token, confirmed=True)

    assert result.purged_attachments == 1
    assert not path.exists()


# ---------------------------------------------------------------------------
# Nakil senaryosu — tekil imha + "+5 iş günü" göstergesi (md. 157/7-d)
# ---------------------------------------------------------------------------
def test_nakil_onizlemesi_bes_is_gunu_son_gununu_hesaplar() -> None:
    _setup_school()
    _case, student = _warning_case()

    # 15.06.2026 Pazartesi → +5 iş günü = 22.06.2026 Pazartesi.
    preview = purge_service.preview_student(
        student.pk, transfer_date=date(2026, 6, 15), today=date(2026, 6, 17)
    )
    assert preview.transfer_date == date(2026, 6, 15)
    assert preview.purge_deadline == date(2026, 6, 22)
    assert preview.working_days_left == 3  # 18, 19 ve 22 Haziran
    assert preview.overdue is False
    assert len(preview.warnings) == 1


def test_nakil_son_gunu_gecmisse_gecikme_isaretlenir() -> None:
    _setup_school()
    _case, student = _warning_case()
    preview = purge_service.preview_student(
        student.pk, transfer_date=date(2026, 6, 15), today=date(2026, 6, 30)
    )
    assert preview.overdue is True


def test_nakil_tarihi_verilmezse_gosterge_bos() -> None:
    _setup_school()
    _case, student = _warning_case()
    preview = purge_service.preview_student(student.pk)
    assert preview.purge_deadline is None
    assert preview.overdue is False


def test_tekil_imha_yalniz_o_ogrencinin_izlerini_siler() -> None:
    """Çok öğrencili dosyada nakil eden öğrencinin uyarısı silinir, DOSYA KALIR."""
    _setup_school()
    giden = StudentFactory(first_name="NAKİL", last_name="GİDEN")
    kalan = StudentFactory(first_name="OKULDA", last_name="KALAN")
    case = services.create_case(
        petition_date=date(2026, 3, 2),
        petitioner_name="İdare",
        petitioner_role="IDARE",
        summary="İki öğrencili olay.",
        student_ids=[giden.pk, kalan.pk],
    )
    services.add_event(
        case,
        CaseStage.DECIDED,
        date(2026, 3, 5),
        override=True,
        override_reason="Rehberlik atlandı.",
        principal_decisions=[PrincipalDecision.WRITTEN_WARNING],
    )
    for s in (giden, kalan):
        services.issue_warning(
            case, student_id=s.pk, warning_date=date(2026, 3, 5), summary="Dikkat çekildi."
        )
        services.log_generated_document(
            case,
            document_type=DocumentType.WARNING_LETTER,
            title="Müdür Uyarısı Yazısı (Form-02)",
            generated_on=date(2026, 3, 5),
            student_id=s.pk,
        )

    record = purge_service.issue_record(
        student_id=giden.pk, transfer_date=date(2026, 6, 15), confirmed=True
    )
    result = purge_service.execute(token=record.token, confirmed=True)

    assert result.purged_cases == 0  # çok öğrencili dosya AYAKTA kalır
    assert result.purged_warnings == 1
    assert result.purged_documents == 1
    assert not DisciplineWarning.all_objects.filter(student_id=giden.pk).exists()
    assert DisciplineWarning.objects.filter(student_id=kalan.pk).count() == 1
    assert DisciplineCase.objects.filter(pk=case.pk).exists()
    assert Student.objects.filter(pk=giden.pk).exists()


def test_tekil_imha_tek_ogrencili_dosyayi_butunuyle_siler() -> None:
    _setup_school()
    case, student = _warning_case()

    record = purge_service.issue_record(student_id=student.pk, confirmed=True)
    result = purge_service.execute(token=record.token, confirmed=True)

    assert result.purged_cases == 1
    assert not DisciplineCase.all_objects.filter(pk=case.pk).exists()
    assert Student.objects.filter(pk=student.pk).exists()


def test_tekil_imha_dal_b_izlerini_silmez() -> None:
    """Aynı öğrencinin kurul kararlı dosyası varsa o dosyaya DOKUNULMAZ."""
    _setup_school()
    student = StudentFactory(first_name="ÇİFT", last_name="DOSYALI")
    dal_a, _s = _warning_case(student=student)
    dal_b = services.create_case(
        petition_date=date(2026, 4, 2),
        petitioner_name="İdare",
        petitioner_role="IDARE",
        summary="Kurulluk fiil.",
        student_ids=[student.pk],
    )
    services.add_event(
        dal_b,
        CaseStage.DECIDED,
        date(2026, 4, 5),
        override=True,
        override_reason="Rehberlik atlandı.",
        principal_decisions=[PrincipalDecision.DISCIPLINE_COMMITTEE],
    )

    record = purge_service.issue_record(student_id=student.pk, confirmed=True)
    purge_service.execute(token=record.token, confirmed=True)

    assert not DisciplineCase.all_objects.filter(pk=dal_a.pk).exists()
    assert DisciplineCase.objects.filter(pk=dal_b.pk).exists()


def test_ogrenci_tutanaginda_nakil_son_gunu_basilir() -> None:
    _setup_school()
    _case, student = _warning_case()
    record = purge_service.issue_record(
        student_id=student.pk,
        transfer_date=date(2026, 6, 15),
        purge_date=date(2026, 6, 18),
        confirmed=True,
    )
    text = _pdf_text(record.pdf_bytes)
    assert "15.06.2026" in text  # nakil tarihi
    assert "22.06.2026" in text  # +5 iş günü son günü
    assert student.full_name in text


# ---------------------------------------------------------------------------
# API yüzeyi (urls.py bağlanmadan doğrudan view çağrısıyla)
# ---------------------------------------------------------------------------
@pytest.fixture
def factory() -> APIRequestFactory:
    return APIRequestFactory()


def _json(response: Any) -> Any:
    response.render() if hasattr(response, "render") else None
    return response.data


def test_api_onizleme_ucu(factory: APIRequestFactory) -> None:
    _setup_school()
    case, _student = _warning_case()
    response = views_purge.PurgePreviewView.as_view()(factory.get("/imha/onizleme/"))
    assert response.status_code == 200
    assert [c["case_id"] for c in _json(response)["cases"]] == [case.pk]


def test_api_ogrenci_onizleme_ucu(factory: APIRequestFactory) -> None:
    _setup_school()
    _case, student = _warning_case()
    request = factory.get("/imha/onizleme/ogrenci/", {"nakil_tarihi": "2026-06-15"})
    response = views_purge.PurgeStudentPreviewView.as_view()(request, student_id=student.pk)
    assert response.status_code == 200
    body = _json(response)
    assert body["purge_deadline"] == "2026-06-22"
    assert body["student_name"] == student.full_name


def test_api_tutanak_ve_uygula_zinciri(factory: APIRequestFactory) -> None:
    _setup_school()
    case, _student = _warning_case()

    tutanak = views_purge.PurgeRecordView.as_view()(
        factory.post("/imha/tutanak/", {"case_ids": [case.pk], "onay": True}, format="json")
    )
    assert tutanak.status_code == 200
    token = tutanak["X-Imha-Token"]
    assert token

    uygula = views_purge.PurgeExecuteView.as_view()(
        factory.post("/imha/uygula/", {"token": token, "onay": True}, format="json")
    )
    assert uygula.status_code == 200
    assert _json(uygula)["purged_cases"] == 1
    assert not DisciplineCase.all_objects.filter(pk=case.pk).exists()


def test_api_uygula_onaysiz_400(factory: APIRequestFactory) -> None:
    _setup_school()
    case, _student = _warning_case()
    tutanak = views_purge.PurgeRecordView.as_view()(
        factory.post("/imha/tutanak/", {"case_ids": [case.pk], "onay": True}, format="json")
    )
    response = views_purge.PurgeExecuteView.as_view()(
        factory.post(
            "/imha/uygula/", {"token": tutanak["X-Imha-Token"], "onay": False}, format="json"
        )
    )
    assert response.status_code == 400
    assert DisciplineCase.objects.filter(pk=case.pk).exists()


def test_api_tutanak_dal_b_400(factory: APIRequestFactory) -> None:
    _setup_school()
    case, _s = _committee_case()
    response = views_purge.PurgeRecordView.as_view()(
        factory.post("/imha/tutanak/", {"case_ids": [case.pk], "onay": True}, format="json")
    )
    assert response.status_code == 400
