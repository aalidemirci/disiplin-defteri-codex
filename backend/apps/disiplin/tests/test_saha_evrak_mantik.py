"""Saha (Windows uçtan uca) denetimi — evrak motoru mantık düzeltmeleri.

Her test, sahada yeniden üretilmiş bir kusuru sabitler (bulgu numarası test
açıklamasında). Bağlam (context) düzeyindeki denetimler `render_pdf_paged`
yakalanarak yapılır — WeasyPrint koşmadan şablona giden veriyi doğrular; resmî
metnin kendisi gereken yerde gerçek PDF'ten okunur.
"""

from __future__ import annotations

from datetime import date
from io import BytesIO
from typing import Any

import pytest
from django.template.loader import render_to_string
from django.utils import timezone
from pypdf import PdfReader

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
    ensure_terms,
)
from apps.okul.services import setup as okul_setup

pytestmark = pytest.mark.django_db


def _pdf_text(pdf_bytes: bytes) -> str:
    reader = PdfReader(BytesIO(pdf_bytes))
    return " ".join("\n".join(page.extract_text() or "" for page in reader.pages).split())


@pytest.fixture
def ctx(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Şablona giden son bağlamı yakalar (PDF üretmeden)."""
    captured: dict[str, Any] = {}

    def fake(template: str, context: dict[str, Any]) -> tuple[bytes, int]:
        captured.clear()
        captured.update(context)
        captured["__template__"] = template
        return b"%PDF-sahte", 1

    monkeypatch.setattr(doc_engine, "render_pdf_paged", fake)
    return captured


def _case(*students: Any, petitioner_user_id: int | None = None) -> DisciplineCase:
    """Kurula sevkli (Dal B) dosya — öğrenciler verilen sırayla eklenir."""
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
        petitioner_role="OGRETMEN" if petitioner_user_id else "IDARE",
        summary="Koridorda kavga.",
        student_ids=[s.pk for s in students],
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


def _warn(case: DisciplineCase, student: Any) -> None:
    """Dal B dosyaya öğrencinin müdür uyarısı kaydını ekler (uyarıdan sonra kurula sevk
    edilmiş dosya). `issue_warning` kurula sevkli dosyada kayıt açmadığı için modelden."""
    DisciplineWarning.objects.create(
        case=case, student_id=student.pk, warning_date=date(2026, 5, 19), summary="x"
    )


def _generate(case: DisciplineCase, document_type: str, **kwargs: Any) -> Any:
    kwargs.setdefault("generated_on", date(2026, 5, 22))
    _pdf, record = doc_engine.generate_document(case, document_type=document_type, **kwargs)
    return record


# ---------------------------------------------------------------------------
# Bulgu 1, 4 — mağdur/tanık ÖĞRENCİ için ifade evrakı (md. 193/1, 195)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("role", [ParticipantRole.WITNESS, ParticipantRole.VICTIM])
@pytest.mark.parametrize(
    "document_type",
    [
        DocumentType.STATEMENT_CALL,
        DocumentType.STATEMENT_RECORD,
        DocumentType.NON_COMPLIANCE_RECORD,
    ],
)
def test_magdur_tanik_ogrenci_icin_ifade_evraki_uretilir(
    ctx: dict[str, Any], role: str, document_type: str
) -> None:
    """md. 193/1 "olayla ilgili tanıkların … yazılı ifadeleri alınır": dosyanın
    hakkında işlem yapılanı OLMAYAN öğrenci-katılımcı için de belge kütüğe yazılır."""
    accused = StudentFactory()
    other = StudentFactory(first_name="TANIK", last_name="ÖĞRENCİ")
    case = _case(accused)
    participant = services.add_participant(
        case, role=role, person_type="STUDENT", person_id=other.pk
    )
    record = _generate(case, document_type, participant_id=participant.pk)
    assert record is not None
    # Kütükte öğrenci bağı yalnız dosyanın öğrencisi (hakkında işlem yapılan) içindir;
    # "kimden" bilgisi source_label/source_name ile taşınır.
    assert record.student_id is None
    assert record.source_name == "TANIK ÖĞRENCİ"
    assert ctx["participant"]["name"] == "TANIK ÖĞRENCİ"


def test_hakkinda_islem_yapilan_ogrencide_kutuk_bagi_korunur(ctx: dict[str, Any]) -> None:
    accused = StudentFactory()
    case = _case(accused)
    participant = case.participants.get(role=ParticipantRole.ACCUSED)
    record = _generate(case, DocumentType.STATEMENT_RECORD, participant_id=participant.pk)
    assert record.student_id == accused.pk


# ---------------------------------------------------------------------------
# Bulgu 16, 21, 35 — seçilen üretim tarihi belgeye basılır (§7.1 yerel tarih)
# ---------------------------------------------------------------------------
def test_secilen_uretim_tarihi_baglamda_belge_tarihidir(ctx: dict[str, Any]) -> None:
    accused = StudentFactory()
    case = _case(accused)
    participant = case.participants.get(role=ParticipantRole.ACCUSED)
    _generate(
        case,
        DocumentType.STATEMENT_CALL,
        participant_id=participant.pk,
        generated_on=date(2026, 5, 20),
    )
    assert timezone.localtime(ctx["generated_at"]).date() == date(2026, 5, 20)


def test_secilen_uretim_tarihi_pdfe_basilir() -> None:
    accused = StudentFactory()
    case = _case(accused)
    participant = case.participants.get(role=ParticipantRole.ACCUSED)
    pdf, _ = doc_engine.generate_document(
        case,
        document_type=DocumentType.STATEMENT_CALL,
        generated_on=date(2026, 5, 20),
        participant_id=participant.pk,
        statement_date=date(2026, 5, 21),
    )
    text = _pdf_text(pdf)
    assert "20.05.2026" in text
    assert timezone.localdate().strftime("%d.%m.%Y") not in text


def test_bugun_uretilen_belgede_tarih_bugundur(ctx: dict[str, Any]) -> None:
    accused = StudentFactory()
    case = _case(accused)
    participant = case.participants.get(role=ParticipantRole.ACCUSED)
    today = timezone.localdate()
    _generate(case, DocumentType.STATEMENT_CALL, participant_id=participant.pk, generated_on=today)
    assert timezone.localtime(ctx["generated_at"]).date() == today


# ---------------------------------------------------------------------------
# Bulgu 15 — Form-11 / md. 195 imza ızgarası: toplantıya katılan heyet
# ---------------------------------------------------------------------------
def _committee_with_conflict() -> tuple[DisciplineCase, Any, Any, Any, Any]:
    year = SchoolYearFactory()
    complainant = PersonnelFactory(first_name="ŞİKÂYETÇİ", last_name="ÜYE")
    other = PersonnelFactory(first_name="DİĞER", last_name="ÜYE")
    substitute = PersonnelFactory(first_name="YEDEK", last_name="ÜYE")
    committee = services.create_committee(school_year_id=year.pk, chair_id=PersonnelFactory().pk)
    m_complainant = services.add_committee_member(
        committee, member_type="TEACHER", person_id=complainant.pk
    )
    m_other = services.add_committee_member(committee, member_type="TEACHER", person_id=other.pk)
    m_sub = services.add_committee_member(
        committee, member_type="TEACHER", person_id=substitute.pk, is_substitute=True
    )
    case = _case(StudentFactory(), petitioner_user_id=complainant.pk)
    return case, committee, m_complainant, m_other, m_sub


def test_form11_izgarasinda_sikayetci_uye_basilmaz(ctx: dict[str, Any]) -> None:
    """md. 191/2: şikâyetçi üye kurula katılamaz — toplantı kaydı yokken bile
    savunmayı alanlar arasında basılmaz."""
    case, _committee, m_complainant, m_other, _m_sub = _committee_with_conflict()
    participant = case.participants.get(role=ParticipantRole.ACCUSED)
    _generate(case, DocumentType.DEFENSE_RECORD, participant_id=participant.pk)
    names = [m.member_name for m in ctx["members"] if not m.is_substitute]
    assert m_complainant.member_name not in names
    assert m_other.member_name in names


@pytest.mark.parametrize(
    "document_type", [DocumentType.DEFENSE_RECORD, DocumentType.NON_COMPLIANCE_RECORD]
)
def test_form11_izgarasi_toplanti_katilimcilarini_basar(
    ctx: dict[str, Any], document_type: str
) -> None:
    """Dosyanın toplantı kaydı varsa imza ızgarası katılan heyettir (yedek dahil) —
    EK-1 ile aynı heyet (md. 186, 191/2, 194/1)."""
    case, _committee, m_complainant, m_other, m_sub = _committee_with_conflict()
    services.record_meeting(
        case, meeting_date=date(2026, 5, 21), attendee_member_ids=[m_other.pk, m_sub.pk]
    )
    participant = case.participants.get(role=ParticipantRole.ACCUSED)
    _generate(case, document_type, participant_id=participant.pk)
    names = [m.member_name for m in ctx["members"] if not m.is_substitute]
    assert sorted(names) == sorted([m_other.member_name, m_sub.member_name])
    assert m_complainant.member_name not in names


# ---------------------------------------------------------------------------
# Bulgu 36 — çok öğrencili dosyada Form-12/13
# ---------------------------------------------------------------------------
def _three_student_case() -> tuple[DisciplineCase, list[Any]]:
    students = [
        StudentFactory(first_name="İSMAİL", last_name="ŞIĞIN", class_level=10, class_section="Ç"),
        StudentFactory(first_name="IRAZ", last_name="ÜNLÜ", class_level=11, class_section="B"),
        StudentFactory(first_name="UĞUR", last_name="IŞIK", class_level=9, class_section="A"),
    ]
    case = _case(*students)
    services.create_extension(
        case, requested_days=5, reason="Tanıklar dinlenemedi.", decided_on=date(2026, 5, 25)
    )
    return case, students


def _html(ctx: dict[str, Any]) -> str:
    """Yakalanan bağlamla şablonun HTML çıktısı (boşluklar tek boşluğa indirgenmiş)."""
    return " ".join(render_to_string(ctx["__template__"], ctx).split())


def _kunye(s: dict[str, Any]) -> str:
    return (
        f"{s['class_label']} sınıfı {s['student_number']} numaralı "
        f"<strong>{s['full_name']}</strong>"
    )


@pytest.mark.parametrize("variant", ["record", "petition"])
def test_form12_13_cok_ogrencili_dosyada_butun_ogrenciler(
    ctx: dict[str, Any], variant: str
) -> None:
    """md. 192/3 uzatması dosya genelidir: bütün öğrenciler, dosyaya eklenme sırasıyla."""
    case, students = _three_student_case()
    _generate(case, DocumentType.DEADLINE_EXTENSION, variant=variant)
    assert [s["full_name"] for s in ctx["students"]] == [s.full_name for s in students]
    # Künye dosyanın İLK öğrencisinden başlar (sicil sırasındaki ilkinden değil).
    assert ctx["student"]["class_label"] == students[0].class_label
    # Gözden geçirme E7: `student.full_name` SAF addır — öteki öğrencilerin künyesi ada
    # gömülmez (kalın vurgu ve tekil "öğrenci/öğrencisi" kalıbı bozuluyordu).
    assert ctx["student"]["full_name"] == students[0].full_name
    assert ctx["requested_days_text"] == "beş"


@pytest.mark.parametrize(
    ("variant", "tail"),
    [
        ("record", "adlı öğrenciler hakkında yürütülmekte olan disiplin soruşturmasında"),
        ("petition", "adlı öğrencileri hakkında, ilgi yönetmelik gereğince başlatılan"),
    ],
)
def test_form12_13_cok_ogrencili_dosyada_cogul_kalip(
    ctx: dict[str, Any], variant: str, tail: str
) -> None:
    """Gözden geçirme E7 — şablon `students` üzerinden çoğul kalıp basar; her öğrencinin
    yalnız ADI kalındır, tekil "öğrenci <ad> hakkında" kalıbı basılmaz."""
    case, _students = _three_student_case()
    _generate(case, DocumentType.DEADLINE_EXTENSION, variant=variant)
    a, b, c = (_kunye(s) for s in ctx["students"])
    html = _html(ctx)
    assert f"{a}, {b} ve {c} {tail}" in html
    assert "numaralı öğrenci <strong>" not in html
    assert "numaralı öğrencisi <strong>" not in html


def test_form12_13_iki_ogrencili_dosyada_ve_baglaci(ctx: dict[str, Any]) -> None:
    a = StudentFactory(first_name="ALİ", last_name="KAYA")
    b = StudentFactory(first_name="VELİ", last_name="CAN")
    case = _case(a, b)
    services.create_extension(case, requested_days=3, reason="x", decided_on=date(2026, 5, 25))
    _generate(case, DocumentType.DEADLINE_EXTENSION, variant="record")
    first, second = (_kunye(s) for s in ctx["students"])
    assert f"{first} ve {second} adlı öğrenciler hakkında" in _html(ctx)


def test_form12_pdf_uc_ogrenciyi_de_yazar() -> None:
    case, students = _three_student_case()
    pdf, _ = doc_engine.generate_document(
        case,
        document_type=DocumentType.DEADLINE_EXTENSION,
        generated_on=date(2026, 5, 25),
        variant="record",
    )
    text = _pdf_text(pdf)
    for s in students:
        assert s.full_name in text
    assert "adlı öğrenciler hakkında yürütülmekte olan" in text


@pytest.mark.parametrize(
    ("variant", "sentence"),
    [
        # HEAD'deki (değişiklik öncesi) şablon cümleleri — birebir.
        (
            "record",
            "{cl} sınıfı {no} numaralı öğrenci <strong>EMRE CAN YILMAZ</strong> hakkında "
            "yürütülmekte olan disiplin soruşturmasında süre uzatımı talebinin görüşülmesi.",
        ),
        (
            "petition",
            "Okulumuz {cl} sınıfı {no} numaralı öğrencisi <strong>EMRE CAN YILMAZ</strong> "
            "hakkında, ilgi yönetmelik gereğince başlatılan ve Disiplin Kurulu Başkanlığım",
        ),
    ],
)
def test_form12_13_tek_ogrencili_dosyada_cikti_degismez(
    ctx: dict[str, Any], variant: str, sentence: str
) -> None:
    """Tek öğrencili dosyada Form-12/13 cümlesi eski (tekil) kalıpla AYNIDIR."""
    student = StudentFactory(first_name="EMRE CAN", last_name="YILMAZ")
    case = _case(student)
    services.create_extension(case, requested_days=3, reason="x", decided_on=date(2026, 5, 25))
    _generate(case, DocumentType.DEADLINE_EXTENSION, variant=variant)
    assert ctx["student"]["full_name"] == "EMRE CAN YILMAZ"
    assert len(ctx["students"]) == 1
    html = _html(ctx)
    assert sentence.format(cl=student.class_label, no=student.student_number) in html
    assert "adlı öğrenci" not in html


# ---------------------------------------------------------------------------
# Bulgu 46, 50, 75 + 13.11 denetimi — dayanak kaydı olmayan belge üretilmez
# ---------------------------------------------------------------------------
def test_tedbir_kaydi_olmayan_ogrenciye_tedbir_bildirimi_uretilmez() -> None:
    a, b = StudentFactory(), StudentFactory()
    case = _case(a, b)
    services.create_precaution(
        case, student_id=b.pk, start_date=date(2026, 5, 20), requested_days=3
    )
    with pytest.raises(ValueError, match="tedbir .* kaydı yok"):
        _generate(case, DocumentType.PRECAUTION_NOTICE, student_id=a.pk)
    assert _generate(case, DocumentType.PRECAUTION_NOTICE, student_id=b.pk) is not None


def test_uzatma_kaydi_yokken_form12_13_uretilmez() -> None:
    case = _case(StudentFactory())
    for variant in ("record", "petition"):
        with pytest.raises(ValueError, match="süre uzatma kaydı yok"):
            _generate(case, DocumentType.DEADLINE_EXTENSION, variant=variant)


def test_karar_yokken_form14_uretilmez() -> None:
    student = StudentFactory()
    case = _case(student)
    with pytest.raises(ValueError, match="kurul kararı yok"):
        _generate(case, DocumentType.PENALTY_NOTICE, student_id=student.pk)


def test_form18_itiraz_kaydi_olmadan_uretilmez() -> None:
    """Form-18 itiraz dilekçesini üst kurula sevk eder: karar, onay, tebliğ ve itiraz
    kaydı yokken "onaylanmıştır / itiraz etmiştir" basılamaz (md. 169/3)."""
    student = StudentFactory()
    case = _case(student)
    with pytest.raises(ValueError, match="kurul kararı yok"):
        _generate(case, DocumentType.APPEAL_LETTER, student_id=student.pk)
    decision = services.record_decision(
        case,
        student_id=student.pk,
        penalty_type=PenaltyType.REPRIMAND,
        decision_date=date(2026, 5, 22),
    )
    with pytest.raises(ValueError, match="itiraz kaydı yok"):
        _generate(case, DocumentType.APPEAL_LETTER, student_id=student.pk)
    approve(decision)
    services.notify_decision(decision, notified_on=date(2026, 5, 22))
    with pytest.raises(ValueError, match="itiraz kaydı yok"):
        _generate(case, DocumentType.APPEAL_LETTER, student_id=student.pk)
    services.file_appeal(decision, filed_on=date(2026, 5, 25), filed_by_role="PARENT")
    assert _generate(case, DocumentType.APPEAL_LETTER, student_id=student.pk) is not None


# ---------------------------------------------------------------------------
# Bulgu 49 — üst kurul onay tebliği: ilçeye gitmemiş müdür onaylı karar
# ---------------------------------------------------------------------------
def test_ust_kurul_onay_tebligi_ilceye_gitmemis_kararda_uretilmez() -> None:
    """md. 169/2-a: kınamayı müdür onaylar; üst kurul kararı ancak md. 197 sevkiyle
    doğar. İlçeye gönderilmemiş kararda "ilçe kurulunca onaylanmıştır" basılmaz."""
    student = StudentFactory()
    case = _case(student)
    decision = services.record_decision(
        case,
        student_id=student.pk,
        penalty_type=PenaltyType.REPRIMAND,
        decision_date=date(2026, 5, 22),
    )
    approve(decision)
    with pytest.raises(ValueError, match="ilçe kuruluna gönderilmemiş"):
        _generate(
            case,
            DocumentType.BOARD_DECISION_NOTICE,
            student_id=student.pk,
            notice_kind="approval",
        )
    # Merci elle seçilse de sonuç değişmez — olmayan bir üst kurul onayı tebliğ edilemez.
    with pytest.raises(ValueError, match="ilçe kuruluna gönderilmemiş"):
        _generate(
            case,
            DocumentType.BOARD_DECISION_NOTICE,
            student_id=student.pk,
            notice_kind="approval",
            board_authority="DISTRICT_BOARD",
        )


def test_ust_kurul_onay_tebligi_onaysiz_kararda_uretilmez() -> None:
    student = StudentFactory()
    case = _case(student)
    services.record_decision(
        case,
        student_id=student.pk,
        penalty_type=PenaltyType.SCHOOL_CHANGE,
        decision_date=date(2026, 5, 22),
    )
    with pytest.raises(ValueError, match="henüz onaylanmamış"):
        _generate(
            case,
            DocumentType.BOARD_DECISION_NOTICE,
            student_id=student.pk,
            notice_kind="approval",
        )


def test_ust_kurul_onay_tebligi_md197_sevkli_kararda_uretilir(ctx: dict[str, Any]) -> None:
    student = StudentFactory()
    case = _case(student)
    decision = services.record_decision(
        case,
        student_id=student.pk,
        penalty_type=PenaltyType.REPRIMAND,
        decision_date=date(2026, 5, 20),
    )
    services.record_principal_review(
        decision, action="RETURN", reason="a", decided_on=date(2026, 5, 21)
    )
    services.record_principal_review(
        decision, action="REFER", reason="b", decided_on=date(2026, 5, 26)
    )
    services.set_decision_approval(
        decision, approval_status="APPROVED", approved_on=date(2026, 5, 28)
    )
    _generate(
        case, DocumentType.BOARD_DECISION_NOTICE, student_id=student.pk, notice_kind="approval"
    )
    assert ctx["board_label"] == "İlçe öğrenci disiplin kurulu"


# ---------------------------------------------------------------------------
# Bulgu 3, 17, 22 — üst kurul / itirazla değişen ceza
# ---------------------------------------------------------------------------
def _reduced_case() -> tuple[DisciplineCase, Any, Any]:
    """5 gün uzaklaştırma → onay → tebliğ → itiraz → REDUCED (kınama)."""
    student = StudentFactory()
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
    appeal = services.file_appeal(decision, filed_on=date(2026, 5, 25), filed_by_role="PARENT")
    services.resolve_appeal(
        appeal,
        result="REDUCED",
        resulted_on=date(2026, 6, 3),
        new_penalty_type=PenaltyType.REPRIMAND,
    )
    decision.refresh_from_db()
    assert decision.penalty_type == PenaltyType.REPRIMAND  # §8: karar yeni cezaya güncellenir
    return case, student, decision


_SUSPENSION = "Okuldan kısa süreli uzaklaştırma"
_SUSPENSION_5 = f"{_SUSPENSION} — 5 gün"  # itiraz kaydı eski gün sayısını da saklar


def test_itiraz_sonucu_tebligi_itiraz_edilen_cezayi_yazar(ctx: dict[str, Any]) -> None:
    """Bulgu 17 — md. 200/1-Ç: "itiraza konu karar" eski cezadır, yeni ceza değil."""
    case, student, _decision = _reduced_case()
    _generate(
        case,
        DocumentType.BOARD_DECISION_NOTICE,
        student_id=student.pk,
        notice_kind="appeal_result",
        result_summary="5 gün uzaklaştırma kınamaya çevrilmiştir.",
    )
    assert ctx["decision"].get_penalty_type_display() == _SUSPENSION
    assert ctx["decision"].suspension_days == 5
    assert ctx["appealed_penalty_display"] == _SUSPENSION_5
    assert ctx["current_penalty_display"] == "Kınama"


@pytest.mark.parametrize(
    "document_type",
    # Gözden geçirme E2: PENALTY_NOTICE (Form-14/15) bu listeden ÇIKARILDI — tebliğ
    # yürürlükteki cezayı basar (aşağıdaki test_ceza_tebligi_* testleri).
    [DocumentType.COMMITTEE_DECISION, DocumentType.APPEAL_LETTER],
)
def test_okul_kurulu_belgeleri_kurulun_verdigi_cezayi_yazar(
    ctx: dict[str, Any], document_type: str
) -> None:
    """Bulgu 22 — okul kurulunun 22.05 kararı uzaklaştırmadır; kınama itiraz kurulunun
    kararıdır. EK-1 / Form-18 yeniden üretilince kurulun cezasını basar."""
    case, student, decision = _reduced_case()
    _generate(case, document_type, student_id=student.pk)
    assert ctx["decision"].get_penalty_type_display() == _SUSPENSION
    assert ctx["decision"].penalty_type == PenaltyType.SHORT_TERM_SUSPENSION
    assert ctx["statute_label"] == "Madde 164/2"
    assert ctx["decision"].suspension_days == 5
    assert ctx["board_penalty_display"] == _SUSPENSION_5
    assert "Kınama" in ctx["penalty_change_note"]
    # Karar kaydının kendisi değişmez (puan ve yürürlük güncel cezadan türer).
    decision.refresh_from_db()
    assert decision.penalty_type == PenaltyType.REPRIMAND
    assert ctx["decision"].decision_no == decision.decision_no


@pytest.mark.parametrize("recipient", ["student", "parent"])
def test_ceza_tebligi_itirazla_degisen_kararda_yururlukteki_cezayi_basar(
    ctx: dict[str, Any], recipient: str
) -> None:
    """Gözden geçirme E2 — Form-14 (öğrenci) ve Form-15 (veli) YÜRÜRLÜKTEKİ cezayı
    tebliğ eder; bağlamdaki karar kaydın kendisidir, iki suret aynı cezayı taşır."""
    case, student, decision = _reduced_case()
    _generate(case, DocumentType.PENALTY_NOTICE, student_id=student.pk, recipient=recipient)
    assert ctx["decision"] == decision
    assert ctx["decision"].get_penalty_type_display() == "Kınama"
    assert ctx["decision"].suspension_days is None
    assert ctx["statute_label"] == doc_engine.statute_label(decision)
    # Kurulun verdiği ceza yalnız notta anlatılır; yön: kurul X verdi → Y'ye değişti.
    note = ctx["penalty_change_note"]
    assert note.startswith("İşbu yazı ile tebliğ edilen ceza yürürlükteki cezadır.")
    assert f'verdiği "{_SUSPENSION_5}" cezası' in note
    assert '"Kınama" olarak değiştirilmiştir.' in note


@pytest.mark.parametrize("recipient", ["student", "parent"])
def test_ceza_tebligi_onayda_degisen_kararda_yururlukteki_cezayi_basar(
    ctx: dict[str, Any], recipient: str
) -> None:
    """Kurul okul değiştirme verdi, ilçe kurulu onayda 5 gün uzaklaştırmaya çevirdi:
    tebliğ edilen (ve itiraz süresi işleyen) ceza uzaklaştırmadır."""
    case, student = _approval_modified_case()
    _generate(case, DocumentType.PENALTY_NOTICE, student_id=student.pk, recipient=recipient)
    assert ctx["decision"] == case.decisions.get()
    assert ctx["decision"].penalty_type == PenaltyType.SHORT_TERM_SUSPENSION
    assert ctx["decision"].suspension_days == 5
    assert ctx["statute_label"] == "Madde 164/2"
    assert 'verdiği "Okul değiştirme" cezası' in ctx["penalty_change_note"]


def test_ceza_tebligi_ogrenci_ve_veli_suretleri_ayni_cezayi_tasir() -> None:
    """Gerçek PDF: iki surette de yürürlükteki ceza ve AYNI değişiklik notu.

    Kullanıcı kararı 14.11.2026 — S3: not eskiden yalnız Form-15'teydi (Form-14 AYNEN
    şablondu); karar Form-14'ü istisna listesine aldı, test buna göre güncellendi."""
    case, student, _decision = _reduced_case()
    texts: dict[str, str] = {}
    for recipient in ("student", "parent"):
        pdf, _ = doc_engine.generate_document(
            case,
            document_type=DocumentType.PENALTY_NOTICE,
            generated_on=date(2026, 6, 5),
            student_id=student.pk,
            recipient=recipient,
            log=False,
        )
        texts[recipient] = _pdf_text(pdf)
    for text in texts.values():
        assert '"Kınama" cezası verilmiştir' in text
        assert "(5 gün)" not in text
        assert "İşbu yazı ile tebliğ edilen ceza yürürlükteki cezadır." in text
        assert f'verdiği "{_SUSPENSION_5}" cezası' in text
        assert '"Kınama" olarak değiştirilmiştir.' in text


