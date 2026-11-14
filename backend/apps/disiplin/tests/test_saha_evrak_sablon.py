"""Saha (Windows uçtan uca) denetimi — evrak ŞABLONU düzeltmeleri.

Her test sahada yeniden üretilmiş bir kusuru sabitler (bulgu numarası açıklamada).
Belge gerçekten üretilir (WeasyPrint) ve metni PDF'ten okunur; yalnız ızgara/sayfa
yapısı gereken yerde HTML ya da sayfa sayısı denetlenir. Şablon bağlamını kuran
mantığın testleri `test_saha_evrak_mantik.py`'dedir.
"""

from __future__ import annotations

from datetime import date
from io import BytesIO
from typing import Any

import pytest
from django.template import Context, Template
from django.template.loader import render_to_string
from pypdf import PdfReader

from apps.disiplin import documents as doc_engine
from apps.disiplin import honor_documents, services
from apps.disiplin.models import (
    CaseStage,
    DisciplineCase,
    DocumentType,
    HonorCriterion,
    HonorProposerRole,
    PenaltyType,
    PrincipalDecision,
)
from apps.disiplin.services.decisions import update_decision_narrative
from apps.disiplin.templatetags.tr_ekler import tamlayan_eki, tr_tamlayan, tr_tamlayan_eki
from apps.disiplin.tests.factories import (
    PersonnelFactory,
    SchoolYearFactory,
    StudentFactory,
    approve,
    committee_for,
    ensure_terms,
)
from apps.okul.models import SchoolTerm, SchoolYear
from apps.okul.services import setup as okul_setup

pytestmark = pytest.mark.django_db


def _pages(pdf_bytes: bytes) -> list[str]:
    reader = PdfReader(BytesIO(pdf_bytes))
    return [" ".join((page.extract_text() or "").split()) for page in reader.pages]


def _pdf_text(pdf_bytes: bytes) -> str:
    return " ".join(_pages(pdf_bytes))


