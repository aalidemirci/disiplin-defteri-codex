"""Kullanıcı kararları (14.11.2026) — "evrak" grubu: S1, S3, S12.

Saha denetiminde OYS paritesi (CLAUDE.md §1/3) gerekçesiyle GERİ ALINAN ya da dokunulmayan
evrak kusurları için kullanıcı 14.11.2026'da karar verdi (`docs/teknik-borc.md`):

- S1  — karar defterinde (dosya görüşme tutanağı) uzaklaştırma gün sayısı basılır,
        kararlar karar numarası sırasıyla dizilir (md. 164/2, 196/1).
- S3  — beş şablon düzeltmesi: Form-02 veli yazısında tamlayan eki; Form-14'te cezasız
        kararın tebellüğ metni ve değişen ceza notu; onur teklif tutanağında "Toplantı
        Tarihi / No"; Form-11 dolu tutanakta imza bloğu taşması.
- S12 — kurula sevkli (Dal B) dosyada öğrencinin uyarı kaydı yoksa müdür yazılı uyarısı
        (Form-02) ve veli görüşme tutanağı üretilmez (md. 157/7-a, 157/7-b).

Her kalemde kararın KAPSAMADIĞI durumun çıktısının değişmediği de sabitlenir.
"""

from __future__ import annotations

from datetime import date
from io import BytesIO
from typing import Any

import pytest
from pypdf import PdfReader
from rest_framework.test import APIClient

from apps.disiplin import documents as doc_engine
from apps.disiplin import honor_documents, selectors, services
from apps.disiplin.models import (
    CaseStage,
    DisciplineCase,
    DisciplineWarning,
    DocumentType,
    ParticipantRole,
    PenaltyType,
    PrincipalDecision,
)
from apps.disiplin.tests.factories import (
    PersonnelFactory,
    SchoolYearFactory,
    StudentFactory,
    approve,
    committee_attendees,
    committee_for,
    decide,
    ensure_terms,
)
from apps.okul.services import setup as okul_setup

pytestmark = pytest.mark.django_db

_SUSPENSION = "Okuldan kısa süreli uzaklaştırma"


def _pages(pdf_bytes: bytes) -> list[str]:
    reader = PdfReader(BytesIO(pdf_bytes))
    return [" ".join((page.extract_text() or "").split()) for page in reader.pages]


def _pdf_text(pdf_bytes: bytes) -> str:
    return " ".join(_pages(pdf_bytes))


def _case(
    *students: Any, principal_decision: str | None = PrincipalDecision.DISCIPLINE_COMMITTEE
) -> DisciplineCase:
    """Dosya: varsayılan kurula sevkli (Dal B); `WRITTEN_WARNING` → Dal A; None → karar öncesi."""
    SchoolYearFactory()
    okul_setup.update_school_config(
        fields={
            "school_name": "Deneme Anadolu Lisesi",
            "district": "Menteşe",
            "principal_name": "ALİ ÖRNEK",
        }
    )
    case = services.create_case(
        petition_date=date(2026, 5, 18),
        petitioner_name="İdare",
        petitioner_role="IDARE",
        summary="Koridorda kavga.",
        student_ids=[s.pk for s in students],
    )
    if principal_decision is not None:
        services.add_event(
            case,
            CaseStage.DECIDED,
            date(2026, 5, 19),
            override=True,
            override_reason="atla",
            principal_decisions=[principal_decision],
        )
    return case


def _pdf(case: DisciplineCase, document_type: str, **kwargs: Any) -> bytes:
    kwargs.setdefault("generated_on", date(2026, 5, 28))
    kwargs.setdefault("log", False)
    pdf, _record = doc_engine.generate_document(case, document_type=document_type, **kwargs)
    return pdf


# ---------------------------------------------------------------------------
# S1 — karar defteri: uzaklaştırma gün sayısı + karar numarası sırası
# ---------------------------------------------------------------------------
def _case_review_meeting(case: DisciplineCase, year: Any) -> Any:
    return services.create_council_meeting(
        school_year_id=year.pk,
        council_type="DISCIPLINE",
        meeting_date=date(2026, 5, 22),
        attendees=committee_attendees(),
        minutes_type="CASE_REVIEW",
        discipline_case_id=case.pk,
    )