def test_ceza_tebligi_degismemis_kararda_not_yok(ctx: dict[str, Any]) -> None:
    student = StudentFactory()
    case = _case(student)
    decision = services.record_decision(
        case,
        student_id=student.pk,
        penalty_type=PenaltyType.REPRIMAND,
        decision_date=date(2026, 5, 22),
    )
    _generate(case, DocumentType.PENALTY_NOTICE, student_id=student.pk)
    assert ctx["decision"] == decision
    assert ctx["penalty_change_note"] == ""


def test_degismemis_kararda_baglam_kararin_kendisidir(ctx: dict[str, Any]) -> None:
    student = StudentFactory()
    case = _case(student)
    decision = services.record_decision(
        case,
        student_id=student.pk,
        penalty_type=PenaltyType.REPRIMAND,
        decision_date=date(2026, 5, 22),
    )
    _generate(case, DocumentType.COMMITTEE_DECISION, student_id=student.pk)
    assert ctx["decision"] == decision
    assert ctx["penalty_change_note"] == ""


def test_degisen_ceza_gercek_pdfte_kurulun_verdigi_cezadir() -> None:
    """Vekil karar nesnesi AYNEN şablonlarla (EK-1, üst kurul tebliği) sorunsuz basılır."""
    case, student, _decision = _reduced_case()
    services.create_committee(school_year_id=SchoolYearFactory().pk, chair_id=PersonnelFactory().pk)
    ek1, _ = doc_engine.generate_document(
        case,
        document_type=DocumentType.COMMITTEE_DECISION,
        generated_on=date(2026, 6, 5),
        student_id=student.pk,
        log=False,
    )
    text = _pdf_text(ek1)
    assert f"{_SUSPENSION} (Madde 164/2) — 5 gün" in text
    assert "Kınama" not in text
    notice, _ = doc_engine.generate_document(
        case,
        document_type=DocumentType.BOARD_DECISION_NOTICE,
        generated_on=date(2026, 6, 5),
        student_id=student.pk,
        notice_kind="appeal_result",
        result_summary="Ceza kınamaya çevrilmiştir.",
        log=False,
    )
    text = _pdf_text(notice)
    assert f'"{_SUSPENSION}" cezasına karşı yapılan itiraz' in text
    assert "değiştirilmiştir" in text