def _case(*students: Any, district: str = "Çekmeköy") -> DisciplineCase:
    """Kurula sevkli (Dal B) dosya; ilçe adı kurulumdaki gibi karışık harfle."""
    SchoolYearFactory()
    okul_setup.update_school_config(
        fields={
            "school_name": "Deneme Anadolu Lisesi",
            "district": district,
            "principal_name": "ALİ ÖRNEK",
        }
    )
    case = services.create_case(
        petition_date=date(2026, 5, 18),
        petitioner_name="İdare",
        petitioner_role="IDARE",
        summary="Koridorda arkadaşına vurmak",
        student_ids=[s.pk for s in students],
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


def _pdf(case: DisciplineCase, document_type: str, **kwargs: Any) -> bytes:
    kwargs.setdefault("generated_on", date(2026, 5, 28))
    pdf, _record = doc_engine.generate_document(case, document_type=document_type, **kwargs)
    return pdf


def _appealed(
    *, filed_by_name: str = "Güler Şığın", district: str = "Çekmeköy", penalty_detail: str = ""
) -> tuple[DisciplineCase, Any, Any]:
    """Kınama → onay → tebliğ → veli itirazı (Form-18 üretilebilir durum)."""
    student = StudentFactory(first_name="IRAZ", last_name="ÇIĞ")
    case = _case(student, district=district)
    decision = services.record_decision(
        case,
        student_id=student.pk,
        penalty_type=PenaltyType.REPRIMAND,
        decision_date=date(2026, 5, 22),
        penalty_detail=penalty_detail,
    )
    approve(decision)
    services.notify_decision(decision, notified_on=date(2026, 5, 22))
    services.file_appeal(
        decision, filed_on=date(2026, 5, 25), filed_by_role="PARENT", filed_by_name=filed_by_name
    )
    return case, student, decision


# ---------------------------------------------------------------------------
# Bulgu 33, 48, 54, 60, 67 — ad sonrası tamlayan eki (ünlü uyumu + kaynaştırma)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("name", "expected"),
    [
        # Ünsüzle biten: yalnız ünlü + n.
        ("Deniz Aydın", "Deniz Aydın'ın"),
        ("Güler Şığın", "Güler Şığın'ın"),
        ("Barış Çelik", "Barış Çelik'in"),
        ("İsmail Öztürk", "İsmail Öztürk'ün"),
        ("Ali Uçar", "Ali Uçar'ın"),
        ("Ayşe Gül", "Ayşe Gül'ün"),
        ("Gülşen Şimşek", "Gülşen Şimşek'in"),
        ("Ömer Çığ", "Ömer Çığ'ın"),
        ("Şule Şahin", "Şule Şahin'in"),
        ("Hüseyin Özışık", "Hüseyin Özışık'ın"),
        ("Çağrı Işıkgöz", "Çağrı Işıkgöz'ün"),
        ("Mert Uysal", "Mert Uysal'ın"),
        ("Can Koç", "Can Koç'un"),
        ("Elif Topuz", "Elif Topuz'un"),
        ("Su Yörük", "Su Yörük'ün"),
        # Ünlüyle biten: n kaynaştırması.
        ("İsmail Çınar Iğdırlı", "İsmail Çınar Iğdırlı'nın"),
        ("Ece Kaya", "Ece Kaya'nın"),
        ("Zeynep Arı", "Zeynep Arı'nın"),
        ("Ümran Ünlü", "Ümran Ünlü'nün"),
        ("Uğur İğci", "Uğur İğci'nin"),
        ("Ahmet Koru", "Ahmet Koru'nun"),
        ("Selin Tekbaşoğlu", "Selin Tekbaşoğlu'nun"),
        ("Emine Türe", "Emine Türe'nin"),
        ("Nur Gözcü", "Nur Gözcü'nün"),
        # Tek sözcük ve boşluk taşması.
        ("Kaya", "Kaya'nın"),
        ("  Deniz Aydın  ", "Deniz Aydın'ın"),
        # İnce l ile biten alıntı adlar (kapalı istisna kümesi).
        ("Mustafa Kemal", "Mustafa Kemal'in"),
        ("Ayşe Hilal", "Ayşe Hilal'in"),
        ("Hasan Bilal", "Hasan Bilal'in"),
        ("Ali Celal", "Ali Celal'in"),
        ("Ahmet Cemal", "Ahmet Cemal'in"),
        ("Ece Nihal", "Ece Nihal'in"),
        ("Selin Zuhal", "Selin Zuhal'in"),
        ("Nur Şevval", "Nur Şevval'in"),
        ("Ayşe İkbal", "Ayşe İkbal'in"),
        ("Elif Zülal", "Elif Zülal'in"),
        ("Ayşe Hayal", "Ayşe Hayal'in"),
        ("Fatma Visal", "Fatma Visal'in"),
        ("Mehmet İstiklal", "Mehmet İstiklal'in"),
        ("Ali İhtilal", "Ali İhtilal'in"),
        ("Nur Şefkat", "Nur Şefkat'in"),
        ("Yusuf Sadakat", "Yusuf Sadakat'in"),
        ("Müzeyyen Dikkat", "Müzeyyen Dikkat'in"),
        ("Hasan Saat", "Hasan Saat'in"),
        ("Ömer Kanaat", "Ömer Kanaat'in"),
        ("Zeynep Hakikat", "Zeynep Hakikat'in"),
        ("ELİF ZÜLAL", "ELİF ZÜLAL'İN"),
        ("Ahmet Resul", "Ahmet Resul'ün"),
        # Kalın kalanlar: istisna kümesine bilerek alınmadı (Türkçe kökenli / kalın okunan).
        ("Ayşe Meral", "Ayşe Meral'ın"),
        ("Ali Nihat", "Ali Nihat'ın"),
        ("Can Ferhat", "Can Ferhat'ın"),
        ("Su Hayat", "Su Hayat'ın"),
        ("Ece Kartal", "Ece Kartal'ın"),
        # Düzeltme işaretli ünlü yalın karşılığıyla.
        ("Hilâl Kâtip", "Hilâl Kâtip'in"),
    ],
)
def test_tamlayan_eki_unlu_uyumu_ve_kaynastirma(name: str, expected: str) -> None:
    assert tr_tamlayan(name) == expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        # Sicil adları büyük harfle tutulur: ek de büyük, Türkçe ı/İ ayrımıyla.
        ("İSMAİL ŞIĞIN", "İSMAİL ŞIĞIN'IN"),
        ("BARIŞ ÇELİK", "BARIŞ ÇELİK'İN"),
        ("IRAZ IĞDIRLI", "IRAZ IĞDIRLI'NIN"),
        ("UĞUR İĞCİ", "UĞUR İĞCİ'NİN"),
        ("ÖMER ÖZTÜRK", "ÖMER ÖZTÜRK'ÜN"),
        ("ECE KORU", "ECE KORU'NUN"),
        # "I" Türkçede kalın ünlüdür (ı); çıplak lower() onu "i" sanar.
        ("Ali Işık", "Ali Işık'ın"),
        ("ALİ IŞIK", "ALİ IŞIK'IN"),
        ("Can Ilgaz", "Can Ilgaz'ın"),
        # "İ" ince ünlüdür.
        ("Ayşe İnci", "Ayşe İnci'nin"),
    ],
)
def test_tamlayan_eki_turkce_i_ayrimi_ve_buyuk_harf(name: str, expected: str) -> None:
    assert tr_tamlayan(name) == expected