def _decision_rows(case: DisciplineCase) -> list[dict[str, Any]]:
    year = SchoolYearFactory()
    rows: list[dict[str, Any]] = doc_engine._council_minutes_context(
        _case_review_meeting(case, year)
    )["case_decisions"]
    return rows


def test_s1_karar_defterinde_uzaklastirma_gun_sayisi_basilir() -> None:
    """md. 164/2: uzaklaştırma 1-5 gündür; karar defteri kaç gün verildiğini de yazar."""
    a, b = StudentFactory(), StudentFactory()
    case = _case(a, b)
    decide(
        case, student_id=a.pk, penalty_type=PenaltyType.REPRIMAND, decision_date=date(2026, 5, 22)
    )
    decide(
        case,
        student_id=b.pk,
        penalty_type=PenaltyType.SHORT_TERM_SUSPENSION,
        suspension_days=3,
        decision_date=date(2026, 5, 22),
    )
    by_name = {r["full_name"]: r for r in _decision_rows(case)}
    assert by_name[b.full_name]["penalty_display"] == f"{_SUSPENSION} — 3 gün"
    # Gün sayısı olmayan cezada etiket değişmez.
    assert by_name[a.full_name]["penalty_display"] == "Kınama"


def test_s1_karar_defteri_pdfinde_gun_sayisi_ve_sira() -> None:
    """Belge gerçekten üretilir: gün sayısı basılı, kararlar numara sırasıyla."""
    year = SchoolYearFactory()
    a, b = StudentFactory(last_name="BİRİNCİ"), StudentFactory(last_name="İKİNCİ")
    case = _case(a, b)
    first = decide(
        case,
        student_id=a.pk,
        penalty_type=PenaltyType.SHORT_TERM_SUSPENSION,
        suspension_days=3,
        decision_date=date(2026, 5, 22),
    )
    second = decide(
        case, student_id=b.pk, penalty_type=PenaltyType.REPRIMAND, decision_date=date(2026, 5, 22)
    )
    text = _pdf_text(doc_engine.render_council_meeting_minutes(_case_review_meeting(case, year)))
    assert f"{_SUSPENSION} — 3 gün" in text
    assert first.decision_no < second.decision_no
    assert text.index(first.decision_no) < text.index(second.decision_no)
    assert text.index("BİRİNCİ") < text.index("İKİNCİ")


def test_s1_kararlar_karar_numarasi_sirasiyla_dizilir() -> None:
    """Numara DOĞAL (sayısal) sıralanır: "…/0002" < "…/0010" < "…/0100"; numarasız sona."""
    students = [StudentFactory() for _ in range(4)]
    case = _case(*students)
    for student in students:
        decide(
            case,
            student_id=student.pk,
            penalty_type=PenaltyType.REPRIMAND,
            decision_date=date(2026, 5, 22),
        )
    # Model sırası (yeniden eskiye) ile numara sırası bilerek çakıştırılmaz; "9" < "10"
    # metin sıralamasında tersine döneceği için sayısal karşılaştırma şarttır.
    numbers = ["2025-2026/0010", "", "2025-2026/0100", "2025-2026/0009"]
    for decision, number in zip(selectors.decisions_for_case(case), numbers, strict=True):
        type(decision).objects.filter(pk=decision.pk).update(decision_no=number)
    rows = _decision_rows(case)
    assert [r["decision_no"] for r in rows] == [
        "2025-2026/0009",
        "2025-2026/0010",
        "2025-2026/0100",
        "",
    ]


def test_s1_ayni_gun_verilen_kararlar_verilis_sirasiyla() -> None:
    """Sahadaki görünüm: aynı gün verilen kararlar ters (yeniden eskiye) diziliyordu."""
    students = [StudentFactory() for _ in range(3)]
    case = _case(*students)
    decisions = [
        decide(
            case,
            student_id=student.pk,
            penalty_type=PenaltyType.REPRIMAND,
            decision_date=date(2026, 5, 22),
        )
        for student in students
    ]
    rows = _decision_rows(case)
    assert [r["decision_no"] for r in rows] == [d.decision_no for d in decisions]
    assert [r["full_name"] for r in rows] == [s.full_name for s in students]