def test_itirazla_degisen_okul_degistirme_onayda_degismis_sayilmaz(ctx: dict[str, Any]) -> None:
    """Okul değiştirme ilçece AYNEN onaylanıp il kurulunca itirazda değiştirilirse
    değişikliği yapan merci itiraz kuruludur (onay mercii çıkarımı yanıltmamalı)."""
    student = StudentFactory()
    case = _case(student)
    decision = services.record_decision(
        case,
        student_id=student.pk,
        penalty_type=PenaltyType.SCHOOL_CHANGE,
        decision_date=date(2026, 5, 22),
    )
    services.set_decision_approval(
        decision, approval_status="APPROVED", approved_on=date(2026, 5, 28)
    )
    services.notify_decision(decision, notified_on=date(2026, 5, 28))
    appeal = services.file_appeal(decision, filed_on=date(2026, 5, 29), filed_by_role="PARENT")
    services.resolve_appeal(
        appeal,
        result="REDUCED",
        resulted_on=date(2026, 6, 8),
        new_penalty_type=PenaltyType.SHORT_TERM_SUSPENSION,
        new_suspension_days=5,
    )
    _generate(case, DocumentType.COMMITTEE_DECISION, student_id=student.pk)
    assert ctx["decision"].get_penalty_type_display() == "Okul değiştirme"
    assert "itiraz üzerine İl öğrenci disiplin kurulunca" in ctx["penalty_change_note"]
    assert "onay aşamasında" not in ctx["penalty_change_note"]