def test_tamlayan_eki_sinir_durumlari() -> None:
    assert tr_tamlayan("") == ""
    assert tr_tamlayan(None) == ""
    assert tr_tamlayan_eki("") == ""
    assert tr_tamlayan_eki("Deniz Aydın") == "'ın"
    assert tamlayan_eki("Ece Kaya") == "'nın"
    # Kısaltma noktası eki bozmaz; ünlüsüz kısaltma harf adıyla okunur.
    assert tr_tamlayan("Ali Yılmaz.") == "Ali Yılmaz.'ın"
    assert tr_tamlayan("Ali K.") == "Ali K.'nin"
    assert tr_tamlayan("TBMM") == "TBMM'NİN"
    # Tek harfli son sözcük (kısaltılmış soyadı) büyük harfli ad sayılmaz.
    assert tr_tamlayan("Ali K") == "Ali K'nin"


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        # Parantezli son bölüm ekin ARKASINA alınır; ek asıl ada göre üretilir.
        ("Ayşe Kaya (anne)", "Ayşe Kaya'nın (anne)"),
        ("Güler Şığın (Veli)", "Güler Şığın'ın (Veli)"),
        ("Mustafa Kemal (baba) (vasi)", "Mustafa Kemal'in (baba) (vasi)"),
        ("Ece Koru (anne", "Ece Koru'nun (anne"),  # kapanmamış parantez
        ("Ayşe Kaya(anne)", "Ayşe Kaya'nın (anne)"),
        # Sondaki noktalama (nokta hariç) atılır.
        ("Ömer Halis Demir,", "Ömer Halis Demir'in"),
        ("Barış Çelik ;", "Barış Çelik'in"),
        ("Deniz Aydın -", "Deniz Aydın'ın"),
        ("Ali Uçar, (baba)", "Ali Uçar'ın (baba)"),
        # Asıl adın sonu harf değil: ek ÜRETİLMEZ, eksiz kalıp basılır.
        ("Ali Kaya 2", "Ali Kaya 2 adlı kişinin"),
        ("Veli Can*", "Veli Can* adlı kişinin"),
        ("Ali Kaya 2 (vasi)", "Ali Kaya 2 adlı kişinin (vasi)"),
        # Adda hiç harf yok: boş döner (şablon kendi yedek kalıbını basar).
        ("—", ""),
        ("...", ""),
        ("12345", ""),
        ("(anne)", ""),
    ],
)
def test_tamlayan_ad_disi_son_bolum_ekten_once_ayrilir(name: str, expected: str) -> None:
    """Gözden geçirme E5 — "Ayşe Kaya (anne)'nin", "Demir,'in" gibi çıktılar üretilmez."""
    assert tr_tamlayan(name) == expected


def test_tamlayan_eki_harfle_bitmeyen_adda_ek_uretmez() -> None:
    assert tamlayan_eki("Ayşe Kaya (anne)") == "'nın"
    assert tamlayan_eki("Ömer Halis Demir,") == "'in"
    for name in ("Ali Kaya 2", "Veli Can*", "—", "12345", "(anne)", "   "):
        assert tamlayan_eki(name) == ""
        assert tr_tamlayan_eki(name) == ""


def test_tamlayan_suzgeci_sablonda_yuklenir() -> None:
    out = Template(
        "{% load tr_ekler %}{{ ad|tr_tamlayan }} / <b>{{ ad }}</b>{{ ad|tr_tamlayan_eki }}"
    ).render(Context({"ad": "Çağrı Işıkgöz"}))
    assert out == "Çağrı Işıkgöz&#x27;ün / <b>Çağrı Işıkgöz</b>&#x27;ün"


@pytest.mark.parametrize(
    ("filed_by_name", "expected"),
    [
        ("Güler Şığın", "b) Güler Şığın'ın 25.05.2026 tarihli itiraz dilekçesi"),
        ("İsmail Öztürk", "b) İsmail Öztürk'ün 25.05.2026 tarihli itiraz dilekçesi"),
        ("Uğur İğci", "b) Uğur İğci'nin 25.05.2026 tarihli itiraz dilekçesi"),
        ("Ece Kaya", "b) Ece Kaya'nın 25.05.2026 tarihli itiraz dilekçesi"),
        # Ad girilmemişse köşeli yer tutucu değil, eksiz kalıp.
        ("", "b) İtiraz edenin 25.05.2026 tarihli itiraz dilekçesi"),
        # Gözden geçirme E5: ad dışı son bölüm cümleyi bozmaz.
        ("Ayşe Kaya (anne)", "b) Ayşe Kaya'nın (anne) 25.05.2026 tarihli itiraz dilekçesi"),
        ("Ömer Halis Demir,", "b) Ömer Halis Demir'in 25.05.2026 tarihli itiraz dilekçesi"),
        ("—", "b) İtiraz edenin 25.05.2026 tarihli itiraz dilekçesi"),
        ("Veli Can 2", "b) Veli Can 2 adlı kişinin 25.05.2026 tarihli itiraz dilekçesi"),
    ],
)
def test_form18_ilgi_satirinda_itiraz_edenin_eki(filed_by_name: str, expected: str) -> None:
    case, student, _decision = _appealed(filed_by_name=filed_by_name)
    text = _pdf_text(_pdf(case, DocumentType.APPEAL_LETTER, student_id=student.pk))
    assert expected in text
    assert "[Ad Soyad]" not in text


# ---------------------------------------------------------------------------
# Bulgu 20 (+68 muhatap) — yer tutucu resmî yazıya basılmaz; muhatap ilçe adıyla
# ---------------------------------------------------------------------------
def test_form18_gerekce_bosken_noktali_satir_basilir() -> None:
    """Gözden geçirme E6: önceki tur boş gerekçe yerine dosya özetini (`case.summary`)
    cümle ortasına gömüyordu — özet serbest, çoğu kez çok cümleli bir alandır ve resmî
    cümleyi bozar. Eski test (`…_dosya_ozeti_basilir`) bu yüzden değiştirildi: noktalı
    satır basılır, elle doldurulur."""
    case, student, _decision = _appealed(penalty_detail="")
    text = _pdf_text(_pdf(case, DocumentType.APPEAL_LETTER, student_id=student.pk))
    assert "[disipline konu olan olayın kısa özeti]" not in text
    assert "hakkında, …………………………………… nedeniyle İlgi (a) karar ile" in text
    assert "Koridorda arkadaşına vurmak" not in text