def test_s1_degisen_cezada_kurulun_verdigi_ceza_gun_sayisiyla() -> None:
    """Karar defteri okul kurulunun kararını kaydeder (md. 196/1): ceza itirazla kınamaya
    çevrilse de satır kurulun verdiği "… — 5 gün" cezasıdır."""
    student = StudentFactory()
    case = _case(student)
    decision = decide(
        case,
        student_id=student.pk,
        penalty_type=PenaltyType.SHORT_TERM_SUSPENSION,
        suspension_days=5,
        decision_date=date(2026, 5, 22),
    )
    approve(decision)
    services.notify_decision(decision, notified_on=date(2026, 5, 22))
    appeal = services.file_appeal(decision, filed_on=date(2026, 5, 25), filed_by_role="PARENT")
    services.resolve_appeal(
        appeal, result="REDUCED", resulted_on=date(2026, 6, 3), new_penalty_type="REPRIMAND"
    )
    row = _decision_rows(case)[0]
    assert row["penalty_display"] == f"{_SUSPENSION} — 5 gün"
    assert row["statute_label"] == "Madde 164/2"


def test_s1_dosyasiz_tutanakta_karar_tablosu_yok() -> None:
    """Kapsam dışı: dosya görüşmesi olmayan (genel) tutanakta öğrenci-bazlı karar bloğu yok."""
    year = SchoolYearFactory()
    meeting = services.create_council_meeting(
        school_year_id=year.pk,
        council_type="DISCIPLINE",
        meeting_date=date(2026, 5, 22),
        attendees=[{"person_name": "BAŞKAN", "attendee_role": "VOTING_MEMBER", "is_chair": True}],
    )
    assert doc_engine._council_minutes_context(meeting)["case_decisions"] == []
    assert "ÖĞRENCİ BAZLI KARARLAR" not in _pdf_text(
        doc_engine.render_council_meeting_minutes(meeting)
    )


# ---------------------------------------------------------------------------
# S3 (a) — Form-02 veli yazısı: öğrenci adından sonra tamlayan eki (ünlü uyumu)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("last_name", "expected"),
    [
        ("AYDIN", "EMRE CAN AYDIN'IN sergilediği"),
        ("KAYA", "EMRE CAN KAYA'NIN sergilediği"),
        ("ÖZTÜRK", "EMRE CAN ÖZTÜRK'ÜN sergilediği"),
        ("ÇELİK", "EMRE CAN ÇELİK'İN sergilediği"),
    ],
)
def test_s3a_form02_veli_yazisinda_tamlayan_eki(last_name: str, expected: str) -> None:
    student = StudentFactory(last_name=last_name)
    case = _case(student, principal_decision=PrincipalDecision.WRITTEN_WARNING)
    text = _pdf_text(
        _pdf(
            case,
            DocumentType.WARNING_LETTER,
            student_id=student.pk,
            recipient="parent",
            behavior_summary="Derse geç kalmak",
        )
    )
    assert expected in text
    assert "'in sergilediği" not in text
    # Cümlenin gerisi değişmedi.
    assert 'sergilediği "Derse geç kalmak" davranışının' in text


def test_s3a_form02_ogrenci_surumu_degismez() -> None:
    """Kapsam dışı: öğrenci sürümü (warning_letter.html) ada ek getirmez — dokunulmadı."""
    student = StudentFactory(last_name="AYDIN")
    case = _case(student, principal_decision=PrincipalDecision.WRITTEN_WARNING)
    text = _pdf_text(
        _pdf(
            case,
            DocumentType.WARNING_LETTER,
            student_id=student.pk,
            behavior_summary="Derse geç kalmak",
        )
    )
    assert "Sayın EMRE CAN AYDIN (" in text
    assert 'Sergilemiş olduğunuz "Derse geç kalmak" eyleminizin' in text
    assert "AYDIN'" not in text


