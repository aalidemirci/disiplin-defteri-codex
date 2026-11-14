"""14.11.2026 kullanıcı kararları — "kurallar" grubu: S4, S9, S10.

- S4 (md. 175): tatil günü başlayan tedbirin iş günleri izleyen İLK İŞ GÜNÜNDEN sayılır;
  girilen tarih karar günü kalır, md. 175/2'deki 3 iş günü ondan sayılır.
- S9 (md. 169/3): "ceza verilmesine yer olmadığı" kararı tebliğ edildikten sonra itiraz
  süresi ve kapanış tamponu beklenmeden dosya kapatılabilir.
- S10 (md. 157/7-e): aşama atlama override'ı ile "daha önce ceza/uyarı almış öğrenciye
  yazılı uyarı" engelinin aşılması iki AYRI işaret ve iki AYRI gerekçe ister.

Tarihler: Mayıs 2026 — 18 Pzt, 19 Sal, 20 Çar, 21 Per, 22 Cum, 23 Cmt, 24 Paz, 25 Pzt,
26 Sal, 27 Çar, 28 Per, 29 Cum; 1 Haziran Pzt.
"""

from __future__ import annotations

from datetime import date
from io import BytesIO
from typing import Any

import pytest
from pypdf import PdfReader
from rest_framework.test import APIClient

from apps.disiplin import deadlines, selectors, services
from apps.disiplin import discipline_periods as dp
from apps.disiplin import documents as doc_engine
from apps.disiplin.models import (
    CaseStage,
    DisciplineCase,
    DocumentType,
    PenaltyType,
    PrincipalDecision,
)
from apps.disiplin.tests.factories import SchoolYearFactory, StudentFactory, approve, decide
from apps.okul.models import Holiday

pytestmark = pytest.mark.django_db

FRI = date(2026, 5, 22)
SAT = date(2026, 5, 23)
SUN = date(2026, 5, 24)
MON = date(2026, 5, 25)
TUE = date(2026, 5, 26)
WED = date(2026, 5, 27)


def _case(*student_ids: int) -> DisciplineCase:
    SchoolYearFactory()
    ids = list(student_ids) or [StudentFactory().pk]
    return services.create_case(
        petition_date=date(2026, 5, 18),
        petitioner_name="İdare",
        petitioner_role="IDARE",
        summary="Sınıf içinde uygunsuz davranış.",
        student_ids=ids,
    )


def _committee_case(*student_ids: int) -> DisciplineCase:
    """Kurula sevkli (Dal B) dosya — rehberlik aşama atlamasıyla."""
    case = _case(*student_ids)
    services.add_event(
        case,
        CaseStage.DECIDED,
        date(2026, 5, 19),
        override=True,
        override_reason="Rehberlik atlandı.",
        principal_decisions=[PrincipalDecision.DISCIPLINE_COMMITTEE],
    )
    case.refresh_from_db()
    return case


def _sid(case: DisciplineCase) -> int:
    return int(case.case_students.values_list("student_id", flat=True)[0])


def _pdf_text(pdf_bytes: bytes) -> str:
    reader = PdfReader(BytesIO(pdf_bytes))
    return " ".join(" ".join((page.extract_text() or "").split()) for page in reader.pages)


def _doc_text(case: DisciplineCase, document_type: str, **kwargs: Any) -> str:
    pdf_bytes, _ = doc_engine.generate_document(
        case,
        document_type=document_type,
        generated_on=date(2026, 5, 25),
        student_id=_sid(case),
        log=False,
        **kwargs,
    )
    return _pdf_text(pdf_bytes)


# ---------------------------------------------------------------------------
# S4 — tedbir süresi izleyen ilk iş gününden sayılır (md. 175/1)
# ---------------------------------------------------------------------------
def test_s4_saf_tatil_gunu_baslayan_tedbir_ilk_is_gununden_sayilir() -> None:
    # Cumartesi başlangıç + 3 iş günü → pazartesi, salı, çarşamba.
    assert dp.precaution_end_date(SAT, 3) == WED
    assert dp.precaution_end_date(SUN, 3) == WED
    # 1 iş günü → yalnız izleyen ilk iş günü (cumartesinin kendisi DEĞİL).
    assert dp.precaution_end_date(SAT, 1) == MON