def test_form18_ceza_ayrintisi_doluyken_o_basilir() -> None:
    case, student, _decision = _appealed(penalty_detail="Derste kopya çekmek")
    text = _pdf_text(_pdf(case, DocumentType.APPEAL_LETTER, student_id=student.pk))
    assert "hakkında, Derste kopya çekmek nedeniyle" in text


def test_form18_muhatap_ilce_adi_turkce_buyuk_harfle() -> None:
    case, student, _decision = _appealed(district="Çekmeköy")
    text = _pdf_text(_pdf(case, DocumentType.APPEAL_LETTER, student_id=student.pk))
    assert "ÇEKMEKÖY İLÇE MİLLÎ EĞİTİM MÜDÜRLÜĞÜNE" in text
    assert "İL / İLÇE" not in text


def test_muhatap_ilce_adinda_turkce_i_dogru_buyur() -> None:
    """Çıplak upper() "Sincan" için "SINCAN" basardı (CLAUDE.md §7.2)."""
    case, student, _decision = _appealed(district="Sincan")
    text = _pdf_text(_pdf(case, DocumentType.APPEAL_LETTER, student_id=student.pk))
    assert "SİNCAN İLÇE MİLLÎ EĞİTİM MÜDÜRLÜĞÜNE" in text


def test_form18_ilce_kayitli_degilse_muhatap_elle_doldurulur() -> None:
    case, student, _decision = _appealed(district="")
    text = _pdf_text(_pdf(case, DocumentType.APPEAL_LETTER, student_id=student.pk))
    assert "……………… İL / İLÇE MİLLÎ EĞİTİM MÜDÜRLÜĞÜNE" in text


def _school_change_case(district: str = "Çekmeköy") -> tuple[DisciplineCase, Any]:
    student = StudentFactory(first_name="IRAZ", last_name="ÇIĞ")
    case = _case(student, district=district)
    services.record_decision(
        case,
        student_id=student.pk,
        penalty_type=PenaltyType.SCHOOL_CHANGE,
        decision_date=date(2026, 5, 22),
    )
    return case, student


def test_onaya_sevk_yazisinda_yer_tutucu_yok_ve_muhatap_dolu() -> None:
    case, student = _school_change_case()
    text = _pdf_text(_pdf(case, DocumentType.APPROVAL_REQUEST_LETTER, student_id=student.pk))
    assert "[disipline konu olan olayın kısa özeti]" not in text
    # Gözden geçirme E6: boş gerekçede dosya özeti cümleye gömülmez, noktalı satır basılır.
    assert "hakkında, …………………………………… nedeniyle Okul Öğrenci Ödül" in text
    assert "Koridorda arkadaşına vurmak" not in text
    assert "ÇEKMEKÖY İLÇE MİLLÎ EĞİTİM MÜDÜRLÜĞÜNE" in text
    assert "……………… İLÇE" not in text


def test_onaya_sevk_yazisinda_ilce_yoksa_muhatap_noktali_kalir() -> None:
    case, student = _school_change_case(district="")
    text = _pdf_text(_pdf(case, DocumentType.APPROVAL_REQUEST_LETTER, student_id=student.pk))
    assert "……………… İLÇE MİLLÎ EĞİTİM MÜDÜRLÜĞÜNE" in text


def test_onaya_sevk_yazisinda_gerekce_doluyken_o_basilir() -> None:
    student = StudentFactory(first_name="IRAZ", last_name="ÇIĞ")
    case = _case(student)
    services.record_decision(
        case,
        student_id=student.pk,
        penalty_type=PenaltyType.SCHOOL_CHANGE,
        decision_date=date(2026, 5, 22),
        penalty_detail="Derste kopya çekmek",
    )
    text = _pdf_text(_pdf(case, DocumentType.APPROVAL_REQUEST_LETTER, student_id=student.pk))
    assert "hakkında, Derste kopya çekmek nedeniyle" in text


def _precaution_case(district: str = "Çekmeköy") -> tuple[DisciplineCase, Any, Any]:
    student = StudentFactory()
    case = _case(student, district=district)
    precaution = services.create_precaution(
        case, student_id=student.pk, start_date=date(2026, 5, 20), requested_days=10
    )
    return case, student, precaution


@pytest.mark.parametrize("variant", ["info", "extension"])
def test_mem_tedbir_yazilarinda_muhatap_ilce_adiyla(variant: str) -> None:
    case, student, _precaution = _precaution_case()
    text = _pdf_text(
        _pdf(case, DocumentType.PRECAUTION_MEM_LETTER, student_id=student.pk, variant=variant)
    )
    assert "ÇEKMEKÖY İLÇE MİLLÎ EĞİTİM MÜDÜRLÜĞÜNE" in text