# ---------------------------------------------------------------------------
# S3 (b) — Form-14: cezasız kararda tebellüğ metni "ceza" demez
# ---------------------------------------------------------------------------
_FORM14_PENALTY_ACK = (
    "Açıklama: Millî Eğitim Bakanlığı Ortaöğretim Kurumları Yönetmeliği uyarınca şahsıma "
    "verilen disiplin cezasına ilişkin yukarıdaki tebliğ yazısını okudum, içeriğini anladım "
    "ve bir suretini elden teslim aldım."
)
_FORM14_NO_PENALTY_ACK = (
    "Açıklama: Millî Eğitim Bakanlığı Ortaöğretim Kurumları Yönetmeliği uyarınca hakkımda "
    "verilen disiplin kurulu kararına ilişkin yukarıdaki tebliğ yazısını okudum, içeriğini "
    "anladım ve bir suretini elden teslim aldım."
)


def _decided_case(penalty_type: str, **kwargs: Any) -> tuple[DisciplineCase, Any]:
    student = StudentFactory(guardian_name="Veli Örnek")
    case = _case(student)
    decide(
        case,
        student_id=student.pk,
        penalty_type=penalty_type,
        decision_date=date(2026, 5, 22),
        **kwargs,
    )
    return case, student


def test_s3b_form14_cezasiz_kararda_tebellug_metni_ceza_demez() -> None:
    """md. 163: "ceza verilmesine yer olmadığı" kararında öğrenci ceza tebellüğ etmez."""
    case, student = _decided_case(PenaltyType.NO_PENALTY)
    text = _pdf_text(_pdf(case, DocumentType.PENALTY_NOTICE, student_id=student.pk))
    assert "ÖĞRENCİYE DİSİPLİN KURULU KARARI TEBLİĞİ" in text
    assert "verilen disiplin cezasına" not in text
    assert _FORM14_NO_PENALTY_ACK in text


def test_s3b_form14_cezali_kararda_tebellug_metni_degismez() -> None:
    case, student = _decided_case(PenaltyType.REPRIMAND)
    text = _pdf_text(_pdf(case, DocumentType.PENALTY_NOTICE, student_id=student.pk))
    assert "ÖĞRENCİYE DİSİPLİN CEZASI TEBLİĞİ" in text
    assert _FORM14_PENALTY_ACK in text
    assert "disiplin kurulu kararına ilişkin" not in text


# ---------------------------------------------------------------------------
# S3 (c) — Form-14: üst kurulca değişen cezada Form-15'teki not
# ---------------------------------------------------------------------------
_CHANGE_NOTE = (
    "İşbu yazı ile tebliğ edilen ceza yürürlükteki cezadır. Okul Öğrenci Ödül ve Disiplin "
    f'Kurulunun verdiği "{_SUSPENSION} — 5 gün" cezası, itiraz üzerine İlçe öğrenci disiplin '
    'kurulunca "Kınama" olarak değiştirilmiştir.'
)


def _reduced_case() -> tuple[DisciplineCase, Any]:
    """5 gün uzaklaştırma → onay → tebliğ → itiraz → REDUCED (kınama) — md. 200/1-ç."""
    case, student = _decided_case(PenaltyType.SHORT_TERM_SUSPENSION, suspension_days=5)
    decision = case.decisions.get()
    approve(decision)
    services.notify_decision(decision, notified_on=date(2026, 5, 22))
    appeal = services.file_appeal(decision, filed_on=date(2026, 5, 25), filed_by_role="PARENT")
    services.resolve_appeal(
        appeal,
        result="REDUCED",
        resulted_on=date(2026, 6, 3),
        new_penalty_type=PenaltyType.REPRIMAND,
    )
    return case, student


def test_s3c_form14_degisen_cezada_not_basilir() -> None:
    case, student = _reduced_case()
    texts = {
        recipient: _pdf_text(
            _pdf(
                case,
                DocumentType.PENALTY_NOTICE,
                student_id=student.pk,
                recipient=recipient,
                generated_on=date(2026, 6, 5),
            )
        )
        for recipient in ("student", "parent")
    }
    # Öğrenci (Form-14) ve veli (Form-15) suretleri AYNI notu taşır.
    assert _CHANGE_NOTE in texts["student"]
    assert _CHANGE_NOTE in texts["parent"]
    # Tebliğ edilen ceza yine yürürlükteki cezadır (§8) — not yalnız geçmişi anlatır.
    assert '"Kınama" cezası verilmiştir' in texts["student"]
    assert "(5 gün)" not in texts["student"]