def _approval_modified_case() -> tuple[DisciplineCase, Any]:
    """Okul değiştirme → ilçe kurulu onayda 5 gün uzaklaştırmaya çevirir (md. 200/1-a)."""
    student = StudentFactory()
    case = _case(student)
    decision = services.record_decision(
        case,
        student_id=student.pk,
        penalty_type=PenaltyType.SCHOOL_CHANGE,
        decision_date=date(2026, 5, 22),
    )
    services.set_decision_approval(
        decision,
        approval_status="APPROVED",
        approved_on=date(2026, 5, 28),
        modified_penalty_type=PenaltyType.SHORT_TERM_SUSPENSION,
        modified_suspension_days=5,
    )
    return case, student


def test_onayda_degisen_ceza_ust_kurul_tebliginde_okul_kararidir(ctx: dict[str, Any]) -> None:
    """Bulgu 3 — okul kurulu okul değiştirme verdi (md. 164/3, onay md. 169/2-b);
    belge kurulun verdiği cezayı uzaklaştırma diye yazmamalı."""
    case, student = _approval_modified_case()
    _generate(
        case,
        DocumentType.BOARD_DECISION_NOTICE,
        student_id=student.pk,
        notice_kind="approval",
        board_outcome="MODIFIED",
        result_summary="Okul değiştirme 5 gün uzaklaştırmaya çevrilmiştir.",
    )
    assert ctx["decision"].get_penalty_type_display() == "Okul değiştirme"
    assert ctx["decision"].penalty_type == PenaltyType.SCHOOL_CHANGE
    assert ctx["statute_label"] == "Madde 164/3"
    assert ctx["current_penalty_display"] == _SUSPENSION_5