def test_ilceye_gonderme_yazisinda_muhatap_dolu_iade_yazisi_tarihi_kayittan() -> None:
    """Bulgu 68 (muhatap) + kullanıcı kararı 14.11.2026 — S11b (eski adı `…_tarihi_noktali`):
    İlgi (b) iade yazısı tarihi kayıttaki İADE tarihidir (`first_returned_at`).

    Kütükteki iade yazısının üretim tarihi yine kaynak değildir: aşağıda yazı iade
    gününden FARKLI bir tarihle üretilir, İlgi (b) yine iade gününü basar."""
    student = StudentFactory()
    case = _case(student)
    decision = services.record_decision(
        case,
        student_id=student.pk,
        penalty_type=PenaltyType.REPRIMAND,
        decision_date=date(2026, 5, 20),
    )
    services.record_principal_review(
        decision, action="RETURN", reason="Ceza hafif.", decided_on=date(2026, 5, 21)
    )
    _pdf(case, DocumentType.RETURN_LETTER, student_id=student.pk, generated_on=date(2026, 5, 22))
    services.record_principal_review(
        decision, action="REFER", reason="Kurul ısrar etti.", decided_on=date(2026, 5, 26)
    )
    text = _pdf_text(
        _pdf(
            case,
            DocumentType.DISTRICT_REFERRAL_LETTER,
            student_id=student.pk,
            generated_on=date(2026, 5, 26),
        )
    )
    assert "ÇEKMEKÖY İLÇE MİLLÎ EĞİTİM MÜDÜRLÜĞÜNE" in text
    assert "b) Müdürlüğümüzün 21.05.2026 tarihli kurula iade yazısı" in text
    assert "22.05.2026" not in text


# ---------------------------------------------------------------------------
# Bulgu 66 — uzatılmış tedbirde MEM bilgilendirmesi md. 175/1 ile 175/2'yi ayırır
# ---------------------------------------------------------------------------
def test_mem_bilgilendirme_uzatilmamis_tedbirde_md175_1() -> None:
    case, student, _precaution = _precaution_case()
    text = _pdf_text(
        _pdf(case, DocumentType.PRECAUTION_MEM_LETTER, student_id=student.pk, variant="info")
    )
    assert "175. maddesinin 1. fıkrası uyarınca öğrenci 20.05.2026 tarihinden itibaren" in text
    assert "10 iş günü (son gün" in text
    assert "uzatılmıştır" not in text


def test_mem_bilgilendirme_uzatilmis_tedbirde_toplami_md175_1e_baglamaz() -> None:
    """md. 175/1 "on iş gününü geçmemek kaydıyla"; fazlası md. 175/2 uzatmasıdır."""
    case, student, precaution = _precaution_case()
    services.extend_precaution(precaution, additional_days=10, mne_notified=True)
    services.extend_precaution(precaution, additional_days=5, mne_notified=True)
    precaution.refresh_from_db()
    text = _pdf_text(
        _pdf(case, DocumentType.PRECAUTION_MEM_LETTER, student_id=student.pk, variant="info")
    )
    assert "tarihinden itibaren 25 iş günü" not in text
    assert (
        "tedbir kararı aynı maddenin 2. fıkrası uyarınca Millî Eğitim Müdürünün onayıyla "
        "2 kez uzatılmıştır"
    ) in text
    assert "uzatmalarla birlikte toplam 25 iş günü" in text
    assert f"son gün {precaution.end_date:%d.%m.%Y}" in text


# ---------------------------------------------------------------------------
# Bulgu 61, 72 — Form-15/17 olay tarihi kayıttan
# ---------------------------------------------------------------------------
def _suspension_case(*, incident: date | None) -> tuple[DisciplineCase, Any]:
    student = StudentFactory(guardian_name="Veli Örnek")
    case = _case(student)
    decision = services.record_decision(
        case,
        student_id=student.pk,
        penalty_type=PenaltyType.SHORT_TERM_SUSPENSION,
        suspension_days=3,
        decision_date=date(2026, 5, 22),
    )
    if incident is not None:
        update_decision_narrative(decision, fields={"incident_date": incident})
    approve(decision)
    services.notify_decision(decision, notified_on=date(2026, 5, 22))
    return case, student


def test_form15_olay_tarihi_kayittan_basilir() -> None:
    case, student = _suspension_case(incident=date(2026, 5, 15))
    text = _pdf_text(
        _pdf(case, DocumentType.PENALTY_NOTICE, student_id=student.pk, recipient="parent")
    )
    assert "hakkında 15.05.2026 tarihinde meydana gelen" in text
    assert "hakkında …/…/202… tarihinde" not in text


def test_form15_olay_tarihi_yoksa_noktali_kalir() -> None:
    case, student = _suspension_case(incident=None)
    text = _pdf_text(
        _pdf(case, DocumentType.PENALTY_NOTICE, student_id=student.pk, recipient="parent")
    )
    assert "hakkında …/…/202… tarihinde meydana gelen" in text


@pytest.mark.parametrize(
    ("incident", "expected"),
    [
        (date(2026, 5, 15), "hakkında 15.05.2026 tarihinde meydana gelen"),
        (None, "hakkında …/…/202… tarihinde meydana gelen"),
    ],
)
def test_form17_olay_tarihi_kayittan_basilir(incident: date | None, expected: str) -> None:
    """Form-17 şablonu doğrudan basılır (üretim kilidi — kesinleşme — burada konu değil)."""
    case, student = _suspension_case(incident=incident)
    context = doc_engine._penalty_days_notice_context(case, student)
    html = render_to_string("disiplin/documents/penalty_days_notice_parent.html", context)
    assert expected in " ".join(html.replace("<strong>", "").replace("</strong>", "").split())


