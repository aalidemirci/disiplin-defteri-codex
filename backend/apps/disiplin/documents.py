"""Disiplin evrak üretim motoru — WeasyPrint (OYS `ogrenci_isleri/documents.py` uyarlaması).

Tasarım §4.4 "7 dokunuş" DIŞINDA kod OYS ile birebirdir: (1) import kökleri,
(2) `_student_context` düz modelden, (3) `_common_context` antet kimliği
`apps.okul.services.setup`'tan, (4) `_parent_context` guardian alanlarından,
(5) `_suspension_dates` yerel iş günü yüklemi, (6) get_student ikameleri
(okul selectors + düz sınıf/no alanları), (7) `generate_document` user/ip'siz.
Dal A/B kısıtı + Form-16/17 kesinleşme kilidi AYNEN KORUNUR.

`raporlar` modülüne DOKUNMADAN (ADR-0002): ORTAK `templates/documents/base.html`
(Tur 99, paylaşılan modern tasarım) + modül form şablonları. Antet
`shared.letterhead`'den. WeasyPrint ağır bağımlılıktır (pango/cairo) → modül düzeyinde değil,
`render_pdf` içinde TEMBEL yüklenir; böylece app import'u (migration/admin) PDF
bağımlılıkları yokken de güvenlidir. Türkçe karakter: base.html `DejaVu Sans`
(Dockerfile fonts-dejavu), raporlar'la aynı yaklaşım.

Vizyon (plan: .claude/plans/disiplin-evrak-uretimi-ve-is-akisi.md):
  - EK-1 kurul kararı + dizi pusulası → TAM-OTO (DB'den otomatik doldurulur).
  - Ceza tebliği → ön-doldurulmuş (mevcut karar verisiyle; elle tamamlanır).
  - Üretilen izlenebilir belge → GeneratedDocument kütüğüne yazılır (Faz C servisi).
  - Rehberlik görüşme formu → no-trace (kütüğe yazılmaz; `log=False`).

KVKK: EK-1 öğrenci TCKN içerir (resmî zorunluluk, md. EK-1 dipnotu) → üretim hassas
okumadır; view katmanı SENSITIVE_READ düşer. PDF içeriği DB'de SAKLANMAZ (yalnız kütük).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import date
from typing import Any

from django.conf import settings
from django.template.loader import render_to_string
from django.utils import timezone

from apps.disiplin import selectors, services
from apps.disiplin.models import (
    AppealResult,
    ApprovalAuthority,
    CaseStage,
    DisciplineCase,
    DocumentType,
    GeneratedDocument,
    ParticipantRole,
    PenaltyType,
    PrincipalDecision,
)
from shared.letterhead import letterhead_context

# Ceza türü → MEB Ortaöğretim Kurumları Yönetmeliği fiil maddesi (md. 164 fıkraları;
# data/mevzuat'tan DOĞRULANDI: 164/1 kınama, 164/2 kısa süreli uzaklaştırma,
# 164/3 okul değiştirme, 164/4 örgün eğitim dışına çıkarma). statute_ref boşsa türetilir.
PENALTY_STATUTE: dict[str, str] = {
    PenaltyType.REPRIMAND: "Madde 164/1",
    PenaltyType.SHORT_TERM_SUSPENSION: "Madde 164/2",
    PenaltyType.SCHOOL_CHANGE: "Madde 164/3",
    PenaltyType.EXPULSION: "Madde 164/4",
    # Ceza verilmesine yer olmadığı: kurul karara bağlamak zorunda (md. 191), ceza
    # vermek zorunda değil (Tur 181, Talep 1b). md. 164 fiil maddesi uygulanmaz.
    PenaltyType.NO_PENALTY: "Madde 191",
}


def statute_label(decision: Any) -> str:
    """Ceza maddesini insan-okunur etikete çevirir (boş döndürmez — form için).

    Öncelik: `decision.statute_ref` (ham çapa '#madde-164' → 'Madde 164');
    boşsa ceza türünden `PENALTY_STATUTE` ile türet; karar yoksa 'Madde ……'.
    """
    if decision is None:
        return "Madde ……"
    ref = (getattr(decision, "statute_ref", "") or "").strip()
    if ref:
        m = re.search(r"madde-?(\d+)", ref)
        if m:
            return f"Madde {m.group(1)}"
        return ref
    return PENALTY_STATUTE.get(getattr(decision, "penalty_type", ""), "Madde ……")


# Tebliğ alıcısı (öğrenci / veli) — Form-14↔15, Form-16↔17 ikizlerini ayırır.
RECIPIENT_STUDENT = "student"
RECIPIENT_PARENT = "parent"
VALID_RECIPIENTS: frozenset[str] = frozenset({RECIPIENT_STUDENT, RECIPIENT_PARENT})

# Tek-alıcılı belgeler → şablon yolu (recipient yok sayılır).
DOC_TEMPLATES: dict[str, str] = {
    DocumentType.COMMITTEE_DECISION: "disiplin/documents/ek1_committee_decision.html",
    DocumentType.INDEX_SHEET: "disiplin/documents/index_sheet.html",
    DocumentType.APPEAL_LETTER: "disiplin/documents/appeal_letter.html",
    DocumentType.PRECAUTION_NOTICE: "disiplin/documents/precaution_notice.html",
    # Dal B ifade/savunma/bilgi formları (Tur 106) — kanonik metin
    # data/sablonlar/disiplin-kurulu/form-03..11. Ön-doldurulmuş, gövde elle.
    DocumentType.STATEMENT_CALL: "disiplin/documents/statement_call.html",  # Form-3
    DocumentType.STATEMENT_RECORD: "disiplin/documents/statement_record.html",  # Form-4/5/6
    DocumentType.INFO_GATHERING: "disiplin/documents/info_gathering.html",  # Form-7/8
    DocumentType.DEFENSE_CALL: "disiplin/documents/defense_call.html",  # Form-9
    DocumentType.MEETING_CALL: "disiplin/documents/meeting_call.html",  # Form-10
    DocumentType.DEFENSE_RECORD: "disiplin/documents/defense_record.html",  # Form-11
}

# Alıcıya göre değişen belgeler (öğrenci sürümü varsayılan; veli ayrı şablon).
DOC_TEMPLATES_BY_RECIPIENT: dict[str, dict[str, str]] = {
    DocumentType.PENALTY_NOTICE: {
        RECIPIENT_STUDENT: "disiplin/documents/penalty_notice.html",  # Form-14
        RECIPIENT_PARENT: "disiplin/documents/penalty_notice_parent.html",  # Form-15
    },
    DocumentType.PENALTY_DAYS_NOTICE: {
        RECIPIENT_STUDENT: "disiplin/documents/penalty_days_notice.html",  # Form-16
        RECIPIENT_PARENT: "disiplin/documents/penalty_days_notice_parent.html",  # Form-17
    },
    # Müdür uyarısı (Tur 213, talep 3b): öğrenciye Form-02 + veliye bilgilendirme
    # (türetilmiş form — resmî MEB karşılığı yok; md. 157/7 dayanak).
    DocumentType.WARNING_LETTER: {
        RECIPIENT_STUDENT: "disiplin/documents/warning_letter.html",  # Form-02
        RECIPIENT_PARENT: "disiplin/documents/warning_letter_parent.html",
    },
    # Üst kurul kararı tebliği (Tur 220, talep 3): onay (md. 169/2) / itiraz sonucu
    # (md. 169/3-4) — senaryo şablon-içi dal (notice_kind), alıcı ikiz şablon.
    DocumentType.BOARD_DECISION_NOTICE: {
        RECIPIENT_STUDENT: "disiplin/documents/board_decision_notice.html",
        RECIPIENT_PARENT: "disiplin/documents/board_decision_notice_parent.html",
    },
}

# Variant'a göre AYRI ŞABLON üreten belgeler (Tur 110) — INFO_GATHERING gövde-variant
# (tek şablon) deseninden FARKLI: süre uzatma çifti iki ayrı belgedir (F-12 kurul ara
# karar tutanağı / F-13 müdürlüğe dilekçe). Varsayılan: VARIANT_RECORD (F-12).
VARIANT_RECORD = "record"
VARIANT_PETITION = "petition"
DOC_TEMPLATES_BY_VARIANT: dict[str, dict[str, str]] = {
    DocumentType.DEADLINE_EXTENSION: {
        VARIANT_RECORD: "disiplin/documents/deadline_extension_record.html",  # Form-12
        VARIANT_PETITION: "disiplin/documents/deadline_extension_petition.html",  # Form-13
    },
}

# Belge türü → varsayılan başlık (kütük kaydında kullanılır).
DOC_TITLES: dict[str, str] = {
    DocumentType.COMMITTEE_DECISION: "EK-1 Okul Öğrenci Ödül ve Disiplin Kurulu Kararı",
    DocumentType.INDEX_SHEET: "Dizi Pusulası",
    DocumentType.PENALTY_NOTICE: "Disiplin Cezası Tebliği",
    DocumentType.PENALTY_DAYS_NOTICE: "Disiplin Ceza Günleri Tebliği",
    DocumentType.APPEAL_LETTER: "İl/İlçe İtiraz Yazısı",
    DocumentType.WARNING_LETTER: "Müdür Uyarısı Yazısı",
    DocumentType.PRECAUTION_NOTICE: "Geçici Uzaklaştırma (Tedbir) Bildirimi",
    DocumentType.STATEMENT_CALL: "İfadeye Çağrı Pusulası",
    DocumentType.STATEMENT_RECORD: "İfade Tutanağı",
    DocumentType.INFO_GATHERING: "Bilgi Toplama Formu",
    DocumentType.DEFENSE_CALL: "Savunmaya Çağrı",
    DocumentType.MEETING_CALL: "Kurul Toplantı Çağrısı",
    DocumentType.DEFENSE_RECORD: "Savunma Tutanağı",
    DocumentType.DEADLINE_EXTENSION: "Süre Uzatma (Ara Karar / Dilekçe)",
    DocumentType.BOARD_DECISION_NOTICE: "Üst Kurul Kararı Tebliği",
}

# Öğrenci-özgü belgeler (öğrenci zorunlu) — dizi pusulası HARİÇ hepsi öğrenciye özgü.
STUDENT_REQUIRED: frozenset[str] = frozenset(
    {
        DocumentType.COMMITTEE_DECISION,
        DocumentType.PENALTY_NOTICE,
        DocumentType.PENALTY_DAYS_NOTICE,
        DocumentType.APPEAL_LETTER,
        DocumentType.WARNING_LETTER,
        DocumentType.PRECAUTION_NOTICE,
        DocumentType.BOARD_DECISION_NOTICE,
    }
)

# Katılımcı-özgü belgeler (Tur 106) — hedef kişi DisciplineParticipant'tan seçilir
# (suçlanan/mağdur/tanık × öğrenci/personel/dış); rol başlığı/etiketi belirler. MEETING_CALL
# katılımcı GEREKTİRMEZ (kurul üyelerine yazılır). Geçici tarih/saat/yer DB'ye yazılmaz.
PARTICIPANT_REQUIRED: frozenset[str] = frozenset(
    {
        DocumentType.STATEMENT_CALL,
        DocumentType.STATEMENT_RECORD,
        DocumentType.INFO_GATHERING,
        DocumentType.DEFENSE_CALL,
        DocumentType.DEFENSE_RECORD,
    }
)

# Belge türü → dizi pusulasında varsayılan KANONİK süreç sırası (Form-0 kontrol formu
# + is-akisi.md akışı; Tur 103). Küçük = önce. Aralıklı (×10) → araya ekleme kolay.
# Tedbir (md.175) acele/erken; Dal A uyarı; Dal B ifade→bilgi→savunma→kurul→karar;
# tebliğ→ceza günleri→itiraz; dizi pusulası kapak (sonda); OTHER/manuel en sonda.
CANONICAL_DOC_ORDER: dict[str, int] = {
    DocumentType.PRECAUTION_NOTICE: 5,  # tedbir (md. 175, acele)
    DocumentType.WARNING_LETTER: 10,  # müdür uyarısı Form-01/02 (md. 157/7)
    DocumentType.STATEMENT_CALL: 20,  # ifadeye çağrı Form-3
    DocumentType.STATEMENT_RECORD: 30,  # ifade tutanağı Form-4/5/6
    DocumentType.INFO_GATHERING: 40,  # bilgi toplama Form-7/8
    DocumentType.DEFENSE_CALL: 50,  # savunmaya çağrı Form-9
    DocumentType.MEETING_CALL: 60,  # kurul toplantı çağrısı Form-10
    DocumentType.DEFENSE_RECORD: 70,  # savunma tutanağı Form-11
    DocumentType.DEADLINE_EXTENSION: 80,  # süre uzatma Form-12/13
    DocumentType.COMMITTEE_DECISION: 90,  # EK-1 kurul kararı
    DocumentType.PENALTY_NOTICE: 100,  # ceza tebliği Form-14/15
    DocumentType.PENALTY_DAYS_NOTICE: 110,  # ceza günleri tebliği Form-16/17
    DocumentType.APPEAL_LETTER: 120,  # il/ilçe itiraz Form-18
    DocumentType.BOARD_DECISION_NOTICE: 125,  # üst kurul kararı tebliği (Tur 220)
    DocumentType.INDEX_SHEET: 900,  # dizi pusulası (kapak — sonda)
    DocumentType.OTHER: 1000,  # diğer/manuel (en sonda; elle taşınır)
}

# Kanonik sırada tanımsız tür için varsayılan rank (sona düşer).
CANONICAL_DOC_ORDER_DEFAULT = 1000


def canonical_order(document_type: str) -> int:
    """Belge türünün dizi pusulasındaki varsayılan kanonik sırası (küçük = önce)."""
    return CANONICAL_DOC_ORDER.get(document_type, CANONICAL_DOC_ORDER_DEFAULT)


# Katılımcı belgelerinde "kimden" KISA rol etiketi (dizi pusulası snapshot, Tur 140).
# Talep 1i: "Suçlanan" → "Hakkında İşlem Yapılan" (enum değeri ACCUSED korunur).
PARTICIPANT_ROLE_SHORT: dict[str, str] = {
    ParticipantRole.ACCUSED: "Hakkında İşlem Yapılan",
    ParticipantRole.VICTIM: "Mağdur",
    ParticipantRole.WITNESS: "Tanık",
}

# Bilgi alma (INFO_GATHERING) için seçilebilir KAYNAK listesi (Tur 140) — katılımcı rolü
# değil; üretimde seçilir. Frontend aynı listeyi gösterir; "Diğer" serbest kabul edilir.
INFO_GATHERING_SOURCES: tuple[str, ...] = (
    "Rehberlik Servisi",
    "Sınıf Öğretmeni",
    "Müdür Yardımcısı",
    "Ders Öğretmeni",
    "Veli",
    "Diğer",
)

# Dizi pusulası kategori gruplaması (Tur 140) — belge türü → kategori başlığı; SABİT sıra.
# INDEX_SHEET listelenmez (kapak). Eşlenmemiş tür "Diğer Evrak"a düşer.
_OTHER_CATEGORY = "Diğer Evrak"
DOC_CATEGORIES: tuple[tuple[str, frozenset[str]], ...] = (
    ("İfadeler", frozenset({DocumentType.STATEMENT_RECORD})),
    ("Savunmalar", frozenset({DocumentType.DEFENSE_RECORD})),
    ("Bilgi Alma Tutanakları", frozenset({DocumentType.INFO_GATHERING})),
    (
        "Çağrı / Davet Yazıları",
        frozenset(
            {DocumentType.STATEMENT_CALL, DocumentType.DEFENSE_CALL, DocumentType.MEETING_CALL}
        ),
    ),
    ("Müdür Uyarısı", frozenset({DocumentType.WARNING_LETTER})),
    (
        "Tedbir / Süre Uzatma",
        frozenset({DocumentType.PRECAUTION_NOTICE, DocumentType.DEADLINE_EXTENSION}),
    ),
    ("Kurul Kararı", frozenset({DocumentType.COMMITTEE_DECISION})),
    (
        "Tebliğler",
        frozenset(
            {
                DocumentType.PENALTY_NOTICE,
                DocumentType.PENALTY_DAYS_NOTICE,
                DocumentType.BOARD_DECISION_NOTICE,
            }
        ),
    ),
    ("İtiraz", frozenset({DocumentType.APPEAL_LETTER})),
    (_OTHER_CATEGORY, frozenset({DocumentType.OTHER})),
)


def categorized_documents(documents: list[Any]) -> list[dict[str, Any]]:
    """Ana evrakları sabit-sıralı kategorilere gruplar (dizi pusulası, Tur 140).

    Boş kategoriler atlanır; DOC_CATEGORIES'te eşlenmemiş tür "Diğer Evrak"a düşer.
    Belge sırası timeline (kanonik) sırasını korur. Alt evraklar kendi ana evrağında kalır.
    """
    type_to_cat = {dt: label for label, types in DOC_CATEGORIES for dt in types}
    buckets: dict[str, list[Any]] = {label: [] for label, _ in DOC_CATEGORIES}
    for doc in documents:
        buckets[type_to_cat.get(doc.document_type, _OTHER_CATEGORY)].append(doc)
    return [
        {"label": label, "documents": buckets[label]}
        for label, _ in DOC_CATEGORIES
        if buckets[label]
    ]


def participant_source(
    document_type: str, participant: Any, selected_source: str = ""
) -> tuple[str, str]:
    """Katılımcı belgesi için (source_label, source_name) snapshot'ı döndürür (Tur 140).

    İfade/savunma/çağrı: etiket rolden (Hakkında İşlem Yapılan/Mağdur/Tanık) OTOMATİK.
    Bilgi alma: etiket üretimde SEÇİLEN kaynaktan (selected_source). Ad daima snapshot
    (yoksa dış kişi adı). Katılımcısız belgede ("" , "").
    """
    if participant is None:
        return "", ""
    # Ad, PDF gövdesiyle AYNI çözümle gelir (snapshot → öğrenci kaydı → dış kişi).
    name = (_participant_context(participant).get("name") or "").strip()
    if document_type == DocumentType.INFO_GATHERING:
        label = (selected_source or "").strip()
    else:
        label = PARTICIPANT_ROLE_SHORT.get(participant.role, participant.get_role_display())
    return label, name


def _resolve_template(document_type: str, recipient: str, variant: str = "") -> str:
    """Belge türü (+ alıcı / variant) → şablon yolu; üretilemezse ValueError."""
    by_variant = DOC_TEMPLATES_BY_VARIANT.get(document_type)
    if by_variant is not None:
        return by_variant.get(variant) or by_variant[VARIANT_RECORD]
    by_recipient = DOC_TEMPLATES_BY_RECIPIENT.get(document_type)
    if by_recipient is not None:
        return by_recipient.get(recipient) or by_recipient[RECIPIENT_STUDENT]
    template = DOC_TEMPLATES.get(document_type)
    if template is None:
        raise ValueError("Geçersiz/üretilemez belge türü.")
    return template


def is_generatable(document_type: str) -> bool:
    """Belge türünün üretim şablonu var mı (tek-alıcılı / alıcıya göre / variant'a göre)."""
    return (
        document_type in DOC_TEMPLATES
        or document_type in DOC_TEMPLATES_BY_RECIPIENT
        or document_type in DOC_TEMPLATES_BY_VARIANT
    )


def render_pdf_paged(template_name: str, context: dict[str, Any]) -> tuple[bytes, int]:
    """Şablonu WeasyPrint ile PDF'e dönüştürür; (bayt, sayfa sayısı) döner (tek render).

    Sayfa sayısı GeneratedDocument.page_count'a yazılır (dizi pusulası, Tur 104).
    """
    from weasyprint import HTML  # tembel import (ağır bağımlılık)

    html = render_to_string(template_name, context)
    base_url = getattr(settings, "STATIC_ROOT", None) or settings.MEDIA_ROOT
    document = HTML(string=html, base_url=str(base_url)).render()
    pdf_bytes: bytes = document.write_pdf()
    return pdf_bytes, len(document.pages)


def render_pdf(template_name: str, context: dict[str, Any]) -> bytes:
    """Bir HTML şablonunu WeasyPrint ile PDF bayt dizisine dönüştürür (sayfa sayısı atılır)."""
    pdf_bytes, _ = render_pdf_paged(template_name, context)
    return pdf_bytes


def _student_context(student: Any) -> dict[str, Any]:
    """EK-1/tebliğ için öğrenci bağlamı (düz modelden). TCKN hassastır.

    Anahtarlar OYS ile BİREBİR (şablon sadakati kritiği — tasarım §4.2):
    düzleştirilmiş `Student` sınıf/no bilgisini satırda taşır.
    """
    return {
        "full_name": student.full_name or "",
        "tckn": student.tckn or "",  # EK-1 resmî zorunluluğu (hassas okuma)
        "birth_date": student.birth_date,
        "class_label": student.class_label,
        "student_number": student.student_number or "",
    }


_KURUL_UNIT = "Okul Öğrenci Ödül ve Disiplin Kurulu"
_MUDURLUK_UNIT = "Okul Müdürlüğü"  # Dal A (müdür uyarısı) belgeleri — Tur 213, talep 3


def _common_context(case: DisciplineCase, *, unit: str = _KURUL_UNIT) -> dict[str, Any]:
    """Tüm belgelerde ortak bağlam (resmî antet + dosya + tarih).

    `unit` antet alt satırı: kurul belgelerinde "Okul Öğrenci Ödül ve Disiplin
    Kurulu"; müdür işlemlerinde (uyarı/tedbir) kuruldan bağımsız → boş geçilir.
    """
    from apps.okul.services import setup as okul_setup

    # Antet kimliği: kurulum sihirbazında girilen okul/ilçe/müdür (SchoolConfig).
    identity = okul_setup.get_letterhead_identity()
    return {
        **letterhead_context(
            school_name=identity["school_name"],
            unit=unit,
            district=identity["district"],
            principal_name=identity["principal_name"],
        ),
        "case": case,
        "generated_at": timezone.now(),
    }


def _parent_context(student: Any) -> dict[str, Any] | None:
    """Veli tebliğleri için sorumlu veli bağlamı — yoksa None.

    Düzleştirilmiş modelde sorumlu veli `guardian_*` alanlarındadır (tasarım
    §4.2 — Form-15/17 buradan beslenir); veli adı boşsa None (şablon elle dolum).
    """
    name = (student.guardian_name or "").strip()
    if not name:
        return None
    return {
        "full_name": name,
        "kinship_display": student.get_guardian_kinship_display()
        if student.guardian_kinship
        else "",
    }


def _ek1_context(case: DisciplineCase, student: Any) -> dict[str, Any]:
    """EK-1 kurul kararı bağlamı — karar + anlatı alanları + kurul üyeleri (TAM-OTO)."""
    decision = case.decisions.filter(student_id=student.pk).first()
    committee = selectors.get_active_committee()
    members = list(selectors.committee_members(committee)) if committee else []
    return {
        **_common_context(case),
        "student": _student_context(student),
        "decision": decision,
        "statute_label": statute_label(decision),
        "committee": committee,
        "members": members,
    }


# Dal A (yalnız yazılı uyarı) dosyasında üretilebilir belge türleri (Tur 214, F17):
# frontend workflow.ts BRANCH_A_DOC_TYPES + dizi pusulası (Dal A'da müdürlük antediyle
# üretilir, Tur 213). Kurul formları kurul antedi/imza ızgarası bastığından Dal A'da
# mevzuata aykırı görüntü oluşturur.
_BRANCH_A_ALLOWED: frozenset[str] = frozenset(
    {
        DocumentType.WARNING_LETTER,
        DocumentType.PRECAUTION_NOTICE,
        DocumentType.INDEX_SHEET,
    }
)


def _case_referred_to_committee(case: DisciplineCase) -> bool:
    """Dosya kurula sevk edildi mi? (Dal B) — DECIDED olayının müdür kararından (Tur 109)."""
    decided = case.events.filter(stage=CaseStage.DECIDED).order_by("event_date").first()
    pds = (decided.principal_decisions or []) if decided else []
    return any(
        d in (PrincipalDecision.HONOR_COMMITTEE, PrincipalDecision.DISCIPLINE_COMMITTEE)
        for d in pds
    )


def _index_sheet_context(case: DisciplineCase) -> dict[str, Any]:
    """Dizi pusulası bağlamı — ana evraklar + alt evraklar + toplam sayfa (Tur 104).

    Düzenleyen dala göre (Tur 109): kurula sevk edilen (Dal B) dosyayı kurul başkanı,
    uyarıyla/triajla yürüyen (Dal A) dosyayı okul müdürü düzenler. Antet birimi de
    dala göre (Tur 213, talep 3): Dal A "Okul Müdürlüğü", Dal B kurul birimi.
    """
    documents = selectors.document_timeline(case)
    total_pages = sum(
        doc.page_count + sum(sub.page_count for sub in doc.sub_documents.all()) for doc in documents
    )
    referred = _case_referred_to_committee(case)
    ctx = {
        **_common_context(case, unit=_KURUL_UNIT if referred else _MUDURLUK_UNIT),
        "categories": categorized_documents(list(documents)),  # kategori gruplaması (Tur 140)
        "total_pages": total_pages,
    }
    if referred:
        committee = selectors.get_active_committee()
        chair = committee.chair if committee else None
        ctx["compiler_name"] = chair.full_name if chair else ""
        ctx["compiler_role"] = "Düzenleyen / Disiplin Kurulu Başkanı"
    else:
        ctx["compiler_name"] = ctx.get("principal_name", "")
        ctx["compiler_role"] = "Düzenleyen / Okul Müdürü"
    return ctx


def _committee_context() -> dict[str, Any]:
    """Tebliğ eden (müdür yrd. / kurul başkanı) için aktif kurul bağlamı."""
    committee = selectors.get_active_committee()
    return {"committee": committee}


def _penalty_notice_context(case: DisciplineCase, student: Any) -> dict[str, Any]:
    """Ceza tebliği (Form-14/15) bağlamı — karar + (veli sürümünde) veli + kurul."""
    decision = case.decisions.filter(student_id=student.pk).first()
    if decision is not None:
        from apps.disiplin.services.decisions import ensure_decision_no

        ensure_decision_no(decision)
    return {
        **_common_context(case),
        **_committee_context(),
        "student": _student_context(student),
        "parent": _parent_context(student),
        "decision": decision,
        "statute_label": statute_label(decision),
    }


def _suspension_dates(decision: Any) -> dict[str, Any]:
    """Uzaklaştırma başlangıç/bitiş/okula-başlama (md. 164/2, 172) — iş günü (tatil hariç).

    `enforcement_start_date` + `suspension_days` varsa hesaplanır; biri yoksa hepsi
    None (şablon "…/…/202…" gösterir). İş günü yüklemi `core.services.is_working_day`
    (resmî/idari tatilleri atlar; ADR-0002 açık servis arayüzü, Tur 90 deseni).
    """
    from apps.disiplin import discipline_periods
    from apps.okul.services.calendar import is_working_day

    start = getattr(decision, "enforcement_start_date", None) if decision else None
    days = getattr(decision, "suspension_days", None) if decision else None
    if start is None or not days:
        return {"enforcement_start": None, "enforcement_end": None, "school_return": None}
    pred = is_working_day
    end = discipline_periods.suspension_end_date(start, days, is_working_day=pred)
    return {
        "enforcement_start": start,
        "enforcement_end": end,
        "school_return": discipline_periods.school_return_date(end, is_working_day=pred),
    }


# Uzaklaştırma gün sayısının yazıyla gösterimi (Tur 218, talep 10) — md. 164/2
# kısa süreli uzaklaştırma 1-5 gün (servis doğruluyor); aralık dışı → boş bırakılır.
_SUSPENSION_DAYS_TEXT: dict[int, str] = {1: "bir", 2: "iki", 3: "üç", 4: "dört", 5: "beş"}


def _penalty_days_notice_context(case: DisciplineCase, student: Any) -> dict[str, Any]:
    """Ceza günleri tebliği (Form-16/17) bağlamı — karar + uygulama tarihleri + veli.

    `suspension_days_text`: gün sayısının yazıyla hâli ("3 (üç) gün" — Tur 218).
    """
    decision = case.decisions.filter(student_id=student.pk).first()
    days = getattr(decision, "suspension_days", None) if decision else None
    return {
        **_common_context(case),
        **_committee_context(),
        "student": _student_context(student),
        "parent": _parent_context(student),
        "decision": decision,
        "statute_label": statute_label(decision),
        "suspension_days_text": _SUSPENSION_DAYS_TEXT.get(days) if days else None,
        **_suspension_dates(decision),
    }


def _appeal_letter_context(case: DisciplineCase, student: Any) -> dict[str, Any]:
    """İl/İlçe itiraz yazısı (Form-18) bağlamı — karar + en son itiraz dilekçesi."""
    decision = case.decisions.filter(student_id=student.pk).first()
    appeal = None
    if decision is not None:
        appeal = selectors.appeals_for_decision(decision).first()
    return {
        **_common_context(case),
        "student": _student_context(student),
        "decision": decision,
        "statute_label": statute_label(decision),
        "appeal": appeal,
    }


def _warning_letter_context(
    case: DisciplineCase, student: Any, extra: dict[str, Any]
) -> dict[str, Any]:
    """Müdür uyarısı yazısı (Form-02) bağlamı — md. 157/7 (Tur 213, talep 3a/3b).

    Davranış özeti önceliği: üretim formundan gelen `behavior_summary` (GEÇİCİ —
    DB'ye/loga yazılmaz, yalnız PDF'e basılır) → yoksa en son uyarı kaydının
    `summary`'si. İkisi de boşsa hata: "[davranışın kısa açıklaması]" placeholder'ı
    resmî belgeye asla düz metin basılmaz. Veli bilgilendirme sürümü (recipient
    parent) için sorumlu veli bağlamı da eklenir.
    """
    warning = selectors.warnings_for_case(case).filter(student_id=student.pk).first()
    summary = (extra.get("behavior_summary") or "").strip() or (
        warning.summary.strip() if warning and warning.summary else ""
    )
    if not summary:
        raise ValueError(
            "Davranışın kısa açıklaması zorunludur: üretim formuna metni girin "
            "veya önce dosyaya müdür uyarısı kaydı ekleyin."
        )
    return {
        **_common_context(case, unit=""),  # müdür işlemi — kurul belgesi değil
        "student": _student_context(student),
        "warning": warning,
        "behavior_summary": summary,
        "parent": _parent_context(student),
    }


# --- Üst kurul kararı tebliği (Tur 220, talep 3) — md. 169/2-4, 197, 200/202 ---

NOTICE_KIND_APPROVAL = "approval"
NOTICE_KIND_APPEAL_RESULT = "appeal_result"
_NOTICE_KINDS: frozenset[str] = frozenset({NOTICE_KIND_APPROVAL, NOTICE_KIND_APPEAL_RESULT})

# Onay mercii kararının sonucu (S1): onay mercii kararı "onaylar veya değiştirir";
# itiraz kurulu (S2) "kaldırır, değiştirir veya itirazı reddeder" (md. 200/1-Ç).
BOARD_OUTCOME_APPROVED = "APPROVED"
BOARD_OUTCOME_MODIFIED = "MODIFIED"
_OUTCOMES_BY_KIND: dict[str, tuple[str, ...]] = {
    NOTICE_KIND_APPROVAL: (BOARD_OUTCOME_APPROVED, BOARD_OUTCOME_MODIFIED),
    NOTICE_KIND_APPEAL_RESULT: (
        AppealResult.UPHELD,
        AppealResult.REDUCED,
        AppealResult.OVERTURNED,
    ),
}

# Üst kurul karar tebliğinde geçerli merciler (PRINCIPAL bu belgeye konu olamaz).
_BOARD_AUTHORITIES: frozenset[str] = frozenset(
    {
        ApprovalAuthority.DISTRICT_BOARD,
        ApprovalAuthority.PROVINCIAL_BOARD,
        ApprovalAuthority.UPPER_BOARD,
    }
)

# S1 onay kararına itirazı değerlendirecek BİR ÜST kurul (md. 169/4: onaylayan kurul
# aynı karara yönelik itirazı görüşemez; md. 169/3-b/c ile tutarlı).
_NEXT_BOARD: dict[str, str] = {
    ApprovalAuthority.DISTRICT_BOARD: ApprovalAuthority.PROVINCIAL_BOARD,
    ApprovalAuthority.PROVINCIAL_BOARD: ApprovalAuthority.UPPER_BOARD,
}


def _board_decision_notice_context(
    case: DisciplineCase, student: Any, extra: dict[str, Any]
) -> dict[str, Any]:
    """Üst kurul kararı tebliği bağlamı (Tur 220, talep 3) — iki senaryo:

    S1 `approval`: onay mercii (ilçe/il) kararının tebliği (md. 169/2-b/c; md. 197
    ısrar-sevki dahil) → belgede İTİRAZ HAKKI paragrafı basılır.
    S2 `appeal_result`: itiraz sonucunun tebliği → KESİNLİK paragrafı (md. 169/4).

    Üst kurul karar no/tarihi ve sonuç özeti GEÇİCİ üretim alanlarıdır (DB'de
    karşılığı yok — E4 kabulü); merci/sonuç boşsa karardan/en son sonuçlanmış
    itirazdan türetilir. Tutarsız girdi Türkçe ValueError ile reddedilir.
    """
    decision = case.decisions.filter(student_id=student.pk).first()
    if decision is None:
        raise ValueError(
            "Dosyada bu öğrenci için resmî karar yok; üst kurul kararı tebliği üretilemez."
        )
    kind = (extra.get("notice_kind") or NOTICE_KIND_APPROVAL).strip()
    if kind not in _NOTICE_KINDS:
        raise ValueError("Geçersiz tebliğ türü (onay kararı / itiraz sonucu).")
    appeal = selectors.latest_resolved_appeal(decision)

    authority = (extra.get("board_authority") or "").strip()
    if not authority:
        if kind == NOTICE_KIND_APPEAL_RESULT:
            authority = appeal.appeal_authority if appeal else ""
        else:
            authority = decision.approval_authority
            if authority == ApprovalAuthority.PRINCIPAL:
                # md. 197: müdür-onaylı cezada üst karar ancak ısrar-sevkiyle İLÇEDEN gelir.
                authority = ApprovalAuthority.DISTRICT_BOARD
    if authority not in _BOARD_AUTHORITIES:
        raise ValueError("Karar mercii belirlenemedi; üretim formundan ilçe/il/üst kurul seçin.")

    outcome = (extra.get("board_outcome") or "").strip()
    if not outcome:
        if kind == NOTICE_KIND_APPROVAL:
            outcome = BOARD_OUTCOME_APPROVED
        elif appeal is not None:
            outcome = appeal.result
    if outcome not in _OUTCOMES_BY_KIND[kind]:
        raise ValueError(
            "Karar sonucu seçilmedi veya tebliğ türüyle uyumsuz "
            "(onay kararı: onaylandı/değiştirildi; itiraz sonucu: onandı/değiştirildi/kaldırıldı)."
        )
    summary = (extra.get("result_summary") or "").strip()
    if outcome in (BOARD_OUTCOME_MODIFIED, AppealResult.REDUCED) and not summary:
        raise ValueError(
            "Karar 'değiştirildi' ise kurul kararı özeti zorunludur — değişen ceza belgeye yazılır."
        )

    next_board = _NEXT_BOARD.get(authority)
    return {
        **_common_context(case),
        **_committee_context(),
        "student": _student_context(student),
        "parent": _parent_context(student),
        "decision": decision,
        "statute_label": statute_label(decision),
        "notice_kind": kind,
        "board_label": ApprovalAuthority(authority).label,
        "appeal_board_label": (
            ApprovalAuthority(next_board).label if next_board else "bir üst disiplin kurulu"
        ),
        "board_decision_no": (extra.get("board_decision_no") or "").strip(),
        "board_decision_date": extra.get("board_decision_date"),
        "board_outcome": outcome,
        "result_summary": summary,
    }


def _precaution_notice_context(case: DisciplineCase, student: Any) -> dict[str, Any]:
    """Tedbir bildirimi (md. 175) bağlamı — yürürlükteki tedbir; yoksa en son."""
    precaution = selectors.active_precaution(case, student.pk) or (
        selectors.precautions_for_case(case).filter(student_id=student.pk).first()
    )
    return {
        **_common_context(case, unit=""),  # müdür tedbiri — kurul belgesi değil
        "student": _student_context(student),
        "precaution": precaution,
    }


# --- Dal B ifade/savunma/bilgi formları (Tur 106) — katılımcı + kurul + geçici alanlar ---


def _committee_with_members_context() -> dict[str, Any]:
    """Aktif kurul + üyeleri (asıl+yedek) — imza ızgaraları için (EK-1 deseni)."""
    committee = selectors.get_active_committee()
    members = list(selectors.committee_members(committee)) if committee else []
    return {"committee": committee, "members": members}


def _participant_context(participant: Any) -> dict[str, Any]:
    """Katılımcı bağlamı — ad + rol + (öğrenciyse) sınıf/no. Snapshot adı önceliklidir.

    Ad-snapshot ekleme anındadır (tutanak bütünlüğü). Öğrenci katılımcıda güncel
    kayıttan sınıf/numara türetilir; personel/dış kişide snapshot/dış ad kullanılır.
    """
    from apps.okul import selectors as okul_selectors

    name = (participant.name_snapshot or "").strip()
    ctx: dict[str, Any] = {
        "name": name,
        "role": participant.role,
        "role_display": participant.get_role_display(),
        "person_type": participant.person_type,
        "person_type_display": participant.get_person_type_display(),
        # Dış kişi sıfatı ("komşu", "esnaf"…) — Form-3/4-6'da kişi tipi satırında basılır.
        "external_title": (participant.external_title or "").strip(),
        "class_label": "",
        "student_number": "",
    }
    if participant.student_id:
        student = okul_selectors.get_student(participant.student_id)
        if student is not None:
            if not name:
                ctx["name"] = student.full_name or ""
            ctx["class_label"] = student.class_label
            ctx["student_number"] = student.student_number or ""
    elif not name:
        ctx["name"] = participant.external_name or ""
    return ctx


def _schedule_context(extra: dict[str, Any]) -> dict[str, Any]:
    """Çağrı/toplantı için GEÇİCİ tarih/saat/yer (DB'ye yazılmaz; yalnız PDF)."""
    return {
        "statement_date": extra.get("statement_date"),
        "statement_time": (extra.get("statement_time") or "").strip(),
        "statement_place": (extra.get("statement_place") or "").strip(),
    }


def _statement_call_context(
    case: DisciplineCase, participant: Any, extra: dict[str, Any]
) -> dict[str, Any]:
    """İfadeye çağrı pusulası (Form-3, md. 194-195) — katılımcı + tebliğ/tebellüğ + zaman."""
    return {
        **_common_context(case),
        **_committee_with_members_context(),
        "participant": _participant_context(participant),
        **_schedule_context(extra),
    }


def _statement_record_context(
    case: DisciplineCase, participant: Any, extra: dict[str, Any]
) -> dict[str, Any]:
    """İfade tutanağı (Form-4/5/6) — rol başlığı katılımcıdan.

    Dolu-bas (Tur 142): `statement_subject` (konu/sorular) + `statement_body` (ifade)
    verilirse PDF'e basılır; boşsa gövde elle yazılır (eski davranış). İçerik GEÇİCİ —
    DB'ye yazılmaz (no-trace; KVKK).
    """
    return {
        **_common_context(case),
        **_committee_with_members_context(),
        "participant": _participant_context(participant),
        "statement_subject": (extra.get("statement_subject") or "").strip(),
        "statement_body": (extra.get("statement_body") or "").strip(),
    }


def _info_gathering_context(
    case: DisciplineCase, participant: Any, extra: dict[str, Any]
) -> dict[str, Any]:
    """Bilgi toplama (Form-7/8) — variant 'student'/'teacher' gövdeyi belirler (hakkında işlem yapılan öğrenci)."""
    return {
        **_common_context(case),
        **_committee_with_members_context(),
        "participant": _participant_context(participant),
        "variant": (extra.get("variant") or "student").strip() or "student",
    }


def _defense_call_context(
    case: DisciplineCase, participant: Any, extra: dict[str, Any]
) -> dict[str, Any]:
    """Savunmaya çağrı (Form-9, md. 194) — suçlanan + tebliğ/tebellüğ + zaman."""
    return {
        **_common_context(case),
        **_committee_with_members_context(),
        "participant": _participant_context(participant),
        **_schedule_context(extra),
    }


def _defense_record_context(
    case: DisciplineCase, participant: Any, extra: dict[str, Any]
) -> dict[str, Any]:
    """Savunma tutanağı (Form-11) — suçlanan künyesi + kurul imza satırı.

    Dolu-bas (Tur 219, talep 2 — statement_record deseni): `statement_subject`
    (Olay satırı) + `statement_body` (savunma metni) verilirse PDF'e DOLU basılır
    ve metin akışkan düzende sürer; boşsa elle yazım için iki-kutu düzeni korunur.
    İçerik GEÇİCİ — DB'ye yazılmaz (no-trace; KVKK).
    """
    return {
        **_common_context(case),
        **_committee_with_members_context(),
        "participant": _participant_context(participant),
        "statement_subject": (extra.get("statement_subject") or "").strip(),
        "statement_body": (extra.get("statement_body") or "").strip(),
        **_schedule_context(extra),
    }


def _meeting_call_context(case: DisciplineCase, extra: dict[str, Any]) -> dict[str, Any]:
    """Kurul toplantı çağrısı (Form-10, md. 190-191) — üye listesi + toplantı zamanı."""
    return {
        **_common_context(case),
        **_committee_with_members_context(),
        **_schedule_context(extra),
    }


def _deadline_extension_context(case: DisciplineCase) -> dict[str, Any]:
    """Süre uzatma (F-12 ara karar / F-13 dilekçe, md. 192/3) — uzatma kaydı + kurul + öğrenci.

    Uzatma dosya başına tektir (alive-unique) → `deadline_extensions.first()`. Öğrenci
    künyesi dosyanın ilk öğrencisinden (çoğu dosya tek öğrencili); yoksa boş kalır.
    """
    extension = case.deadline_extensions.first()
    student = case.students.first()
    return {
        **_common_context(case),
        **_committee_with_members_context(),
        "extension": extension,
        "student": _student_context(student) if student is not None else None,
    }


# Belge türü → katılımcı-özgü bağlam üretici (Tur 106).
_ParticipantContextBuilder = Callable[[DisciplineCase, Any, dict[str, Any]], dict[str, Any]]
_PARTICIPANT_CONTEXT_BUILDERS: dict[str, _ParticipantContextBuilder] = {
    DocumentType.STATEMENT_CALL: _statement_call_context,
    DocumentType.STATEMENT_RECORD: _statement_record_context,
    DocumentType.INFO_GATHERING: _info_gathering_context,
    DocumentType.DEFENSE_CALL: _defense_call_context,
    DocumentType.DEFENSE_RECORD: _defense_record_context,
}


# Belge türü → bağlam üretici (öğrenci-özgü builder'lar).
_StudentContextBuilder = Callable[[DisciplineCase, Any], dict[str, Any]]
_STUDENT_CONTEXT_BUILDERS: dict[str, _StudentContextBuilder] = {
    DocumentType.COMMITTEE_DECISION: _ek1_context,
    DocumentType.PENALTY_NOTICE: _penalty_notice_context,
    DocumentType.PENALTY_DAYS_NOTICE: _penalty_days_notice_context,
    DocumentType.APPEAL_LETTER: _appeal_letter_context,
    # WARNING_LETTER burada DEĞİL — extra (behavior_summary) gerektirir,
    # _build_context'te özel dala alınır (Tur 213). STUDENT_REQUIRED'da kalır.
    DocumentType.PRECAUTION_NOTICE: _precaution_notice_context,
}


def _build_context(
    case: DisciplineCase,
    document_type: str,
    student: Any,
    participant: Any,
    extra: dict[str, Any],
) -> dict[str, Any]:
    """Belge türüne göre şablon bağlamını oluşturur (öğrenci / katılımcı / kurul)."""
    if document_type == DocumentType.INDEX_SHEET:
        return _index_sheet_context(case)
    if document_type == DocumentType.WARNING_LETTER:
        return _warning_letter_context(case, student, extra)
    if document_type == DocumentType.BOARD_DECISION_NOTICE:
        return _board_decision_notice_context(case, student, extra)
    if document_type == DocumentType.MEETING_CALL:
        return _meeting_call_context(case, extra)
    if document_type == DocumentType.DEADLINE_EXTENSION:
        return _deadline_extension_context(case)
    participant_builder = _PARTICIPANT_CONTEXT_BUILDERS.get(document_type)
    if participant_builder is not None:
        return participant_builder(case, participant, extra)
    builder = _STUDENT_CONTEXT_BUILDERS.get(document_type)
    if builder is None:
        raise ValueError("Bu belge türü için üretim şablonu tanımlı değil.")
    return builder(case, student)


def generate_document(
    case: DisciplineCase,
    *,
    document_type: str,
    generated_on: date,
    recipient: str = RECIPIENT_STUDENT,
    student_id: int | None = None,
    participant_id: int | None = None,
    statement_date: date | None = None,
    statement_time: str = "",
    statement_place: str = "",
    statement_subject: str = "",
    statement_body: str = "",
    behavior_summary: str = "",
    notice_kind: str = "",
    board_authority: str = "",
    board_decision_no: str = "",
    board_decision_date: date | None = None,
    board_outcome: str = "",
    result_summary: str = "",
    variant: str = "",
    document_no: str = "",
    title: str = "",
    source_label: str = "",
    log: bool = True,
) -> tuple[bytes, GeneratedDocument | None]:
    """Bir disiplin belgesini üretir (PDF bayt) ve izlenebilirse kütüğe kaydeder.

    `log=True` (varsayılan) → üretilen belge GeneratedDocument kütüğüne yazılır
    (services.log_generated_document; AuditLog + kütük izi). Yeniden basımda veya
    no-trace belgelerde `log=False`. Öğrenci-özgü belgelerde (`STUDENT_REQUIRED`)
    `student_id` zorunlu ve dosyaya dahil olmalı. `recipient` (öğrenci/veli) yalnız
    `DOC_TEMPLATES_BY_RECIPIENT`'taki ikiz belgelerde (Form-14↔15, 16↔17) şablonu
    belirler; diğerlerinde yok sayılır.

    Dal B ifade/savunma/bilgi formları (Tur 106, `PARTICIPANT_REQUIRED`) hedef kişiyi
    `participant_id` (DisciplineParticipant) ile çözer; `statement_date/time/place` +
    `variant` (Form-7/8 öğrenci/öğretmen) yalnız PDF'e basılan GEÇİCİ alanlardır,
    Serbest metin alanları ayrı model alanlarına yazılmaz; ancak kullanıcının
    yeniden yazdırma talebi gereği üretilen PDF'nin değişmez kopyasında yer alır.

    İfade tutanağı (Form-4/5/6) dolu-bas (Tur 142): `statement_subject` (disiplin konusu /
    sorular) + `statement_body` (ifade gövdesi) verilirse PDF'e DOLU basılır; boşsa eski
    boş kutu (elle yazım) korunur. Bu iki alan da GEÇİCİ — DB'ye YAZILMAZ ve loglanmaz
    (proje vizyonu "ifade içeriği saklanmaz"; KVKK).

    Döner: (pdf_bytes, kütük_kaydı | None).
    """
    if recipient not in VALID_RECIPIENTS:
        raise ValueError("Geçersiz tebliğ alıcısı (öğrenci/veli).")
    # Dal A koruması (Tur 214, F17): yalnız-uyarı dalında (DECIDED kararı var,
    # kurula sevk yok) kurul formları üretilmez — Tur 213 (3c) UI filtresinin
    # sunucu karşılığı. DECIDED öncesi (dal belirsiz) ve Dal B'de tam liste.
    if document_type not in _BRANCH_A_ALLOWED:
        decided = case.events.filter(stage=CaseStage.DECIDED).order_by("event_date").first()
        pds = (decided.principal_decisions or []) if decided else []
        if pds and not _case_referred_to_committee(case):
            raise ValueError(
                "Bu dosya kurula sevk edilmedi (yalnız uyarı dalı); kurul formları üretilemez."
            )
    template = _resolve_template(document_type, recipient, variant)
    student = None
    if document_type in STUDENT_REQUIRED:
        if student_id is None:
            raise ValueError("Bu belge öğrenci-özgüdür; student_id zorunludur.")
        student = _student_in_case(case, student_id)
    participant = None
    if document_type in PARTICIPANT_REQUIRED:
        if participant_id is None:
            raise ValueError("Bu belge katılımcı-özgüdür; participant_id zorunludur.")
        participant = _participant_in_case(case, participant_id)

    # Kesinleşme kilidi (Tur 218, talep 9): ceza günleri tebliği (Form-16/17) ancak
    # KESİNLEŞMİŞ cezada üretilir (md. 169/3-4 + md. 172/2-ç emsali) — itiraz süresi
    # dolmadan/derdest itiraz varken uygulama tebliği telafisi güç mağduriyet doğurur.
    if document_type == DocumentType.PENALTY_DAYS_NOTICE:
        days_decision = case.decisions.filter(student_id=student_id).first()
        if days_decision is None:
            final, reason = False, "dosyada bu öğrenci için resmî karar yok"
        else:
            final, reason = selectors.decision_is_final(days_decision)
        if not final:
            raise ValueError(f"Ceza kesinleşmeden ceza günleri tebliği üretilemez: {reason}.")

    extra = {
        "statement_date": statement_date,
        "statement_time": statement_time,
        "statement_place": statement_place,
        "statement_subject": statement_subject,
        "statement_body": statement_body,
        # Form-02 davranış özeti (Tur 213) — GEÇİCİ: DB'ye/loga yazılmaz, yalnız PDF.
        "behavior_summary": behavior_summary,
        # Üst kurul kararı tebliği alanları (Tur 220) — GEÇİCİ (üst kurul karar
        # no/tarihi modelde tutulmaz, E4 kabulü; yalnız PDF'e basılır).
        "notice_kind": notice_kind,
        "board_authority": board_authority,
        "board_decision_no": board_decision_no,
        "board_decision_date": board_decision_date,
        "board_outcome": board_outcome,
        "result_summary": result_summary,
        "variant": variant,
    }
    context = _build_context(case, document_type, student, participant, extra)
    # NOT: eski DOC_CODES/doc_code altbilgi kodu Talep 1g'de (Tur 181) PDF
    # altbilgisinden kaldırılmıştı; ölü bağlam enjeksiyonu Tur 217'de temizlendi.
    # Form ↔ madde eşlemesi artık yalnız şablon alt başlıklarında yaşar.
    context["recipient"] = recipient
    # NOT: Form-14/15'te hesaplanan itiraz son günü BASILMAZ (Tur 181, Talep 1d —
    # tebligat günü belirsiz, PTT olabilir); şablonda yalnız "5 iş günü" hakkı yazılıdır.
    # Karar snapshot'ı (decision.appeal_deadline) tebliğ kaydında tutulur
    # (services.notify_decision); PDF bağlamına ayrıca işlenmez.
    pdf_bytes, page_count = render_pdf_paged(template, context)

    # Kütükte öğrenci bağı: öğrenci-özgü belgede student_id; katılımcı belgesinde
    # katılımcı bir öğrenciyse onun id'si (zaman çizelgesinde öğrenciyle ilişkilensin).
    log_student_id: int | None = None
    if document_type in STUDENT_REQUIRED:
        log_student_id = student_id
    elif participant is not None:
        log_student_id = participant.student_id

    # "Kimden" snapshot (Tur 140): katılımcı belgelerinde rol/kaynak + ad → dizi pusulası.
    src_label, src_name = participant_source(document_type, participant, source_label)

    record: GeneratedDocument | None = None
    if log:
        record = services.log_generated_document(
            case,
            document_type=document_type,
            title=title or DOC_TITLES.get(document_type, "Disiplin belgesi"),
            generated_on=generated_on,
            document_no=document_no,
            student_id=log_student_id,
            source_label=src_label,
            source_name=src_name,
            page_count=page_count,  # WeasyPrint'ten otomatik
            pdf_content=pdf_bytes,
            stored_filename=f"{case.case_no}-{document_type}.pdf",
        )
    return pdf_bytes, record


def _student_in_case(case: DisciplineCase, student_id: int) -> Any:
    """Dosyaya dahil öğrenciyi getirir; aksi halde ValueError (üretim ön-koşulu)."""
    from apps.okul import selectors as okul_selectors

    if not case.case_students.filter(student_id=student_id).exists():
        raise ValueError("Öğrenci bu disiplin dosyasına dahil değil.")
    student = okul_selectors.get_student(student_id)
    if student is None:
        raise ValueError("Öğrenci bulunamadı.")
    return student


def _participant_in_case(case: DisciplineCase, participant_id: int) -> Any:
    """Dosyanın katılımcısını getirir; aksi halde ValueError (üretim ön-koşulu)."""
    participant = selectors.get_participant(case, participant_id)
    if participant is None:
        raise ValueError("Katılımcı bu disiplin dosyasında bulunamadı.")
    return participant


# =============================================================================
# Kurul Toplantı Tutanağı / Karar Defteri (Tur 204, madde j) — md. 184/206
# =============================================================================

COUNCIL_MEETING_MINUTES_TEMPLATE = "disiplin/documents/council_meeting_minutes.html"

# Kurul türüne göre tutanak başlığı + antet birimi (md. 180 onur / md. 185 disiplin).
_COUNCIL_TITLES: dict[str, tuple[str, str]] = {
    "DISCIPLINE": (
        "ÖDÜL VE DİSİPLİN KURULU TOPLANTI TUTANAĞI",
        "Okul Öğrenci Ödül ve Disiplin Kurulu",
    ),
    "HONOR": ("ONUR KURULU TOPLANTI TUTANAĞI", "Onur Kurulu"),
}

# Kurul türüne göre mevzuat atıfları (Tur 216): tutanak alt başlığı + bölüm
# başlıklarındaki madde referansları kurul türüne özgüdür — toplanma/oy md. 191 ve
# davetli md. 185/6 ödül-disiplin kuruluna; toplanma md. 183 + karar defteri md. 184
# onur kuruluna aittir. md. 206 (gerekçeli, oy birliği/çoğunluğu, karşı görüş) ortak usul.
_COUNCIL_ARTICLES: dict[str, dict[str, str]] = {
    "DISCIPLINE": {
        # md. 190 çağrı, 191 toplanma/oy, 196 karar defteri (EK-1), 206 ortak usul.
        "subtitle": "MEB Ortaöğretim Kurumları Yönetmeliği md. 190-191, md. 196, md. 206",
        "attendees": "md. 191",
        "invitees": "md. 185/6",
        "closing": "md. 191, md. 206",
    },
    "HONOR": {
        "subtitle": "MEB Ortaöğretim Kurumları Yönetmeliği md. 183-184, md. 206",
        "attendees": "md. 183",
        "invitees": "",  # onur kurulunda özgül davetli maddesi yok — atıf basılmaz
        "closing": "md. 206",
    },
}
_COUNCIL_ARTICLES_DEFAULT: dict[str, str] = {
    "subtitle": "MEB Ortaöğretim Kurumları Yönetmeliği md. 206",
    "attendees": "",
    "invitees": "",
    "closing": "md. 206",
}


def _council_minutes_context(meeting: Any) -> dict[str, Any]:
    """Kurul toplantı tutanağı şablon bağlamı (render'dan ayrı — HTML testi için)."""
    from apps.okul.services import setup as okul_setup

    title, unit = _COUNCIL_TITLES.get(meeting.council_type, ("KURUL TOPLANTI TUTANAĞI", "Kurul"))
    articles = _COUNCIL_ARTICLES.get(meeting.council_type, _COUNCIL_ARTICLES_DEFAULT)
    if (
        meeting.council_type == "HONOR"
        and getattr(meeting, "honor_meeting_kind", "") == "GENERAL_ASSEMBLY"
    ):
        title = "ONUR GENEL KURULU TOPLANTI TUTANAĞI"
        unit = "Onur Genel Kurulu"
        articles = {
            "subtitle": "MEB Ortaöğretim Kurumları Yönetmeliği md. 178-181, md. 206",
            "attendees": "md. 178-181",
            "invitees": "",
            "closing": "md. 206",
        }
    identity = okul_setup.get_letterhead_identity()
    attendees = list(meeting.attendees.all())
    voting = [a for a in attendees if a.attendee_role == "VOTING_MEMBER"]
    invitees = [a for a in attendees if a.attendee_role == "NON_VOTING_INVITEE"]
    chair = next((a for a in voting if a.is_chair), None)
    dissenters = [a for a in attendees if (a.dissent_note or "").strip()]
    case = meeting.discipline_case if meeting.minutes_type == "CASE_REVIEW" else None
    case_decisions: list[dict[str, Any]] = []
    if case is not None:
        for decision in selectors.decisions_for_case(case).select_related("student"):
            student = decision.student
            case_decisions.append(
                {
                    "full_name": student.full_name or "",
                    "class_label": student.class_label,
                    "student_number": student.student_number or "",
                    "penalty_display": decision.get_penalty_type_display(),
                    "penalty_detail": decision.penalty_detail,
                    "decision_no": decision.decision_no,
                    "decision_date": decision.decision_date,
                    "statute_label": statute_label(decision),
                }
            )
    context: dict[str, Any] = {
        **letterhead_context(
            school_name=identity["school_name"],
            unit=unit,
            district=identity["district"],
            principal_name=identity["principal_name"],
        ),
        "generated_at": timezone.now(),
        "title": title,
        "articles": articles,
        "meeting": meeting,
        "chair": chair,
        "voting_members": voting,
        "invitees": invitees,
        "dissenters": dissenters,
        "case": case,
        "case_decisions": case_decisions,
    }
    return context


def render_council_meeting_minutes(meeting: Any) -> bytes:
    """Bir kurul toplantı tutanağını (karar defteri satırı) PDF'e dönüştürür (md. 184/206).

    Katılımcılar oy hakkı olan üyeler / oy hakkı olmayan davetliler (md. 185/6) olarak
    ayrılır; imza ızgarası başkan + oy hakkı olan üyelerden kurulur. Karşı görüş notları
    (md. 206) dipnot olarak listelenir. Madde atıfları kurul türüne göre basılır
    (_COUNCIL_ARTICLES, Tur 216). İçerik DB'de saklanmaz (disiplin evrak felsefesi).
    Dosya görüşme tutanağında (CASE_REVIEW, Tur 212) öğrenci-bazlı resmî kararlar
    (DisciplineDecision) render anında dosyadan derlenir — TCKN tutanağa yazılmaz.
    """
    return render_pdf(COUNCIL_MEETING_MINUTES_TEMPLATE, _council_minutes_context(meeting))