def test_onayda_degisen_ceza_onaya_sevk_yazisinda_okul_kararidir(ctx: dict[str, Any]) -> None:
    case, student = _approval_modified_case()
    _generate(case, DocumentType.APPROVAL_REQUEST_LETTER, student_id=student.pk)
    assert ctx["decision"].get_penalty_type_display() == "Okul değiştirme"
    assert ctx["statute_label"] == "Madde 164/3"


def test_ceza_gunleri_tebligi_guncel_cezayi_kullanir(ctx: dict[str, Any]) -> None:
    """Form-16/17 fiilen çekilecek (güncel) cezayı basar — kurulun ilk kararını değil."""
    case, student = _approval_modified_case()
    decision = case.decisions.get()
    services.notify_decision(decision, notified_on=date(2026, 5, 28))
    decision.enforcement_start_date = date(2026, 6, 15)
    decision.save(update_fields=["enforcement_start_date"])
    _generate(
        case,
        DocumentType.PENALTY_DAYS_NOTICE,
        student_id=student.pk,
        generated_on=date(2026, 6, 12),
    )
    assert ctx["decision"].penalty_type == PenaltyType.SHORT_TERM_SUSPENSION


# ---------------------------------------------------------------------------
# Bulgu 31, 58 — karar defteri (dosya görüşme tutanağı) — KULLANICI KARARI S1
#
# Gözden geçirme E3 bu iki davranışı (karar numarası sırası + uzaklaştırmada "— N gün")
# OYS paritesi (CLAUDE.md §1/3) gerekçesiyle geri almış, testi "OYS ile aynı" diye
# sabitlemişti. Kullanıcı 14.11.2026'da karar verdi (S1): İKİSİ DE uygulanır, bilinçli
# sapma olarak yazılır → test yeniden tersine çevrildi. Ayrıntılı testler:
# test_kararlar_evrak.py (test_s1_*).
# ---------------------------------------------------------------------------
def _case_review_meeting(case: DisciplineCase, year: Any) -> Any:
    return services.create_council_meeting(
        school_year_id=year.pk,
        council_type="DISCIPLINE",
        meeting_date=date(2026, 5, 22),
        attendees=[{"person_name": "BAŞKAN", "attendee_role": "VOTING_MEMBER", "is_chair": True}],
        minutes_type="CASE_REVIEW",
        discipline_case_id=case.pk,
    )