# ---------------------------------------------------------------------------
# Bulgu 73 — cezasız kararın veli tebliğinde örnek şerh "ceza" demez
# ---------------------------------------------------------------------------
def test_cezasiz_kararin_veli_tebliginde_serh_ceza_demez() -> None:
    student = StudentFactory()
    case = _case(student)
    services.record_decision(
        case,
        student_id=student.pk,
        penalty_type=PenaltyType.NO_PENALTY,
        decision_date=date(2026, 5, 22),
    )
    text = _pdf_text(
        _pdf(case, DocumentType.PENALTY_NOTICE, student_id=student.pk, recipient="parent")
    )
    assert "VELİYE DİSİPLİN KURULU KARARI TEBLİĞİ" in text
    assert "verilen disiplin cezasına ilişkin" not in text
    assert "öğrenci hakkında verilen disiplin kurulu kararına ilişkin tebliğ" in text


def test_cezali_kararin_veli_tebliginde_serh_degismez() -> None:
    case, student = _suspension_case(incident=None)
    text = _pdf_text(
        _pdf(case, DocumentType.PENALTY_NOTICE, student_id=student.pk, recipient="parent")
    )
    assert "Velisi bulunduğum öğrenciye verilen disiplin cezasına ilişkin tebliğ" in text


# ---------------------------------------------------------------------------
# Bulgu 3, 22 — değişen ceza notu değiştirilebilir şablonlarda (Form-15, Form-18)
# ---------------------------------------------------------------------------
def _reduced_case() -> tuple[DisciplineCase, Any]:
    """5 gün uzaklaştırma → onay → tebliğ → itiraz → REDUCED (kınama)."""
    student = StudentFactory(guardian_name="Veli Örnek")
    case = _case(student)
    decision = services.record_decision(
        case,
        student_id=student.pk,
        penalty_type=PenaltyType.SHORT_TERM_SUSPENSION,
        suspension_days=5,
        decision_date=date(2026, 5, 22),
    )
    approve(decision)
    services.notify_decision(decision, notified_on=date(2026, 5, 22))
    appeal = services.file_appeal(
        decision, filed_on=date(2026, 5, 25), filed_by_role="PARENT", filed_by_name="Ece Kaya"
    )
    services.resolve_appeal(
        appeal,
        result="REDUCED",
        resulted_on=date(2026, 6, 3),
        new_penalty_type=PenaltyType.REPRIMAND,
    )
    return case, student


_CHANGE_NOTE = (
    'Okul Öğrenci Ödül ve Disiplin Kurulunun verdiği "Okuldan kısa süreli uzaklaştırma — '
    '5 gün" cezası, itiraz üzerine İlçe öğrenci disiplin kurulunca "Kınama" olarak '
    "değiştirilmiştir."
)


@pytest.mark.parametrize(
    ("document_type", "recipient"),
    [(DocumentType.APPEAL_LETTER, "student"), (DocumentType.PENALTY_NOTICE, "parent")],
)
def test_degisen_ceza_notu_form18_ve_form15te_basilir(document_type: str, recipient: str) -> None:
    case, student = _reduced_case()
    text = _pdf_text(
        _pdf(
            case,
            document_type,
            student_id=student.pk,
            recipient=recipient,
            generated_on=date(2026, 6, 5),
        )
    )
    assert _CHANGE_NOTE in text


def test_form15_degisen_cezada_yururlukteki_cezayi_teblig_eder() -> None:
    """Gözden geçirme E2 — veli tebliği yürürlükteki cezayı ("Kınama") basar; kurulun
    verdiği ceza yalnız not paragrafında, doğru yönle anlatılır."""
    case, student = _reduced_case()
    text = _pdf_text(
        _pdf(
            case,
            DocumentType.PENALTY_NOTICE,
            student_id=student.pk,
            recipient="parent",
            generated_on=date(2026, 6, 5),
        )
    )
    assert 'öğrencinize "Kınama" cezası verilmiştir' in text
    assert f"İşbu yazı ile tebliğ edilen ceza yürürlükteki cezadır. {_CHANGE_NOTE}" in text
    assert "(5 gün)" not in text


def test_degismemis_cezada_not_basilmaz() -> None:
    case, student, _decision = _appealed()
    text = _pdf_text(_pdf(case, DocumentType.APPEAL_LETTER, student_id=student.pk))
    assert "olarak değiştirilmiştir" not in text


# ---------------------------------------------------------------------------
# Bulgu 36 (Form-13 yazıyla gün) — önceki turun bağlamı şablonda
# ---------------------------------------------------------------------------
def test_form13_gun_sayisi_yaziyla() -> None:
    student = StudentFactory()
    case = _case(student)
    committee_for(SchoolYear.objects.get(is_active=True))
    services.create_extension(
        case, requested_days=5, reason="Tanıklar dinlenemedi.", decided_on=date(2026, 5, 25)
    )
    text = _pdf_text(_pdf(case, DocumentType.DEADLINE_EXTENSION, variant="petition"))
    assert "tarafıma 5 (beş) iş günü ek süre" in text
    assert "(……)" not in text