def test_s4_saf_is_gunu_baslangicinda_davranis_ayni() -> None:
    assert dp.precaution_end_date(MON, 1) == MON
    assert dp.precaution_end_date(MON, 3) == WED
    assert dp.precaution_end_date(FRI, 3) == TUE  # Cum, Pzt, Sal


def test_s4_saf_yuklem_enjeksiyonu_resmi_tatili_de_atlar() -> None:
    """İlk iş günü `is_working_day` yüklemiyle aranır: pazartesi resmî tatilse salıdan sayılır."""

    def monday_off(day: date) -> bool:
        return day.weekday() < 5 and day != MON

    assert dp.precaution_end_date(SAT, 2, is_working_day=monday_off) == WED  # Sal, Çar
    assert dp.precaution_end_date(MON, 1, is_working_day=monday_off) == TUE


def test_s4_serviste_cumartesi_tedbiri_carsamba_biter_karar_gunu_kalir() -> None:
    case = _committee_case()
    p = services.create_precaution(case, student_id=_sid(case), start_date=SAT, requested_days=3)
    assert p.start_date == SAT  # girilen tarih karar günü olarak kalır
    assert p.end_date == WED  # Pzt, Sal, Çar
    # md. 175/2: işleme başlama süresi KARAR gününden sayılır (Pzt, Sal, Çar).
    assert p.process_start_deadline == WED


def test_s4_serviste_resmi_tatilde_baslayan_tedbir() -> None:
    case = _committee_case()
    Holiday.objects.create(name="Deneme tatili", start_date=FRI, end_date=FRI)
    p = services.create_precaution(case, student_id=_sid(case), start_date=FRI, requested_days=2)
    assert p.start_date == FRI
    assert p.end_date == TUE  # Pzt, Sal
    assert p.process_start_deadline == WED  # karar günü Cum → Pzt, Sal, Çar


def test_s4_serviste_is_gunu_baslangici_degismez() -> None:
    case = _committee_case()
    p = services.create_precaution(case, student_id=_sid(case), start_date=FRI, requested_days=3)
    assert p.end_date == TUE  # Cum (1. gün), Pzt, Sal
    assert p.process_start_deadline == WED


def test_s4_uzatma_ayni_kurala_uyar() -> None:
    """Uzatma mevcut bitişi izleyen iş günlerinden sayılır; tatil günü hiç sayılmaz."""
    case = _committee_case()
    p = services.create_precaution(case, student_id=_sid(case), start_date=SAT, requested_days=1)
    assert p.end_date == MON
    services.extend_precaution(p, additional_days=2, mne_notified=True)
    p.refresh_from_db()
    assert p.end_date == WED  # Sal, Çar
    assert p.requested_days == 3


def test_s4_tedbir_bildirimi_ve_mem_yazisi_yeni_bitisi_basar() -> None:
    case = _committee_case()
    services.create_precaution(case, student_id=_sid(case), start_date=SAT, requested_days=3)
    notice = _doc_text(case, DocumentType.PRECAUTION_NOTICE)
    assert "23.05.2026" in notice  # karar/başlangıç günü
    assert "Tedbir Bitiş Günü 27.05.2026" in notice
    assert "26.05.2026" not in notice  # eski sayım (Cmt 1. gün → salı) basılmaz
    mem = _doc_text(case, DocumentType.PRECAUTION_MEM_LETTER, variant="info")
    assert "son gün 27.05.2026" in mem


def test_s4_is_gunu_baslangicinda_belge_degismez() -> None:
    case = _committee_case()
    services.create_precaution(case, student_id=_sid(case), start_date=FRI, requested_days=3)
    notice = _doc_text(case, DocumentType.PRECAUTION_NOTICE)
    assert "Tedbir Bitiş Günü 26.05.2026" in notice