def test_s3c_form14_degismemis_kararda_not_yok() -> None:
    case, student = _decided_case(PenaltyType.SHORT_TERM_SUSPENSION, suspension_days=3)
    text = _pdf_text(_pdf(case, DocumentType.PENALTY_NOTICE, student_id=student.pk))
    assert "olarak değiştirilmiştir" not in text
    assert "yürürlükteki cezadır" not in text
    # Ceza paragrafından sonra doğrudan md. 166 paragrafı gelir (araya not girmedi).
    assert (
        "işbu belge ile tarafınıza tebliğ edilmektedir. Disiplin cezası verilmesine sebep" in text
    )
    assert _FORM14_PENALTY_ACK in text


# ---------------------------------------------------------------------------
# S3 (d) — Onur Kurulu Teklif Tutanağı: "Toplantı Tarihi / No"
# ---------------------------------------------------------------------------
def _honor_meeting(year: Any) -> Any:
    ensure_terms(year)
    return services.create_council_meeting(
        school_year_id=year.pk,
        council_type="HONOR",
        meeting_date=date(2026, 5, 25),
        attendees=[
            {"person_name": "Onur Başkanı", "attendee_role": "VOTING_MEMBER", "is_chair": True},
            {"person_name": "Öğrenci Üye", "attendee_role": "VOTING_MEMBER", "is_chair": False},
        ],
    )


def test_s3d_onur_teklif_tutanaginda_toplanti_tarihi_ve_no() -> None:
    """md. 183/b: uygun görüş toplantıda verilir — tutanak toplantının tarih ve numarasını taşır."""
    year = SchoolYearFactory()
    board = services.create_honor_board(school_year_id=year.pk, chair_id=PersonnelFactory().pk)
    meeting = _honor_meeting(year)
    text = _pdf_text(honor_documents.render_recommendation_record([], board=board, meeting=meeting))
    assert f"Toplantı Tarihi / No 25.05.2026 / {meeting.meeting_no_display}" in text
    assert "Düzenlenme Tarihi" in text


def test_s3d_onur_teklif_tutanagi_toplantisiz_yolda_satir_basilmaz() -> None:
    year = SchoolYearFactory()
    board = services.create_honor_board(school_year_id=year.pk, chair_id=PersonnelFactory().pk)
    text = _pdf_text(honor_documents.render_recommendation_record([], board=board))
    assert "Toplantı Tarihi" not in text
    assert "Teklif Dönemi — Düzenlenme Tarihi" in text  # künye iki satır, arada başka satır yok


# ---------------------------------------------------------------------------
# S3 (e) — Form-11 savunma tutanağı: imza bloğu tek başına sayfaya düşmez
# ---------------------------------------------------------------------------
_SENTENCE = "Olay günü koridorda arkadaşımla tartıştım, sonra pişman oldum ve özür diledim. "


def _defense_case(*, with_committee: bool = True) -> tuple[DisciplineCase, Any]:
    year = SchoolYearFactory()
    if with_committee:
        committee_for(year)
    case = _case(StudentFactory())
    return case, case.participants.get(role=ParticipantRole.ACCUSED)


def _defense_pages(case: DisciplineCase, participant: Any, sentences: int) -> list[str]:
    return _pages(
        _pdf(
            case,
            DocumentType.DEFENSE_RECORD,
            participant_id=participant.pk,
            statement_subject="Koridorda kavga" if sentences else "",
            statement_body=(_SENTENCE * sentences).strip(),
        )
    )


def test_s3e_form11_kisa_dolu_tutanak_tek_sayfa() -> None:
    """Sahadaki kusur: birkaç cümlelik savunmada kurul imza ızgarası TEK BAŞINA 2. sayfaya
    düşüyor, "SAVUNMAYI ALANLAR" başlığı 1. sayfada sahipsiz kalıyordu."""
    case, participant = _defense_case()
    for sentences in (1, 5, 10):
        pages = _defense_pages(case, participant, sentences)
        assert len(pages) == 1, f"{sentences} cümle: {len(pages)} sayfa"
        assert "Savunma Veren — Adı Soyadı ve İmza SAVUNMAYI ALANLAR" in pages[0]
        assert "Başkan (Müdür Yrd.)" in pages[0]