def test_karar_defteri_karar_numarasi_sirasi_ve_gun_sayisi() -> None:
    """Kullanıcı kararı 14.11.2026 — S1 (eski adı `…_oys_ile_ayni_sira_ve_etiket`, tersine
    döndü): kararlar karar numarası sırasıyla, uzaklaştırma gün sayısıyla basılır."""
    year = SchoolYearFactory()
    a, b = StudentFactory(), StudentFactory()
    case = _case(a, b)
    first = services.record_decision(
        case, student_id=a.pk, penalty_type=PenaltyType.REPRIMAND, decision_date=date(2026, 5, 22)
    )
    second = services.record_decision(
        case,
        student_id=b.pk,
        penalty_type=PenaltyType.SHORT_TERM_SUSPENSION,
        suspension_days=3,
        decision_date=date(2026, 5, 22),
    )
    rows = doc_engine._council_minutes_context(_case_review_meeting(case, year))["case_decisions"]
    # (a) Sıra karar numarasıdır — selector/model sırası (yeniden eskiye) DEĞİL.
    assert [r["decision_no"] for r in rows] == [first.decision_no, second.decision_no]
    assert [r["full_name"] for r in rows] == [a.full_name, b.full_name]
    assert [d.decision_no for d in selectors.decisions_for_case(case)] != [
        r["decision_no"] for r in rows
    ]
    # (b) Uzaklaştırmada gün sayısı basılır; gün sayısı olmayan cezada etiket yalındır.
    assert rows[0]["penalty_display"] == "Kınama"
    assert rows[1]["penalty_display"] == f"{_SUSPENSION} — 3 gün"
    for row, decision in zip(rows, (first, second), strict=True):
        assert row["statute_label"] == doc_engine.statute_label(decision)


def test_karar_defterinde_itirazla_degisen_ceza_kurulun_verdigidir() -> None:
    """Ceza sonradan değiştiyse basılan ceza kurulun verdiğidir — gün sayısıyla (S1)."""
    case, _student, _decision = _reduced_case()
    year = SchoolYearFactory()
    row = doc_engine._council_minutes_context(_case_review_meeting(case, year))["case_decisions"][0]
    assert row["penalty_display"] == _SUSPENSION_5
    assert row["statute_label"] == "Madde 164/2"