# ---------------------------------------------------------------------------
# S9 — cezasız karar tebliğden sonra süre beklemeden kapanır
# ---------------------------------------------------------------------------
def _decide(case: DisciplineCase, student_id: int, penalty_type: str) -> Any:
    return decide(case, student_id=student_id, penalty_type=penalty_type, decision_date=FRI)


def test_s9_cezasiz_karar_tebligden_sonra_hemen_kapanir() -> None:
    case = _committee_case()
    d = _decide(case, _sid(case), PenaltyType.NO_PENALTY)
    approve(d)
    services.notify_decision(d, notified_on=FRI)
    # İtiraz son günü (29.05) ve tampon (05.06) BEKLENMEZ: tebliğ günü uygundur.
    assert selectors.close_eligibility_details(case, today=FRI) == (True, None, "")
    services.close_case(case)
    case.refresh_from_db()
    assert case.current_stage == CaseStage.CLOSED


def test_s9_tebligsiz_cezasiz_karar_kapanisi_acmaz() -> None:
    case = _committee_case()
    d = _decide(case, _sid(case), PenaltyType.NO_PENALTY)
    approve(d)
    eligible, eligible_on, reason = selectors.close_eligibility_details(
        case, today=date(2026, 7, 1)
    )
    assert (eligible, eligible_on) == (False, None)
    assert "tebliğ" in reason
    with pytest.raises(ValueError, match="tebliğ"):
        services.close_case(case)


def test_s9_onaysiz_cezasiz_karar_kapanisi_acmaz() -> None:
    """Onay şartı KALDIRILMADI: karar "tebliğden sonra" der, tebliğ de onaysız yapılamaz."""
    case = _committee_case()
    _decide(case, _sid(case), PenaltyType.NO_PENALTY)
    eligible, _on, reason = selectors.close_eligibility_details(case, today=date(2026, 7, 1))
    assert eligible is False
    assert "onaylanmadı" in reason


def test_s9_md197_askisindaki_cezasiz_karar_kapanisi_acmaz() -> None:
    case = _committee_case()
    d = _decide(case, _sid(case), PenaltyType.NO_PENALTY)
    services.record_principal_review(
        d, action="RETURN", reason="Dosya eksik incelenmiş.", decided_on=FRI
    )
    eligible, _on, reason = selectors.close_eligibility_details(case, today=date(2026, 7, 1))
    assert eligible is False
    assert "müdür incelemesinde" in reason


def test_s9_cezali_kararda_sureler_eskisi_gibi_beklenir() -> None:
    case = _committee_case()
    d = _decide(case, _sid(case), PenaltyType.REPRIMAND)
    approve(d)
    services.notify_decision(d, notified_on=FRI)
    # İtiraz son günü 29.05 + 5 iş günü tampon = 05.06.2026.
    eligible, eligible_on, reason = selectors.close_eligibility_details(
        case, today=date(2026, 6, 1)
    )
    assert (eligible, eligible_on) == (False, date(2026, 6, 5))
    assert "tampon" in reason


def test_s9_cok_ogrencili_dosyada_kural_ogrenci_bazinda() -> None:
    a, b = StudentFactory().pk, StudentFactory().pk
    case = _committee_case(a, b)
    cezasiz = _decide(case, a, PenaltyType.NO_PENALTY)
    cezali = _decide(case, b, PenaltyType.REPRIMAND)
    approve(cezasiz)
    services.notify_decision(cezasiz, notified_on=FRI)
    # Cezalı karar tebliğsiz → dosya kapanmaz.
    assert selectors.close_eligible(case, today=date(2026, 7, 1)) == (False, None)
    approve(cezali)
    services.notify_decision(cezali, notified_on=FRI)
    # Cezalı öğrenci için itiraz süresi + tampon beklenir (05.06); cezasız karar tarih eklemez.
    assert selectors.close_eligible(case, today=date(2026, 6, 4)) == (False, date(2026, 6, 5))
    services.confirm_e_school_entry(cezali, processed_on=date(2026, 6, 5))
    assert selectors.close_eligible(case, today=date(2026, 6, 5)) == (True, date(2026, 6, 5))