@pytest.mark.parametrize("sentences", [1, 5, 10, 14, 18, 20, 22, 24, 26, 28, 30, 40, 60, 80])
def test_s3e_form11_imza_blogu_savunma_metniyle_ayni_sayfada(sentences: int) -> None:
    """Metin ne uzunlukta olursa olsun: savunmayı verenin imzası, "SAVUNMAYI ALANLAR"
    başlığı ve kurul ızgarası BİRLİKTE kalır ve bulundukları sayfada savunma metni vardır."""
    case, participant = _defense_case()
    pages = _defense_pages(case, participant, sentences)
    last = pages[-1]
    assert "Savunma Veren — Adı Soyadı ve İmza SAVUNMAYI ALANLAR" in last
    assert "Başkan (Müdür Yrd.)" in last
    assert "özür diledim." in last, "imza bloğu savunma metni olmadan tek başına kaldı"
    for page in pages[:-1]:
        assert "Savunma Veren" not in page and "SAVUNMAYI ALANLAR" not in page
    # Metnin tamamı basıldı (kesilmedi).
    assert " ".join(pages).count("özür diledim.") == sentences


def test_s3e_form11_uzun_tutanakta_sayfa_sayisi_degismez() -> None:
    """Metin zaten son sayfaya akıyorsa sayfa sayısı eskisiyle aynıdır (30-60 cümle: 2, 80: 3)."""
    case, participant = _defense_case()
    assert [len(_defense_pages(case, participant, n)) for n in (30, 40, 60, 80)] == [2, 2, 2, 3]


def test_s3e_form11_bos_tutanak_degismez() -> None:
    """Kapsam dışı: elle doldurulan boş tutanak iki sayfadır; düzeni değişmedi."""
    case, participant = _defense_case()
    pages = _defense_pages(case, participant, 0)
    assert len(pages) == 2
    assert pages[0].endswith("SAVUNMAM (İkinci sayfada devam ediniz.) Sayfa 1 / 2")
    assert pages[1].startswith(
        "SAVUNMAM (devamı) …/…/202… ………………………………………… Savunma Veren — Adı Soyadı ve İmza "
        "SAVUNMAYI ALANLAR"
    )


def test_s3e_form11_yer_varsayilani_kalir() -> None:
    """Kullanıcı kararı: boş "Yer" alanına "Müdür Yardımcısı Odası" basılması SÜRER."""
    case, participant = _defense_case()
    assert "Yer Müdür Yardımcısı Odası" in _defense_pages(case, participant, 1)[0]
    assert "Yer Müdür Yardımcısı Odası" in _defense_pages(case, participant, 0)[0]


def test_s3e_form11_kurulsuz_kisa_tutanak_tek_sayfa() -> None:
    case, participant = _defense_case(with_committee=False)
    pages = _defense_pages(case, participant, 1)
    assert len(pages) == 1
    assert "Disiplin kurulu tanımlı değil" in pages[0]


# ---------------------------------------------------------------------------
# S12 — Dal B dosyada uyarı kaydı yoksa Form-02 ve veli görüşme tutanağı üretilmez
# ---------------------------------------------------------------------------
_S12_DOCS: list[tuple[str, dict[str, Any]]] = [
    (DocumentType.WARNING_LETTER, {"recipient": "student", "behavior_summary": "Geç kalmak"}),
    (DocumentType.WARNING_LETTER, {"recipient": "parent", "behavior_summary": "Geç kalmak"}),
    (DocumentType.PARENT_MEETING, {"variant": "meeting"}),
]
_S12_IDS = ["form02-ogrenci", "form02-veli", "veli-gorusme-tutanagi"]


def _warned_referred_case() -> tuple[DisciplineCase, Any]:
    """Dal B dosya + öğrencinin O DOSYADA uyarı kaydı.

    Gerçekte bu durum, müdürün yazılı uyarı kararından sonra aşamanın geri alınıp dosyanın
    kurula sevk edilmesiyle oluşur (uyarı kaydı dosyada kalır). Kayıt burada doğrudan
    modelden açılır: `issue_warning` kurula sevkli dosyada yeni kayıt açmaz.
    """
    student = StudentFactory(guardian_name="Veli Örnek")
    case = _case(student)
    DisciplineWarning.objects.create(
        case=case, student_id=student.pk, warning_date=date(2026, 5, 19), summary="Geç kalmak"
    )
    return case, student