# ---------------------------------------------------------------------------
# Bulgu 44, 53, 69 — kütük / dizi pusulası başlıkları
# ---------------------------------------------------------------------------
def test_surume_gore_varsayilan_baslik_ve_dosya_adi(ctx: dict[str, Any]) -> None:
    student = StudentFactory()
    case = _case(student)
    services.create_extension(case, requested_days=3, reason="x", decided_on=date(2026, 5, 25))
    record = _generate(case, DocumentType.DEADLINE_EXTENSION, variant="record")
    petition = _generate(case, DocumentType.DEADLINE_EXTENSION, variant="petition")
    assert "Form-12" in record.title and "Form-13" in petition.title
    assert record.stored_filename != petition.stored_filename
    # Variant verilmezse türün varsayılan (ilk) sürümünün başlığı.
    assert _generate(case, DocumentType.DEADLINE_EXTENSION).title == record.title

    # Kullanıcı kararı 14.11.2026 — S12: kurula sevkli dosyada veli görüşme tutanağı
    # yalnız öğrencinin uyarı kaydı varsa üretilir.
    _warn(case, student)
    titles = {
        v: _generate(case, DocumentType.PARENT_MEETING, student_id=student.pk, variant=v).title
        for v in ("invite", "meeting", "no_show")
    }
    assert len(set(titles.values())) == 3
    assert "Davet" in titles["invite"] and "Gelmedi" in titles["no_show"]

    services.create_precaution(
        case, student_id=student.pk, start_date=date(2026, 5, 20), requested_days=3
    )
    mem = {
        v: _generate(case, DocumentType.PRECAUTION_MEM_LETTER, student_id=student.pk, variant=v)
        for v in ("info", "extension")
    }
    assert mem["info"].title != mem["extension"].title


def test_aliciya_gore_varsayilan_baslik(ctx: dict[str, Any]) -> None:
    student = StudentFactory()
    case = _case(student)
    _warn(case, student)  # S12: kurula sevkli dosyada Form-02 için uyarı kaydı şart
    ogrenci = _generate(
        case, DocumentType.WARNING_LETTER, student_id=student.pk, behavior_summary="x"
    )
    veli = _generate(
        case,
        DocumentType.WARNING_LETTER,
        student_id=student.pk,
        behavior_summary="x",
        recipient="parent",
    )
    assert ogrenci.title != veli.title
    assert "Veli" in veli.title
    assert ogrenci.stored_filename != veli.stored_filename
    # Kullanıcının yazdığı başlık her zaman önceliklidir.
    ozel = _generate(
        case,
        DocumentType.WARNING_LETTER,
        student_id=student.pk,
        behavior_summary="x",
        title="Özel başlık",
    )
    assert ozel.title == "Özel başlık"


def test_dizi_pusulasinda_elle_girilen_baslik_kaybolmaz() -> None:
    """Bulgu 44/53 — "kimden" girilen harici evrakın başlığı pusulada görünür; katılımcı
    belgelerinde (ifade/savunma/çağrı) kısa "kimden" biçimi korunur (Tur 140)."""
    student = StudentFactory(first_name="ÇAĞRI", last_name="IŞIKGÖZ")
    case = _case(student)
    services.log_generated_document(
        case,
        document_type=DocumentType.OTHER,
        title="Nöbetçi öğretmen olay tutanağı",
        generated_on=date(2026, 5, 19),
        source_label="Tanık",
        source_name="Çiğdem Özışık",
    )
    participant = case.participants.get(role=ParticipantRole.ACCUSED)
    doc_engine.generate_document(
        case,
        document_type=DocumentType.STATEMENT_RECORD,
        generated_on=date(2026, 5, 20),
        participant_id=participant.pk,
    )
    pdf, _ = doc_engine.generate_document(
        case, document_type=DocumentType.INDEX_SHEET, generated_on=date(2026, 5, 26), log=False
    )
    text = _pdf_text(pdf)
    assert "Nöbetçi öğretmen olay tutanağı" in text
    assert "anık: Çiğdem Özışık" in text  # pypdf "T anık" diye ayırır (harf aralığı)
    assert "Hakkında İşlem Yapılan: ÇAĞRI IŞIKGÖZ" in text
    assert "İfade Tutanağı —" not in text  # katılımcı belgesinde başlık eklenmez
    # Kütük kaydı değişmez — yalnız pusula görünümü.
    other = case.generated_documents.get(document_type=DocumentType.OTHER)
    assert other.source_label == "Tanık"


def test_md195_tespit_tutanagi_savunmalar_altinda_listelenmez() -> None:
    """Bulgu 53 — md. 195 tespit tutanağı savunma değildir; kendi kategorisinde durur."""
    labels = {dt: label for label, types in doc_engine.DOC_CATEGORIES for dt in types}
    assert labels[DocumentType.NON_COMPLIANCE_RECORD] != labels[DocumentType.DEFENSE_RECORD]
    assert "195" in labels[DocumentType.NON_COMPLIANCE_RECORD]


# ---------------------------------------------------------------------------
# Bulgu 74 — elle sıralamadan sonra üretilen belgenin yeri
# ---------------------------------------------------------------------------
def _titles_in_order(case: DisciplineCase) -> list[str]:
    from apps.disiplin import selectors

    return [d.title for d in selectors.document_timeline(case)]


def test_elle_siralamadan_sonra_uretilen_belge_turunun_sonuna_duser() -> None:
    student = StudentFactory()
    case = _case(student)

    def log(document_type: str, title: str) -> Any:
        return services.log_generated_document(
            case, document_type=document_type, title=title, generated_on=date(2026, 5, 20)
        )

    docs = [
        log(DocumentType.STATEMENT_CALL, "çağrı-1"),
        log(DocumentType.STATEMENT_RECORD, "ifade-1"),
        log(DocumentType.STATEMENT_RECORD, "ifade-2"),
        log(DocumentType.COMMITTEE_DECISION, "ek1-1"),
        log(DocumentType.PENALTY_NOTICE, "teblig-1"),
        log(DocumentType.PENALTY_NOTICE, "teblig-2"),
        log(DocumentType.OTHER, "diger-1"),
    ]
    # Kullanıcı ilk iki belgenin yerini değiştirir → sort_order 10, 20, … olur.
    order = [docs[1].pk, docs[0].pk, *[d.pk for d in docs[2:]]]
    services.reorder_documents(case, ordered_ids=order)

    log(DocumentType.COMMITTEE_DECISION, "ek1-2")  # kanonik 90
    log(DocumentType.PENALTY_DAYS_NOTICE, "gunler-1")  # kanonik 110 — türünün ilki
    log(DocumentType.STATEMENT_RECORD, "ifade-3")  # kanonik 30
    assert _titles_in_order(case) == [
        "ifade-1",
        "çağrı-1",
        "ifade-2",
        "ifade-3",
        "ek1-1",
        "ek1-2",
        "teblig-1",
        "teblig-2",
        "gunler-1",
        "diger-1",
    ]