def test_s9_karari_girilmemis_ogrenci_varken_cezasiz_karar_dosyayi_kapatmaz() -> None:
    """Gözden geçirme bulgusu: A cezasız + tebliğli, B'nin kararı henüz girilmemiş."""
    a, b = StudentFactory().pk, StudentFactory().pk
    case = _committee_case(a, b)
    cezasiz = _decide(case, a, PenaltyType.NO_PENALTY)
    approve(cezasiz)
    services.notify_decision(cezasiz, notified_on=FRI)

    uygun, tarih, neden = selectors.close_eligibility_details(case, today=FRI)

    assert (uygun, tarih) == (False, None)
    assert "her öğrenci için karar" in neden
    # B'nin kararı da cezasız girilip tebliğ edilince dosya kapanabilir.
    ikinci = _decide(case, b, PenaltyType.NO_PENALTY)
    approve(ikinci)
    services.notify_decision(ikinci, notified_on=FRI)
    assert selectors.close_eligibility_details(case, today=FRI) == (True, None, "")


def test_s9_cezali_karar_bekleyen_itirazla_bloke() -> None:
    a, b = StudentFactory().pk, StudentFactory().pk
    case = _committee_case(a, b)
    cezasiz = _decide(case, a, PenaltyType.NO_PENALTY)
    cezali = _decide(case, b, PenaltyType.REPRIMAND)
    for d in (cezasiz, cezali):
        approve(d)
        services.notify_decision(d, notified_on=FRI)
    services.file_appeal(cezali, filed_on=MON, filed_by_role="PARENT")
    eligible, _on, reason = selectors.close_eligibility_details(case, today=date(2026, 7, 1))
    assert eligible is False
    assert "İtiraz incelemesi" in reason


def test_s9_panel_kapanisa_hazir_satiri_cezasiz_karari_dogru_anlatir() -> None:
    case = _committee_case()
    d = _decide(case, _sid(case), PenaltyType.NO_PENALTY)
    approve(d)
    services.notify_decision(d, notified_on=FRI)
    titles = [i.title for i in deadlines.collect_deadline_items(FRI) if i.case_no == case.case_no]
    assert "Dosya kapatılabilir (cezasız karar tebliğ edildi)" in titles
    assert not any("tampon doldu" in t for t in titles)


# ---------------------------------------------------------------------------
# S10 — aşama atlama override'ı md. 157/7-e engelini AŞMAZ
# ---------------------------------------------------------------------------
def _student_with_prior_warning() -> int:
    """Daha önce yazılı uyarıyla kapanmış (Dal A) dosyası olan öğrenci."""
    SchoolYearFactory()
    sid = int(StudentFactory().pk)
    first = _case(sid)
    services.add_event(
        first,
        CaseStage.DECIDED,
        date(2026, 5, 19),
        override=True,
        override_reason="Rehberlik atlandı.",
        principal_decisions=[PrincipalDecision.WRITTEN_WARNING],
    )
    return sid


def _warn(case: DisciplineCase, **kwargs: Any) -> Any:
    return services.add_event(
        case,
        CaseStage.DECIDED,
        date(2026, 5, 21),
        principal_decisions=[PrincipalDecision.WRITTEN_WARNING],
        **kwargs,
    )


def test_s10_asama_atlama_override_i_157_7e_engelini_asmaz() -> None:
    second = _case(_student_with_prior_warning())
    with pytest.raises(ValueError, match=r"md\. 157/7-e") as exc:
        _warn(second, override=True, override_reason="Rehberlik atlandı.")
    # İleti hangi engelin, nasıl aşılacağını söyler.
    assert "ayrı" in str(exc.value)
    assert "gerekçe" in str(exc.value)
    second.refresh_from_db()
    assert second.current_stage == CaseStage.PETITION


def test_s10_ayri_isaret_gerekcesiz_reddedilir() -> None:
    second = _case(_student_with_prior_warning())
    with pytest.raises(ValueError, match=r"md\. 157/7-e.*gerekçe"):
        _warn(
            second,
            override=True,
            override_reason="Rehberlik atlandı.",
            warning_block_override=True,
            warning_block_override_reason="  ",
        )