# ---------------------------------------------------------------------------
# Bulgu 77 — Onur Kurulu Teklif Tutanağında toplantı tarihi / no
# ---------------------------------------------------------------------------
def _honor_meeting(year: Any, **kwargs: Any) -> Any:
    ensure_terms(year)
    if "attendees" not in kwargs:
        kwargs["attendees"] = [
            {"person_name": "Onur Başkanı", "attendee_role": "VOTING_MEMBER", "is_chair": True},
            {"person_name": "Öğrenci Üye", "attendee_role": "VOTING_MEMBER", "is_chair": False},
        ]
    return services.create_council_meeting(
        school_year_id=year.pk, council_type="HONOR", meeting_date=date(2026, 5, 25), **kwargs
    )


def test_onur_teklif_tutanagi_toplanti_tarihi_ve_no() -> None:
    """Kullanıcı kararı 14.11.2026 — S3 (eski adı `…_sablonu_toplanti_satiri_basmaz`, tersine
    döndü): gözden geçirme E1 satırı OYS paritesi gerekçesiyle geri almıştı; kullanıcı şablonu
    istisna listesine aldı — toplantı tarihi ve defter numarası künyeye basılır (md. 183/b)."""
    year = SchoolYearFactory()
    board = services.create_honor_board(school_year_id=year.pk, chair_id=PersonnelFactory().pk)
    meeting = _honor_meeting(year)
    text = _pdf_text(honor_documents.render_recommendation_record([], board=board, meeting=meeting))
    assert f"Toplantı Tarihi / No 25.05.2026 / {meeting.meeting_no_display}" in text
    assert "Düzenlenme Tarihi" in text


def test_onur_teklif_tutanagi_toplantisiz_yolda_degismez() -> None:
    year = SchoolYearFactory()
    board = services.create_honor_board(school_year_id=year.pk, chair_id=PersonnelFactory().pk)
    text = _pdf_text(honor_documents.render_recommendation_record([], board=board))
    assert "Toplantı Tarihi / No" not in text
    assert "Düzenlenme Tarihi" in text


# ---------------------------------------------------------------------------
# Bulgu 79 — gündemli tutanakta üst bilgi "Karar Esası" maddelerle çelişmez
# ---------------------------------------------------------------------------
def _minutes_html(meeting: Any) -> str:
    return render_to_string(
        doc_engine.COUNCIL_MEETING_MINUTES_TEMPLATE, doc_engine._council_minutes_context(meeting)
    )


def _certificate(year: Any) -> Any:
    ensure_terms(year)
    services.create_honor_board(school_year_id=year.pk, chair_id=PersonnelFactory().pk)
    return services.propose_honor_certificate(
        student_id=StudentFactory().pk,
        proposer_role=HonorProposerRole.TEACHER,
        school_term_id=SchoolTerm.objects.get(school_year=year, sequence=2).pk,
        criteria=[HonorCriterion.ATTENDANCE],
    )


def test_gundemli_tutanakta_karar_esasi_maddelere_atif_yapar() -> None:
    year = SchoolYearFactory()
    certificate = _certificate(year)
    meeting = _honor_meeting(year)
    item = services.add_agenda_items(meeting, honor_certificate_ids=[certificate.pk])[0]
    services.decide_agenda_item(
        item,
        outcome="FAVORABLE",
        decision_basis="MAJORITY",
        dissent_note="Öğrenci Üye: etkinlik sayısı yetersiz.",
    )
    meeting.refresh_from_db()
    text = _pdf_text(doc_engine.render_council_meeting_minutes(meeting))
    assert "Karar Esası Oy birliği" not in text
    assert "Karar Esası Her gündem maddesinin karar esası kendi satırında" in text
    assert "Oy çoğunluğu" in text


def test_gundemsiz_tutanakta_karar_esasi_satiri_degismez() -> None:
    year = SchoolYearFactory()
    meeting = _honor_meeting(year, decision_text="Karar.", decision_basis="MAJORITY")
    text = _pdf_text(doc_engine.render_council_meeting_minutes(meeting))
    assert "Karar Esası Oy çoğunluğu" in text
    assert "kendi satırında" not in text


def test_gundemli_tutanakta_serbest_karar_varsa_genel_karar_esasi_kalir() -> None:
    """Genel KARAR bölümü basılıyorsa onun karar esası üst bilgide de durur."""
    year = SchoolYearFactory()
    certificate = _certificate(year)
    meeting = _honor_meeting(year, decision_text="Ayrıca gezi planlandı.")
    services.add_agenda_items(meeting, honor_certificate_ids=[certificate.pk])
    meeting.refresh_from_db()
    html = _minutes_html(meeting)
    assert '<td class="label">Karar Esası</td><td>Oy birliği</td>' in html


# ---------------------------------------------------------------------------
# Bulgu 5 — imza ızgarası satırlara bölünür (kalabalık Onur Genel Kurulu)
# ---------------------------------------------------------------------------
def _assembly_meeting(count: int) -> Any:
    year = SchoolYearFactory()
    attendees: list[dict[str, Any]] = [
        {"person_name": "Tuğçe Karagöz", "attendee_role": "VOTING_MEMBER", "is_chair": True}
    ]
    attendees += [
        {"person_name": f"Temsilci Öğrenci {i:02d}", "attendee_role": "VOTING_MEMBER"}
        for i in range(1, count)
    ]
    return _honor_meeting(year, attendees=attendees, honor_meeting_kind="GENERAL_ASSEMBLY")