def test_siralanmamis_dosyada_kanonik_sira_korunur() -> None:
    student = StudentFactory()
    case = _case(student)
    record = services.log_generated_document(
        case,
        document_type=DocumentType.COMMITTEE_DECISION,
        title="ek1",
        generated_on=date(2026, 5, 20),
    )
    again = services.log_generated_document(
        case,
        document_type=DocumentType.COMMITTEE_DECISION,
        title="ek1",
        generated_on=date(2026, 5, 21),
    )
    assert record.sort_order == again.sort_order == 90


# ---------------------------------------------------------------------------
# Bulgu 24 — md. 197 iade yazısı ilçeye sevkten sonra (güvenli kısım)
# ---------------------------------------------------------------------------
def test_iade_yazisi_sevkten_sonra_tarih_uydurmaz(ctx: dict[str, Any]) -> None:
    """REFER `returned_at`'i sevk tarihiyle ezer; ilk iade tarihi kayıtta KALMAZ.

    Gözden geçirme E4: önceki tur iade tarihini kütükteki iade yazısının ÜRETİM
    tarihinden alıyordu — güvenilir değil (yazı başka bir tarihle ya da sonradan
    üretilmiş olabilir). Eski test (`…_iade_tarihini_korur`) bu yüzden gevşetildi:
    sevkten sonra tarih UYDURULMAZ, noktalı basılır; sevk tarihi de iade tarihi diye
    basılmaz."""
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
    # İade yazısı iade gününden FARKLI bir üretim tarihiyle kütüğe girer.
    _generate(
        case, DocumentType.RETURN_LETTER, student_id=student.pk, generated_on=date(2026, 5, 23)
    )
    # Sevkten önce iade tarihi kayıttadır: üretim tarihi değil `returned_at` basılır.
    assert ctx["decision"].returned_at == date(2026, 5, 21)
    assert ctx["return_date_unknown"] is False
    assert '<td class="label">Tarih</td><td>21.05.2026</td>' in _html(ctx)
    services.record_principal_review(
        decision, action="REFER", reason="Kurul ısrar etti.", decided_on=date(2026, 5, 26)
    )
    _generate(
        case, DocumentType.RETURN_LETTER, student_id=student.pk, generated_on=date(2026, 5, 27)
    )
    assert ctx["return_date_unknown"] is True
    assert ctx["decision"].returned_at is None
    assert ctx["return_reason_text"] == "Ceza hafif."
    html = _html(ctx)
    assert '<td class="label">Tarih</td><td>…/…/202…</td>' in html
    for wrong in ("23.05.2026", "26.05.2026", "27.05.2026"):  # kütük / sevk / üretim
        assert wrong not in html
    # İlçe yazısı sevk tarihini basar; İlgi (b) iade yazısı tarihi noktalı kalır.
    _generate(
        case,
        DocumentType.DISTRICT_REFERRAL_LETTER,
        student_id=student.pk,
        generated_on=date(2026, 5, 26),
    )
    assert ctx["decision"].returned_at == date(2026, 5, 26)
    assert ctx["return_letter_date"] is None
    assert "b) Müdürlüğümüzün …/…/202… tarihli kurula iade yazısı" in _html(ctx)


# ---------------------------------------------------------------------------
# Bulgu 77, 80 — Onur Kurulu Teklif Tutanağı
# ---------------------------------------------------------------------------
def test_onur_teklif_tutanagi_toplanti_tarihi_ve_ikinci_baskan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    year = SchoolYearFactory()
    ensure_terms(year)
    board = services.create_honor_board(school_year_id=year.pk, chair_id=PersonnelFactory().pk)
    uye = StudentFactory(first_name="MÜGE", last_name="ÜNLÜOĞLU", class_level=11)
    assembly_member = services.add_general_assembly_member(
        school_year_id=year.pk, student_id=uye.pk, effective_from=year.start_date
    )
    member = services.add_honor_board_member(
        board,
        student_id=uye.pk,
        grade_level=11,
        is_second_chair=True,
        assembly_member_id=assembly_member.pk,
    )
    meeting = services.create_council_meeting(
        school_year_id=year.pk,
        council_type="HONOR",
        meeting_date=date(2026, 5, 25),
        attendees=[
            {"person_name": "ONUR BAŞKANI", "attendee_role": "VOTING_MEMBER", "is_chair": True},
            {
                "person_name": "MÜGE ÜNLÜOĞLU",
                "attendee_role": "VOTING_MEMBER",
                "is_chair": False,
                "member_student_id": uye.pk,
            },
        ],
    )
    captured: dict[str, Any] = {}

    def fake(template: str, context: dict[str, Any]) -> bytes:
        captured.clear()
        captured.update(context)
        return b"%PDF-sahte"

    monkeypatch.setattr(honor_documents, "render_pdf", fake)
    honor_documents.render_recommendation_record([], board=board, meeting=meeting)
    # Bulgu 77: uygun görüş toplantısının tarihi ve defter numarası BAĞLAMDA hazırdır;
    # şablona (honor_recommendation_record.html — AYNEN) basılması kullanıcı kararıdır.
    assert captured["meeting_date"] == date(2026, 5, 25)
    assert captured["meeting_no"] == meeting.meeting_no_display
    assert captured["members"][0]["is_second_chair"] is True

    # Bulgu 80: üyelik sonradan sonlansa da aynı toplantının belgesi değişmez.
    services.remove_honor_board_member(member)
    board.refresh_from_db()
    honor_documents.render_recommendation_record([], board=board, meeting=meeting)
    assert captured["members"][0]["is_second_chair"] is True

    # Toplantıdan ÖNCE sona ermiş üyelik ise ikinci başkan sayılmaz.
    member.effective_until = date(2026, 5, 1)
    member.save(update_fields=["effective_until"])
    honor_documents.render_recommendation_record([], board=board, meeting=meeting)
    assert captured["members"][0]["is_second_chair"] is False