def test_s10_iki_ayri_gerekceyle_asilir_ve_izi_kalir() -> None:
    second = _case(_student_with_prior_warning())
    ev = _warn(
        second,
        override=True,
        override_reason="Rehberlik atlandı.",
        warning_block_override=True,
        warning_block_override_reason="Önceki uyarı farklı nitelikte bir davranış içindi.",
    )
    assert ev.is_override is True
    assert ev.override_reason == (
        "Rehberlik atlandı.\n\n"
        "md. 157/7-e engeli aşıldı: Önceki uyarı farklı nitelikte bir davranış içindi."
    )
    second.refresh_from_db()
    assert second.current_stage == CaseStage.CLOSED  # yalnız uyarı → otomatik kapanış


def test_s10_normal_yoldan_mudur_kararinda_da_ayri_onay_gerekir() -> None:
    second = _case(_student_with_prior_warning())
    services.add_event(second, CaseStage.GUIDANCE_REFERRED, date(2026, 5, 19))
    services.add_event(
        second, CaseStage.GUIDANCE_RETURNED, date(2026, 5, 20), guidance_outcome="rapor"
    )
    with pytest.raises(ValueError, match=r"md\. 157/7-e"):
        _warn(second)
    # Aşama atlama işareti burada anlamsızdır; engeli o da aşmaz.
    with pytest.raises(ValueError, match=r"md\. 157/7-e"):
        _warn(second, override=True, override_reason="Gerekçe.")
    ev = _warn(
        second,
        warning_block_override=True,
        warning_block_override_reason="Müdür takdiri: davranışlar arasında bağ yok.",
    )
    # Aşama atlanmadı; iz yalnız md. 157/7-e gerekçesini taşır.
    assert ev.is_override is True
    assert ev.override_reason == (
        "md. 157/7-e engeli aşıldı: Müdür takdiri: davranışlar arasında bağ yok."
    )


def test_s10_engel_yoksa_ayri_isaret_iz_birakmaz() -> None:
    """Geçmişi temiz öğrencide davranış AYNEN: işaret gönderilse de override izi doğmaz."""
    case = _case()
    services.add_event(case, CaseStage.GUIDANCE_REFERRED, date(2026, 5, 19))
    services.add_event(
        case, CaseStage.GUIDANCE_RETURNED, date(2026, 5, 20), guidance_outcome="rapor"
    )
    ev = _warn(case, warning_block_override=True, warning_block_override_reason="Gereksiz.")
    assert ev.is_override is False
    assert ev.override_reason == ""


def test_s10_gerekce_iz_alanina_sigmazsa_turkce_ret() -> None:
    """Şema değişmedi: iki gerekçe tek iz alanına (255 karakter) yazılır."""
    second = _case(_student_with_prior_warning())
    with pytest.raises(ValueError, match="255"):
        _warn(
            second,
            override=True,
            override_reason="A" * 150,
            warning_block_override=True,
            warning_block_override_reason="B" * 150,
        )


def test_s10_api_ayri_alanlari_tasir() -> None:
    sid = _student_with_prior_warning()
    second = _case(sid)
    client = APIClient()
    url = f"/api/v1/discipline/cases/{second.pk}/events/"
    body: dict[str, Any] = {
        "stage": CaseStage.DECIDED,
        "event_date": "2026-05-21",
        "override": True,
        "override_reason": "Rehberlik atlandı.",
        "principal_decisions": [PrincipalDecision.WRITTEN_WARNING],
    }
    resp = client.post(url, body, format="json")
    assert resp.status_code == 400, resp.content
    assert "md. 157/7-e" in resp.json()["message"]
    resp = client.post(
        url,
        {
            **body,
            "warning_block_override": True,
            "warning_block_override_reason": "Davranışlar arasında bağ yok.",
        },
        format="json",
    )
    assert resp.status_code == 201, resp.content
    assert (
        "md. 157/7-e engeli aşıldı: Davranışlar arasında bağ yok."
        in (resp.json()["override_reason"])
    )