def _signature_grid(html: str) -> str:
    return html.split('<table class="sig-grid"', 1)[1].split("</table>", 1)[0]


def _signature_rows(html: str) -> list[int]:
    """İmza ızgarasının her satırındaki DOLU imza hanesi sayısı."""
    rows = _signature_grid(html).split("<tr>")[1:]
    return [row.count('<div class="line"></div>') for row in rows]


def test_kalabalik_kurulda_imza_izgarasi_satirlara_bolunur() -> None:
    html = _minutes_html(_assembly_meeting(25))
    assert _signature_rows(html) == [5, 5, 5, 5, 5]
    grid = _signature_grid(html)
    # Başkan ilk hanede; son temsilci de ızgarada.
    assert grid.index("Tuğçe Karagöz") < grid.index("Temsilci Öğrenci 01")
    assert "Temsilci Öğrenci 24" in grid


def test_son_satir_eksikse_haneler_ayni_genislikte_kalir() -> None:
    html = _minutes_html(_assembly_meeting(7))
    assert _signature_rows(html) == [5, 2]
    # 2 imzalı son satır 5 hücreye tamamlanır: haneler yarım sayfaya yayılmaz.
    assert _signature_grid(html).split("<tr>")[2].count("<td") == 5


def test_kalabalik_kurul_tutanagi_butun_imzacilari_sayfa_icinde_basar() -> None:
    """Tek satırlı ızgarada 7. haneden sonrası sayfa dışına taşıyordu (25 imzacı)."""
    meeting = _assembly_meeting(25)
    reader = PdfReader(BytesIO(doc_engine.render_council_meeting_minutes(meeting)))
    page_width = float(reader.pages[0].mediabox.width)
    positions: list[float] = []

    def visitor(text: str, cm: Any, tm: Any, _font: Any, _size: Any) -> None:
        if text.strip():
            # Metin matrisi (tm) sayfa dönüşümüyle (cm) çarpılınca sayfa koordinatı olur.
            positions.append(float(cm[0] * tm[4] + cm[2] * tm[5] + cm[4]))

    for page in reader.pages:
        page.extract_text(visitor_text=visitor)
    assert positions
    assert max(positions) < page_width


def test_az_uyeli_kurulda_imza_izgarasi_tek_satir_kalir() -> None:
    """5 ve altı imzacıda (ÖDK başkan + 4 üye) çıktı eski tek satırlı ızgaradır."""
    html = _minutes_html(_assembly_meeting(5))
    assert _signature_rows(html) == [5]
    grid = _signature_grid(html)
    assert grid.count("<td>") == 5  # hane genişliği yalnız çok satırlı ızgarada sabitlenir
    assert "width" not in grid


# ---------------------------------------------------------------------------
# Bulgu 11, 32, 55 — imza/onay bloğu tek başına ayrı sayfaya düşmez
# ---------------------------------------------------------------------------
def test_arama_tutanagi_tek_sayfadir() -> None:
    """md. 158/3: imzalar ve müdür onayı aynı sayfada (iki nüsha = iki çıktı)."""
    case = _case(StudentFactory())
    pages = _pages(
        _pdf(
            case,
            DocumentType.SEARCH_RECORD,
            statement_date=date(2026, 5, 20),
            statement_time="10:40",
            statement_place="10/A dersliği",
        )
    )
    assert len(pages) == 1
    assert "İlgili Öğrenci (varsa)" in pages[0]
    assert "ONAYLANDI" in pages[0]


def test_arama_tutanagi_bos_uretimde_de_tek_sayfadir() -> None:
    case = _case(StudentFactory())
    assert len(_pages(_pdf(case, DocumentType.SEARCH_RECORD))) == 1


@pytest.mark.parametrize("penalty_type", [PenaltyType.NO_PENALTY, PenaltyType.REPRIMAND])
def test_ek1_mudur_imzasi_onay_kutusundan_kopmaz(penalty_type: str) -> None:
    """Müdür imza bloğu onay kutusuyla aynı sayfada: son sayfada yalnız imza kalmaz.

    Taşma içerik uzunluğuna bağlıdır (sahada kısa anlatılarla çıktı): anlatı satır satır
    uzatılarak sayfa sonunun onay kutusuna denk geldiği aralık taranır — eski şablonda
    7-12 satırda imza bloğu tek başına üçüncü sayfaya düşüyordu.
    """
    student = StudentFactory(first_name="IRAZ ÖYKÜ", last_name="ÜNLÜ")
    case = _case(student)
    committee_for(SchoolYear.objects.get(is_active=True))
    decision = services.record_decision(
        case, student_id=student.pk, penalty_type=penalty_type, decision_date=date(2026, 5, 22)
    )
    for line_count in range(5, 15):
        update_decision_narrative(
            decision,
            fields={
                "accused_statement_summary": "\n".join(f"Satır {i}" for i in range(line_count))
            },
        )
        pages = _pages(
            _pdf(case, DocumentType.COMMITTEE_DECISION, student_id=student.pk, log=False)
        )
        signature_page = next(p for p in reversed(pages) if "Okul Müdürü" in p)
        assert "OKUL MÜDÜRÜNÜN ONAYI" in signature_page, line_count
        assert "YENİDEN GÖRÜŞÜLMESİ HUSUSUNDA" in signature_page, line_count