@pytest.mark.parametrize(("document_type", "kwargs"), _S12_DOCS, ids=_S12_IDS)
def test_s12_dal_b_uyari_kaydi_yoksa_uretilmez(document_type: str, kwargs: dict[str, Any]) -> None:
    """md. 157/7-a/b: yapılmamış yazılı uyarı "yapıldı" diye belgelenmez."""
    student = StudentFactory()
    case = _case(student)
    with pytest.raises(ValueError, match="müdür uyarısı kaydı yok") as excinfo:
        _pdf(case, document_type, student_id=student.pk, log=True, **kwargs)
    message = str(excinfo.value)
    assert "kurula sevk edilmiş" in message
    assert "md. 157/7" in message
    assert not case.generated_documents.exists()  # kütüğe de yazılmadı


@pytest.mark.parametrize(("document_type", "kwargs"), _S12_DOCS, ids=_S12_IDS)
def test_s12_dal_b_uyari_kaydi_varsa_uretilir(document_type: str, kwargs: dict[str, Any]) -> None:
    case, student = _warned_referred_case()
    text = _pdf_text(_pdf(case, document_type, student_id=student.pk, **kwargs))
    assert "157" in text


def test_s12_cok_ogrencili_dosyada_kayit_ogrenciye_ozgudur() -> None:
    """Uyarı kaydı başka öğrencinin ise seçilen öğrenci için belge üretilmez."""
    warned, other = StudentFactory(), StudentFactory()
    case = _case(warned, other)
    DisciplineWarning.objects.create(
        case=case, student_id=warned.pk, warning_date=date(2026, 5, 19), summary="Geç kalmak"
    )
    _pdf(case, DocumentType.WARNING_LETTER, student_id=warned.pk, behavior_summary="Geç kalmak")
    with pytest.raises(ValueError, match="müdür uyarısı kaydı yok"):
        _pdf(case, DocumentType.WARNING_LETTER, student_id=other.pk, behavior_summary="Geç kalmak")


@pytest.mark.parametrize("variant", ["invite", "no_show", ""])
def test_s12_veli_davet_ve_gelmedi_tutanagi_kapsam_disi(variant: str) -> None:
    """Karar yalnız görüşme tutanağını kapsar: davet yazısı ve "veli gelmedi" tutanağı Dal B
    dosyada uyarı kaydı olmadan da üretilmeye devam eder (boş sürüm = davet)."""
    student = StudentFactory()
    case = _case(student)
    text = _pdf_text(
        _pdf(case, DocumentType.PARENT_MEETING, student_id=student.pk, variant=variant)
    )
    assert "157" in text
    assert "VELİ GÖRÜŞME TUTANAĞI" not in text


@pytest.mark.parametrize(("document_type", "kwargs"), _S12_DOCS, ids=_S12_IDS)
@pytest.mark.parametrize(
    "principal_decision", [PrincipalDecision.WRITTEN_WARNING, None], ids=["dal-a", "karar-oncesi"]
)
def test_s12_dal_a_ve_karar_oncesi_dosyada_davranis_degismez(
    principal_decision: str | None, document_type: str, kwargs: dict[str, Any]
) -> None:
    """Kapsam dışı: yazılı uyarıyla kapanan (Dal A) ve henüz müdür kararı verilmemiş dosyada
    belge, uyarı kaydı aranmadan eskisi gibi üretilir."""
    student = StudentFactory()
    case = _case(student, principal_decision=principal_decision)
    assert not case.warnings.exists()
    text = _pdf_text(_pdf(case, document_type, student_id=student.pk, **kwargs))
    assert "157" in text


def test_s12_uretim_ucu_turkce_iletiyle_400_doner() -> None:
    """Arayüz ret iletisini sunucudan alır ({code, message} sözleşmesi)."""
    student = StudentFactory()
    case = _case(student)
    response = APIClient().post(
        f"/api/v1/discipline/cases/{case.pk}/documents/generate/",
        {
            "document_type": "WARNING_LETTER",
            "generated_on": "2026-05-28",
            "student": student.pk,
            "behavior_summary": "Geç kalmak",
        },
        format="json",
    )
    assert response.status_code == 400
    assert "müdür uyarısı kaydı yok" in response.json()["message"]
