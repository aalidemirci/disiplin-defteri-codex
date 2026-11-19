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
from datetime import date, datetime, time
from typing import Any

from django.conf import settings
from django.template.loader import render_to_string
from django.utils import timezone

from apps.disiplin import selectors, services
from apps.disiplin.models import (
    AppealResult,
    ApprovalAuthority,
    CaseStage,
    CouncilDecisionBasis,
    DecisionApprovalStatus,
    DisciplineCase,
    DisciplineDecision,
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
    # M2 Grup 1 süreç yazıları (kullanıcı kararı 27.09.2026) — resmî MEB örneği yok;
    # içerik md. 169/1 ve 197 metninden türetildi, kayıttan dolu basılır.
    DocumentType.RETURN_LETTER: "disiplin/documents/return_letter.html",
    DocumentType.DISTRICT_REFERRAL_LETTER: "disiplin/documents/district_referral_letter.html",
    DocumentType.APPROVAL_REQUEST_LETTER: "disiplin/documents/approval_request_letter.html",
    # M2 Grup 2 tutanakları (kullanıcı kararı 27.09.2026) — künye/antet dolu, beyan elle.
    DocumentType.SEARCH_RECORD: "disiplin/documents/search_record.html",
    DocumentType.NON_COMPLIANCE_RECORD: "disiplin/documents/non_compliance_record.html",
    # M2 Grup 3 — md. 157/7-a Form-01 (yazılı uyarıdan ÖNCEKİ rehberlik değerlendirmesi).
    DocumentType.GUIDANCE_ASSESSMENT: "disiplin/documents/guidance_assessment.html",
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
# md. 175 MEM yazısı: ilk bildirim (175/1 "millî eğitim müdürünü bilgilendirerek") /
# uzatma onayı talebi (175/2 "millî eğitim müdürünün onayına bağlı olarak").
VARIANT_MEM_INFO = "info"
VARIANT_MEM_EXTENSION = "extension"
# md. 157/7-b veli süreci: davet yazısı / görüşme tutanağı / gelmedi tutanağı.
VARIANT_PARENT_INVITE = "invite"
VARIANT_PARENT_MEETING = "meeting"
VARIANT_PARENT_NO_SHOW = "no_show"
DOC_TEMPLATES_BY_VARIANT: dict[str, dict[str, str]] = {
    DocumentType.DEADLINE_EXTENSION: {
        VARIANT_RECORD: "disiplin/documents/deadline_extension_record.html",  # Form-12
        VARIANT_PETITION: "disiplin/documents/deadline_extension_petition.html",  # Form-13
    },
    DocumentType.PRECAUTION_MEM_LETTER: {
        VARIANT_MEM_INFO: "disiplin/documents/precaution_mem_info.html",
        VARIANT_MEM_EXTENSION: "disiplin/documents/precaution_mem_extension.html",
    },
    DocumentType.PARENT_MEETING: {
        VARIANT_PARENT_INVITE: "disiplin/documents/parent_invite.html",
        VARIANT_PARENT_MEETING: "disiplin/documents/parent_meeting_record.html",
        VARIANT_PARENT_NO_SHOW: "disiplin/documents/parent_no_show_record.html",
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
    DocumentType.RETURN_LETTER: "Kurula İade Yazısı (md. 197)",
    DocumentType.DISTRICT_REFERRAL_LETTER: "İlçe Kuruluna Gönderme Yazısı (md. 197)",
    DocumentType.APPROVAL_REQUEST_LETTER: "Onaya Sevk Üst Yazısı (md. 169/1)",
    DocumentType.PRECAUTION_MEM_LETTER: "Tedbir Millî Eğitim Müdürlüğü Yazısı (md. 175)",
    DocumentType.PARENT_MEETING: "Veli Görüşmesi (md. 157/7-b)",
    DocumentType.GUIDANCE_ASSESSMENT: "Rehberlik Değerlendirme ve Öneri Formu (Form-01)",
    DocumentType.SEARCH_RECORD: "Arama Tutanağı (md. 158/3)",
    DocumentType.NON_COMPLIANCE_RECORD: "İfade/Savunma Vermedi Tespit Tutanağı (md. 195)",
}

# Aynı türün FARKLI belgeleri (sürüm / alıcı) kütükte ve dizi pusulasında aynı adla
# listelenmesin (saha denetimi 14.11.2026): (tür, variant) ve (tür, alıcı) → başlık.
# Kullanıcının üretim formuna yazdığı başlık her zaman önceliklidir.
DOC_TITLES_BY_VARIANT: dict[tuple[str, str], str] = {
    (DocumentType.DEADLINE_EXTENSION, VARIANT_RECORD): "Süre Uzatma Karar Tutanağı (Form-12)",
    (DocumentType.DEADLINE_EXTENSION, VARIANT_PETITION): "Süre Uzatma İsteği Dilekçesi (Form-13)",
    (
        DocumentType.PRECAUTION_MEM_LETTER,
        VARIANT_MEM_INFO,
    ): "Tedbir MEM Bilgilendirme Yazısı (md. 175/1)",
    (
        DocumentType.PRECAUTION_MEM_LETTER,
        VARIANT_MEM_EXTENSION,
    ): "Tedbir Uzatma Onayı Yazısı (md. 175/2)",
    (DocumentType.PARENT_MEETING, VARIANT_PARENT_INVITE): "Veli Davet Yazısı (md. 157/7-b)",
    (DocumentType.PARENT_MEETING, VARIANT_PARENT_MEETING): "Veli Görüşme Tutanağı (md. 157/7-b)",
    (DocumentType.PARENT_MEETING, VARIANT_PARENT_NO_SHOW): "Veli Gelmedi Tutanağı (md. 157/7-b)",
}
DOC_TITLES_BY_RECIPIENT: dict[tuple[str, str], str] = {
    (DocumentType.WARNING_LETTER, RECIPIENT_STUDENT): "Müdür Uyarısı Yazısı (Form-02)",
    (DocumentType.WARNING_LETTER, RECIPIENT_PARENT): "Müdür Uyarısı — Veli Bilgilendirme Yazısı",
    (DocumentType.PENALTY_NOTICE, RECIPIENT_STUDENT): "Disiplin Cezası Tebliği — Öğrenci (Form-14)",
    (DocumentType.PENALTY_NOTICE, RECIPIENT_PARENT): "Disiplin Cezası Tebliği — Veli (Form-15)",
    (
        DocumentType.PENALTY_DAYS_NOTICE,
        RECIPIENT_STUDENT,
    ): "Disiplin Ceza Günleri Tebliği — Öğrenci (Form-16)",
    (
        DocumentType.PENALTY_DAYS_NOTICE,
        RECIPIENT_PARENT,
    ): "Disiplin Ceza Günleri Tebliği — Veli (Form-17)",
    (DocumentType.BOARD_DECISION_NOTICE, RECIPIENT_STUDENT): "Üst Kurul Kararı Tebliği — Öğrenci",
    (DocumentType.BOARD_DECISION_NOTICE, RECIPIENT_PARENT): "Üst Kurul Kararı Tebliği — Veli",
}


def _effective_variant(document_type: str, variant: str) -> str:
    """Şablonu fiilen belirleyen sürüm (tanımsız/boş → türün ilk sürümü); sürümsüz türde ""."""
    by_variant = DOC_TEMPLATES_BY_VARIANT.get(document_type)
    if by_variant is None:
        return ""
    return variant if variant in by_variant else next(iter(by_variant))


def default_title(document_type: str, recipient: str = RECIPIENT_STUDENT, variant: str = "") -> str:
    """Kütük/dizi pusulası varsayılan başlığı — sürüm ve alıcıya göre ayrışır."""
    effective = _effective_variant(document_type, variant)
    if effective:
        by_variant = DOC_TITLES_BY_VARIANT.get((document_type, effective))
        if by_variant:
            return by_variant
    if document_type in DOC_TEMPLATES_BY_RECIPIENT:
        by_recipient = DOC_TITLES_BY_RECIPIENT.get((document_type, recipient))
        if by_recipient:
            return by_recipient
    return DOC_TITLES.get(document_type, "Disiplin belgesi")


def _stored_filename(case_no: str, document_type: str, recipient: str, variant: str) -> str:
    """Kütükten yeniden indirme adı — sürüm/alıcı eki aynı türün belgelerini ayırır."""
    suffix = _effective_variant(document_type, variant)
    if not suffix and document_type in DOC_TEMPLATES_BY_RECIPIENT:
        suffix = recipient
    return f"{case_no}-{document_type}{f'-{suffix}' if suffix else ''}.pdf"


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
        DocumentType.RETURN_LETTER,
        DocumentType.DISTRICT_REFERRAL_LETTER,
        DocumentType.APPROVAL_REQUEST_LETTER,
        DocumentType.PRECAUTION_MEM_LETTER,
        DocumentType.PARENT_MEETING,
        DocumentType.GUIDANCE_ASSESSMENT,
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
        DocumentType.NON_COMPLIANCE_RECORD,
    }
)

# Belge türü → dizi pusulasında varsayılan KANONİK süreç sırası (Form-0 kontrol formu
# + is-akisi.md akışı; Tur 103). Küçük = önce. Aralıklı (×10) → araya ekleme kolay.
# Tedbir (md.175) acele/erken; Dal A uyarı; Dal B ifade→bilgi→savunma→kurul→karar;
# tebliğ→ceza günleri→itiraz; dizi pusulası kapak (sonda); OTHER/manuel en sonda.
CANONICAL_DOC_ORDER: dict[str, int] = {
    DocumentType.PRECAUTION_NOTICE: 5,  # tedbir (md. 175, acele)
    DocumentType.PRECAUTION_MEM_LETTER: 6,  # tedbir MEM bildirimi/uzatma onayı (md. 175)
    DocumentType.SEARCH_RECORD: 3,  # arama tutanağı (md. 158/3 — olay tespiti, en başta)
    DocumentType.GUIDANCE_ASSESSMENT: 8,  # rehberlik değerlendirmesi Form-01 (md. 157/7-a)
    DocumentType.WARNING_LETTER: 10,  # müdür uyarısı Form-01/02 (md. 157/7)
    DocumentType.PARENT_MEETING: 12,  # veli daveti/görüşme/gelmedi (md. 157/7-b)
    DocumentType.STATEMENT_CALL: 20,  # ifadeye çağrı Form-3
    DocumentType.STATEMENT_RECORD: 30,  # ifade tutanağı Form-4/5/6
    DocumentType.INFO_GATHERING: 40,  # bilgi toplama Form-7/8
    DocumentType.DEFENSE_CALL: 50,  # savunmaya çağrı Form-9
    DocumentType.MEETING_CALL: 60,  # kurul toplantı çağrısı Form-10
    DocumentType.DEFENSE_RECORD: 70,  # savunma tutanağı Form-11
    DocumentType.NON_COMPLIANCE_RECORD: 75,  # ifade/savunma vermedi tespiti (md. 195)
    DocumentType.DEADLINE_EXTENSION: 80,  # süre uzatma Form-12/13
    DocumentType.COMMITTEE_DECISION: 90,  # EK-1 kurul kararı
    DocumentType.RETURN_LETTER: 92,  # md. 197 kurula iade
    DocumentType.DISTRICT_REFERRAL_LETTER: 94,  # md. 197 ilçe kuruluna gönderme
    DocumentType.APPROVAL_REQUEST_LETTER: 96,  # md. 169/1 onaya sevk
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
    # md. 195 tespit tutanağı savunma DEĞİLDİR (ifade/savunma vermeyen ya da gelmeyen
    # kişi için tutulur) — ayrı kategori (saha denetimi 14.11.2026). Frontend
    # `DOCUMENT_CATEGORIES` (api.ts) bu listeyle birebirdir.
    ("Tespit Tutanakları (md. 195)", frozenset({DocumentType.NON_COMPLIANCE_RECORD})),
    ("Bilgi Alma Tutanakları", frozenset({DocumentType.INFO_GATHERING})),
    (
        "Çağrı / Davet Yazıları",
        frozenset(
            {DocumentType.STATEMENT_CALL, DocumentType.DEFENSE_CALL, DocumentType.MEETING_CALL}
        ),
    ),
    (
        "Müdür Uyarısı",
        frozenset(
            {
                DocumentType.GUIDANCE_ASSESSMENT,
                DocumentType.WARNING_LETTER,
                DocumentType.PARENT_MEETING,
            }
        ),
    ),
    ("Arama Tutanakları", frozenset({DocumentType.SEARCH_RECORD})),
    (
        "Tedbir / Süre Uzatma",
        frozenset(
            {
                DocumentType.PRECAUTION_NOTICE,
                DocumentType.PRECAUTION_MEM_LETTER,
                DocumentType.DEADLINE_EXTENSION,
            }
        ),
    ),
    ("Kurul Kararı", frozenset({DocumentType.COMMITTEE_DECISION})),
    (
        "Onay / İade Yazıları",
        frozenset(
            {
                DocumentType.RETURN_LETTER,
                DocumentType.DISTRICT_REFERRAL_LETTER,
                DocumentType.APPROVAL_REQUEST_LETTER,
            }
        ),
    ),
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
        # Tanımsız/boş variant → türün İLK (varsayılan) şablonu.
        return by_variant.get(variant) or next(iter(by_variant.values()))
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


EK1_MAX_WIDE_PAGES = 2


def render_ek1_paged(template_name: str, context: dict[str, Any]) -> tuple[bytes, int]:
    """EK-1 kurul kararını karar defterine yapıştırmaya uygun basar (md. 196/1).

    Kullanıcı kararı (19.11.2026): önce SIKI düzen (`ek1_compact`) denenir; tek yaprağa
    sığıyorsa o basılır. Sığmıyorsa sıkıştırmanın anlamı yoktur → FERAH düzen basılır,
    yeter ki iki sayfayı aşmasın. Ferah düzen de ikiyi aşıyorsa (çok uzun metin) daha az
    sayfa tutan sıkı düzen basılır. Alan listesi iki düzende de aynıdır.
    """
    compact = render_pdf_paged(template_name, {**context, "ek1_compact": True})
    if compact[1] <= 1:
        return compact
    wide = render_pdf_paged(template_name, {**context, "ek1_compact": False})
    if wide[1] <= EK1_MAX_WIDE_PAGES:
        return wide
    return compact if compact[1] < wide[1] else wide


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
    from apps.okul.normalize import section_upper
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
        # Muhatap satırı ("<İLÇE> İLÇE MİLLÎ EĞİTİM MÜDÜRLÜĞÜNE") için ilçe adı TÜRKÇE
        # büyük harfle (i → İ; çıplak upper() değil — §7.2); kayıtlı değilse "" → şablon
        # noktalı yer tutucu basar (saha denetimi 14.11.2026).
        "district_upper": section_upper(identity["district"]),
        "case": case,
        "generated_at": timezone.now(),
    }


def _document_datetime(generated_on: date) -> datetime:
    """Belgeye basılacak tarih = kullanıcının SEÇTİĞİ üretim tarihi (kütükle aynı gün).

    Şablonlar `generated_at|date:'d.m.Y'` basar; eskiden burası hep "şimdi" idi ve
    geçmişe dönük üretilen davet yazısı, davet ettiği görüşmeden sonraki tarihi
    taşıyordu (saha denetimi 14.11.2026). Bugün üretilen belgede an korunur; başka bir
    günde yerel öğlen alınır — UTC'ye çevrilse de gün kaymaz (CLAUDE.md §7.1).
    """
    if generated_on == timezone.localdate():
        return timezone.now()
    return timezone.make_aware(datetime.combine(generated_on, time(12, 0)))


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


class _Signer:
    """Toplantıya katılan üyeyi imza ızgarasına ASIL üye olarak sunar.

    AYNEN şablon yedekleri (`is_substitute`) gizler; toplantıya asıl üyenin
    yerine katılan yedek de kararı imzalamak zorundadır (md. 186, 196/1).
    """

    is_substitute = False

    def __init__(self, member: Any) -> None:
        self.pk = member.pk
        self.member_name = member.member_name
        self.title = member.title
        self._member = member

    def get_member_type_display(self) -> str:
        return str(self._member.get_member_type_display())


class _CalledSubstitute(_Signer):
    """Form-10 çağrılanlar tablosunda toplantıya katılan YEDEK üye (md. 188/1, 191/2).

    `_Signer` ile aynı sunum (şablonun `is_substitute` süzgecinden geçer); `pk` üyenin
    kendi anahtarıdır. Kurul kaydı DEĞİŞMEZ — üye yedek kalır.

    K6 (kullanıcı kararı, 15.11.2026): görev sütunu "<görev> (Yedek Üye)" basılır (ör.
    "Öğretmen (Yedek Üye)") — çağrılan kişinin yedek üye olduğu yazıdan anlaşılsın. Şablon
    `m.title|default:m.get_member_type_display` okur; ibare bağlamda `title`'a eklenir.
    """

    def __init__(self, member: Any) -> None:
        super().__init__(member)
        base = (member.title or "").strip() or str(member.get_member_type_display())
        self.title = f"{base} (Yedek Üye)"


def _signing_members(case: DisciplineCase, committee: Any, meeting: Any | None = None) -> list[Any]:
    """Dosyayı görüşen HEYET — EK-1, Form-11 ve md. 195 tutanağı imza ızgaraları.

    md. 196/1 "karar bütün üyelerce imzalanır", md. 194/1 savunmayı kurul alır: imzayı
    işlemi yapan heyet atar. Dosyanın kurul toplantısı kaydı varsa katılanlar basılır
    (şikâyetçi üyenin yerine gelen yedek dahil — md. 191/2, 186). Kayıt yoksa kurulun
    üyeleri; ancak dosyada şikâyetçi / zarar gören (veya hakkında işlem yapılan) üye
    kurula katılamayacağından ızgaradan çıkarılır (md. 191/2 —
    `services.committee._check_conflicts` ile aynı küme).

    `meeting` (S8): EK-1'de kararın BAĞLI olduğu toplantı verilir; verilmezse dosyanın SON
    toplantısı (dosya düzeyindeki belgeler ve toplantısız girilmiş eski kararlar).
    """
    if committee is None:
        return []
    if meeting is None:
        meeting = selectors.meetings_for_case(case).first()
    if meeting is not None:
        # Sonradan kuruldan çıkarılan üye de o gün katılmış ve kararı imzalamıştır
        # (md. 196/1) — yeter sayı sayımıyla aynı küme (`services.committee.meeting_attendees`).
        attendees = services.committee.meeting_attendees(meeting)
        if attendees:
            # S7: başkanlık eden üye başkan hanesinde basılır (`_signing_panel`); üye
            # hanelerinde ikinci kez yer almaz. Vekâletsiz toplantıda liste aynen kalır.
            acting_id = meeting.acting_chair_id if meeting.chair_absent else None
            return [_Signer(m) for m in attendees if m.pk != acting_id]
    conflicted_users = set(
        case.participants.filter(role=ParticipantRole.VICTIM, user__isnull=False).values_list(
            "user_id", flat=True
        )
    )
    conflicted_students = set(
        case.participants.filter(
            role__in=[ParticipantRole.VICTIM, ParticipantRole.ACCUSED], student__isnull=False
        ).values_list("student_id", flat=True)
    )
    if case.petitioner_user_id is not None:
        conflicted_users.add(case.petitioner_user_id)
    if case.petitioner_student_id is not None and case.petitioner_role == "OGRENCI":
        conflicted_students.add(case.petitioner_student_id)
    return [
        m
        for m in selectors.committee_members(committee)
        if not (
            (m.member_user_id is not None and m.member_user_id in conflicted_users)
            or (m.member_student_id is not None and m.member_student_id in conflicted_students)
        )
    ]


#: md. 188/1: "Başkan bulunmadığında müdürün görevlendireceği öğretmen üyelerden biri kurula
#: başkanlık eder." Yönetmelik bu kişiye ayrı bir unvan ("vekil") vermez; belgede maddenin
#: kendi ifadesi kullanılır. TEK ifade (kullanıcı kararı, 14.11.2026 — S7/K1): EK-1, Form-11,
#: md. 195 tutanağı ve karar defterinde — ve K3 kapsamındaki diğer kurul evrakında — aynı metin.
ACTING_CHAIR_ROLE = "Kurula Başkanlık Eden Öğretmen Üye (md. 188)"

#: Form-12 giriş cümlesi: "… tarihinde <ifade> <ad> başkanlığında toplanarak" — şablondaki
#: sabit "Disiplin Kurulu Başkanı" yerine (kullanıcı kararı, 14.11.2026 — S7).
ACTING_CHAIR_PRESIDING = "md. 188 gereğince kurula başkanlık eden öğretmen üye"

#: Form-13 gövdesi: "… başlatılan ve <ifade> tarafından yürütülen disiplin soruşturması" —
#: şablondaki sabit "Disiplin Kurulu Başkanlığım" yerine. Dilekçeyi başkanlık eden öğretmen
#: üye imzalar; "başkanlığım" diyemez (başkan müdür yardımcısıdır — md. 188).
ACTING_CHAIR_OFFICE = "md. 188 uyarınca başkanlık ettiğim Disiplin Kurulu"


class _ActingChair:
    """Katılmayan başkanın yerine başkan hanesine basılan öğretmen üye (md. 188).

    Şablonlar başkan hanesinde `committee.chair.get_full_name|default:…username` okur.
    Ad satırı YALNIZ adı taşır; md. 188 ifadesi hane ETİKETİNDEDİR ve bağlamdan
    (`chair_role`) gelir: EK-1 ve Form-11 / md. 195 ızgarası (K1) ile Form-3, 4-6, 7-8, 9,
    10, 12, 13 (kullanıcı kararı, 14.11.2026 — S7; eski "ad — md. 188 ifadesi" satır içi eki
    kaldırıldı).
    """

    def __init__(self, member: Any) -> None:
        self.full_name = str(member.member_name)
        self.username = self.full_name
        # Başkan hanesine yazılan üyenin anahtarı: üye hanelerinde ikinci kez basılmasın (K4).
        self.member_pk = member.pk

    def get_full_name(self) -> str:
        return self.full_name


#: Başkan hanesinde ad yerine basılan boş satır — şablonların başkan tanımsızken kullandığı
#: noktalı çizginin aynısı (ör. `meeting_call.html`).
_BLANK_CHAIR_NAME = "…………………………"


class _BlankChair:
    """Kurula katılamayan başkanın yerine başkan hanesine BOŞ ad satırı basan vekil.

    md. 191/2: şikâyetçi / zarar gören başkan kurula katılamaz; dosyada vekâlet kaydı da
    yoksa kimin başkanlık ettiği bilinmez — ad uydurulmaz, hane elle doldurulur.
    """

    full_name = _BLANK_CHAIR_NAME
    username = _BLANK_CHAIR_NAME

    def get_full_name(self) -> str:
        return _BLANK_CHAIR_NAME


class _ActingCommittee:
    """Kurulu şablona yalnız `chair` alanı FARKLI sunan salt-okunur vekil (S7).

    Verilmeyen her alan kurul kaydına devredilir; kayıt DEĞİŞMEZ.
    """

    def __init__(self, committee: Any, chair: Any) -> None:
        self._committee = committee
        self.chair = chair

    def __getattr__(self, name: str) -> Any:
        return getattr(self._committee, name)


def _signing_panel(case: DisciplineCase, meeting: Any | None = None) -> dict[str, Any]:
    """İmza ızgarası bağlamı: dosyanın kurulu + işlemi yapan heyet (EK-1, Form-11, md. 195).

    VEKÂLET KAYDI (kullanıcı kararı, 14.11.2026 — S7): dosyanın SON toplantı kaydında başkan
    katılmadıysa (md. 191/2 şikâyetçi / zarar gören başkan ya da izin/rapor) katılmayan
    başkan BASILMAZ; başkan hanesine kurula başkanlık eden öğretmen üye yazılır (md. 188).
    Vekâlet kaydı olmayan toplantıda ve toplantı kaydı olmayan dosyada bağlam eskisiyle
    aynıdır (gerçek kurul nesnesi + `_signing_members`) — TEK istisna: başkan o dosyada
    şikâyetçi / zarar gören ise (md. 191/2) vekâlet kaydı olmasa da BASILMAZ; başkan hanesinin
    ad satırı boş (noktalı) kalır. S8 öncesi (toplantısız girilmiş) kararlarda ve S7 öncesi
    kaydedilmiş toplantılarda (vekâlet alanı yok) bu yol açıktır; üyeler için aynı
    süzme `_signing_members` içindedir. Evrak üretimi engellenmez: kapalı dosyada toplantı
    kaydedilemediği için ret, eski dosyada çıkışsız kalırdı (§7.6).

    `meeting` (S8): EK-1 kararın BAĞLI olduğu toplantıyı verir — heyet ve başkan / vekâlet o
    toplantıdan basılır. Verilmezse "SON toplantı" kuralı (yukarıdaki) aynen işler.
    """
    committee = selectors.committee_for_case(case)
    members = _signing_members(case, committee, meeting)
    if committee is not None:
        if meeting is None:
            meeting = selectors.meetings_for_case(case).first()
        if meeting is not None and meeting.chair_absent and meeting.acting_chair_id is not None:
            return {
                "committee": _ActingCommittee(committee, _ActingChair(meeting.acting_chair)),
                "members": members,
                # K1: hane etiketi — verilmezse şablon eski sabit metni basar.
                "chair_role": ACTING_CHAIR_ROLE,
            }
        if services.committee.chair_conflicted(case, committee):
            return {"committee": _ActingCommittee(committee, _BlankChair()), "members": members}
    return {"committee": committee, "members": members}


def _acting_chair_member(case: DisciplineCase) -> Any | None:
    """Dosyanın SON toplantı kaydında kurula başkanlık eden üye (vekâlet kaydı yoksa None)."""
    meeting = selectors.meetings_for_case(case).first()
    if meeting is not None and meeting.chair_absent and meeting.acting_chair_id is not None:
        return meeting.acting_chair
    return None


def _case_committee(case: DisciplineCase, *, acting: bool = True) -> Any:
    """Dosyanın kurulu — başkan hanesi dosyanın SON toplantı kaydına ve md. 191/2'ye göre.

    Kullanıcı kararı, 15.11.2026 — "izinli başkan durumunda da çağrı evrakı başkanlık edeni
    bassın": dosyanın SON toplantı kaydı vekâletliyse (başkan şikâyetçi / zarar gören olsun
    ya da yalnız izinli / raporlu olsun — md. 188/1) Form-3, 4-6, 7-8, 9, 10, 12, 13 başkan
    hanesine kurula başkanlık eden üye yazılır (ad satırı yalın; hane etiketi ve gövde
    ifadeleri `_committee_with_members_context` ile bağlamdan gelir). Böylece dosyanın bütün
    kurul evrakı EK-1, Form-11, md. 195 tutanağı ve karar defteriyle (`_signing_panel`) AYNI
    kişiyi basar. "Son kayıt" kuralı gereği toplantı kaydedilmeden ÖNCE üretilen çağrı asıl
    başkanla çıkar; vekâletli toplantıdan sonra vekâletsiz toplantı kaydedilirse evrak yeniden
    asıl başkanı basar.

    Kullanıcı kararı, 14.11.2026 — S7/K3: şikâyetçi / zarar gören başkan (md. 191/2) dosyanın
    BÜTÜN kurul evrakından çıkar (ceza tebliğleri dahil); vekâletli toplantı kaydı yoksa ad
    satırı boş (noktalı) kalır, ad uydurulmaz ve etiket şablonun eski sabit metnidir.

    `acting=False` (ceza tebliğleri): başkanlık eden üye HİÇ yazılmaz — etiket "Tebliğ Eden —
    Müdür Yardımcısı" sabittir; kurula başkanlık eden öğretmen üye tebliğ eden müdür
    yardımcısı değildir. Şikâyetçi / zarar gören başkanda hane boş kalır; izinli başkanda
    kurulun kendi kaydı döner (tebliği müdür yardımcısı kendisi yapabilir — çıktı AYNEN).

    Son toplantı kaydı vekâletli DEĞİLSE ve başkan şikâyetçi / zarar gören değilse kurulun
    kendi kaydı döner: bu belgelerin çıktısı AYNEN kalır.
    """
    committee = selectors.committee_for_case(case)
    if committee is None:
        return None
    member = _acting_chair_member(case) if acting else None
    if member is not None:
        return _ActingCommittee(committee, _ActingChair(member))
    if services.committee.chair_conflicted(case, committee):
        return _ActingCommittee(committee, _BlankChair())
    return committee


class _DecisionView:
    """Kararı şablona bazı alanları FARKLI değerle sunan salt-okunur vekil.

    Üst kurul cezayı onayda (md. 200/1-a) ya da itirazda (md. 200/1-Ç) değiştirdiğinde
    karar kaydı YENİ cezaya güncellenir (§8: puan ve yürürlük güncel cezadan türer).
    Okul kurulunun belgeleri ise kurulun VERDİĞİ cezayı basmalıdır; AYNEN şablonlar
    `decision.get_penalty_type_display` okuduğundan şablona dokunmadan bağlamda
    çözülür. Verilmeyen her alan karar kaydına devredilir; kayıt DEĞİŞMEZ.
    """

    def __init__(self, decision: Any, **overrides: Any) -> None:
        self._decision = decision
        self._overrides = overrides

    def __getattr__(self, name: str) -> Any:
        if name.startswith("__"):
            raise AttributeError(name)
        overrides = self.__dict__.get("_overrides", {})
        if name in overrides:
            return overrides[name]
        return getattr(self.__dict__["_decision"], name)

    def get_penalty_type_display(self) -> str:
        return str(PenaltyType(self.penalty_type).label)


# Yalnız üst kurul onayına bağlı cezalar (md. 169/2-b/c): onay mercii değişmediği
# (`_apply_penalty_change`) için, mercii ilçe/il olan ama cezası artık o olmayan karar
# onay aşamasında DEĞİŞTİRİLMİŞTİR — okul kurulunun verdiği ceza merciden okunur.
_PENALTY_BY_APPROVAL_BOARD: dict[str, str] = {
    ApprovalAuthority.DISTRICT_BOARD: PenaltyType.SCHOOL_CHANGE,
    ApprovalAuthority.PROVINCIAL_BOARD: PenaltyType.EXPULSION,
}


def _penalty_text(penalty_type: str, suspension_days: int | None) -> str:
    """Ceza adı (+ uzaklaştırmada gün sayısı): "Okuldan kısa süreli uzaklaştırma — 3 gün"."""
    label = str(PenaltyType(penalty_type).label)
    if penalty_type == PenaltyType.SHORT_TERM_SUSPENSION and suspension_days:
        return f"{label} — {suspension_days} gün"
    return label


def _reduced_appeal(decision: Any) -> Any:
    """Kararı DEĞİŞTİREN (REDUCED) son itiraz — eski ceza kaydıyla; yoksa None."""
    appeal = selectors.latest_resolved_appeal(decision)
    if appeal is None or appeal.result != AppealResult.REDUCED or not appeal.previous_penalty_type:
        return None
    return appeal


def _appealed_penalty(decision: Any) -> tuple[str, int | None] | None:
    """İtiraza KONU ceza (itiraz kurulu değiştirmeden önceki) — değişmediyse None."""
    appeal = _reduced_appeal(decision)
    if appeal is None:
        return None
    days = getattr(appeal, "previous_suspension_days", None)
    if appeal.previous_penalty_type != PenaltyType.SHORT_TERM_SUSPENSION:
        days = None
    if appeal.previous_penalty_type == decision.penalty_type and (
        days is None or days == decision.suspension_days
    ):
        return None  # tür aynı ve eski gün sayısı yok/aynı — gösterilecek fark yok
    return appeal.previous_penalty_type, days


def _stored_board_penalty(decision: Any) -> tuple[str, int | None, str] | None:
    """Kayıttaki özgün ceza (`board_penalty_*`): (tür, gün, değiştiren merci) ya da None.

    Alan boşsa (bilinmiyor / hiç değişmedi) ya da yürürlükteki cezayla aynıysa (ceza
    değişip kurulun verdiğine geri döndü — fark yok) None. İkisini çağıran ayırır:
    `_board_penalty` alan DOLUYKEN tahmine inmez.
    Değiştiren merci: itiraza KONU ceza (`DisciplineAppeal.previous_*`) kurulun
    verdiğinden farklıysa ceza önce ONAYDA değişmiştir; itiraz yoksa yalnız onayda.
    Onaylayan kurul md. 197 sevkinde ilçe kuruludur, değilse cezanın onay merciidir.
    """
    penalty_type = getattr(decision, "board_penalty_type", "")
    if not penalty_type:
        return None
    days = decision.board_suspension_days
    if penalty_type != PenaltyType.SHORT_TERM_SUSPENSION:
        days = None
    if penalty_type == decision.penalty_type and days == decision.suspension_days:
        return None
    authority = (
        ApprovalAuthority.DISTRICT_BOARD
        if decision.referred_to_district
        else decision.approval_authority
    )
    approved_by = f"onay aşamasında {ApprovalAuthority(authority).label}nca"
    appeal = _reduced_appeal(decision)
    if appeal is None:
        return penalty_type, days, approved_by
    appealed_by = f"itiraz üzerine {ApprovalAuthority(appeal.appeal_authority).label}nca"
    appealed_days = appeal.previous_suspension_days
    same_as_board = appeal.previous_penalty_type == penalty_type and (
        days is None or appealed_days is None or appealed_days == days
    )
    if same_as_board:
        return penalty_type, days, appealed_by  # ceza yalnız itirazda değişti
    return penalty_type, days, f"{approved_by}, ardından {appealed_by}"


def _board_penalty(decision: Any) -> tuple[str, int | None, str] | None:
    """Okul kurulunun VERDİĞİ ceza, sonradan değiştiyse: (tür, gün, değiştiren merci).

    Değişmediyse None. ASIL kaynak kayıttır (kullanıcı kararı 14.11.2026 — S11b):
    `decision.board_penalty_type` / `board_suspension_days` doluysa ONLAR basılır —
    md. 197 ile ilçeye giden karar ve gün sayısı dahil (`_stored_board_penalty`).
    Alan DOLUYSA tahmine HİÇ inilmez: ceza değişip kurulun verdiğine geri döndüyse
    (onayda değişiklik → itirazla özgün cezaya dönüş) fark yoktur, None döner — tahmin
    o durumda itiraza KONU cezayı "kurulun verdiği" diye basardı.
    Alan boşsa (ceza S11 göçünden ÖNCE değişmiş) eski TAHMİNE geri dönülür:
    (1) onay aşaması — yalnız onay mercii ilçe/il olan cezada merciden türetilir, gün
    sayısı bilinmez; (2) itiraz — `DisciplineAppeal.previous_*`. Tahminin SINIRI: göçten
    önce md. 197 ile ilçeye gidip onayda değişmiş kararda özgün ceza bilinemez → güncel
    ceza basılmaya devam eder.
    """
    if decision is None:
        return None
    if getattr(decision, "board_penalty_type", ""):
        return _stored_board_penalty(decision)
    approved_penalty: str | None = None
    approved_by = ""
    if not decision.referred_to_district:
        approved_penalty = _PENALTY_BY_APPROVAL_BOARD.get(decision.approval_authority)
        if approved_penalty is not None:
            board = str(ApprovalAuthority(decision.approval_authority).label)
            approved_by = f"onay aşamasında {board}nca"
    appealed = _appealed_penalty(decision)
    if appealed is not None:
        appeal = _reduced_appeal(decision)
        board = str(ApprovalAuthority(appeal.appeal_authority).label)
        appealed_by = f"itiraz üzerine {board}nca"
        if approved_penalty is not None and approved_penalty != appealed[0]:
            # Ceza önce onayda, sonra itirazda değişti: kurulun verdiği, onaya sunulandır.
            return approved_penalty, None, f"{approved_by}, ardından {appealed_by}"
        return appealed[0], appealed[1], appealed_by
    if approved_penalty is not None and approved_penalty != decision.penalty_type:
        return approved_penalty, None, approved_by
    return None


def _board_decision_context(decision: Any) -> dict[str, Any]:
    """Okul kurulu belgeleri için karar bağlamı — kurulun VERDİĞİ cezayla.

    `decision` ceza sonradan değiştiyse `_DecisionView` (kurulun cezası), değişmediyse
    kaydın kendisidir; `statute_label` aynı cezadan türer. Ek anahtarlar şablonların
    değişikliği ayrıca yazabilmesi içindir: `board_penalty_display` (kurulun verdiği),
    `current_penalty_display` (yürürlükteki) ve `penalty_change_note` (değişmediyse "").
    """
    if decision is None:
        return {
            "decision": None,
            "statute_label": statute_label(None),
            "board_penalty_display": "",
            "current_penalty_display": "",
            "penalty_change_note": "",
        }
    current = _penalty_text(decision.penalty_type, decision.suspension_days)
    original = _board_penalty(decision)
    if original is None:
        return {
            "decision": decision,
            "statute_label": statute_label(decision),
            "board_penalty_display": current,
            "current_penalty_display": current,
            "penalty_change_note": "",
        }
    penalty_type, days, changed_by = original
    view = _DecisionView(decision, penalty_type=penalty_type, suspension_days=days)
    board_text = _penalty_text(penalty_type, days)
    return {
        "decision": view,
        "statute_label": statute_label(view),
        "board_penalty_display": board_text,
        "current_penalty_display": current,
        "penalty_change_note": (
            f'Okul Öğrenci Ödül ve Disiplin Kurulunun verdiği "{board_text}" cezası, '
            f'{changed_by} "{current}" olarak değiştirilmiştir.'
        ),
    }


def _ek1_context(case: DisciplineCase, student: Any) -> dict[str, Any]:
    """EK-1 kurul kararı bağlamı — karar + anlatı alanları + kurul üyeleri (TAM-OTO)."""
    decision = case.decisions.filter(student_id=student.pk).first()
    # S8: karar toplantıya bağlıysa (ve toplantı canlıysa) imza heyeti o toplantıdır —
    # md. 196/1 kararı, onu veren heyet imzalar. Bağ yoksa (S8 öncesi karar / karar yok)
    # dosyanın SON toplantısı (S7 kuralı).
    meeting = None
    if decision is not None and decision.meeting_id is not None:
        bound = decision.meeting
        if bound is not None and bound.deleted_at is None:
            meeting = bound
    return {
        **_common_context(case),
        "student": _student_context(student),
        **_board_decision_context(decision),
        **_signing_panel(case, meeting),
    }


# Dal A (yalnız yazılı uyarı) dosyasında üretilebilir belge türleri (Tur 214, F17):
# frontend workflow.ts BRANCH_A_DOC_TYPES + dizi pusulası (Dal A'da müdürlük antediyle
# üretilir, Tur 213). Kurul formları kurul antedi/imza ızgarası bastığından Dal A'da
# mevzuata aykırı görüntü oluşturur.
_BRANCH_A_ALLOWED: frozenset[str] = frozenset(
    {
        DocumentType.WARNING_LETTER,
        DocumentType.PRECAUTION_NOTICE,
        DocumentType.PRECAUTION_MEM_LETTER,
        DocumentType.PARENT_MEETING,
        DocumentType.GUIDANCE_ASSESSMENT,
        DocumentType.SEARCH_RECORD,
        DocumentType.INDEX_SHEET,
    }
)


def _case_referred_to_committee(case: DisciplineCase) -> bool:
    """Dosya kurula sevk edildi mi? (Dal B) — EN SON DECIDED olayının müdür kararından.

    Yanlış "yazılı uyarı" seçimi aşama geri alınıp kurula sevkle düzeltildiğinde
    dal da düzelmeli; ilk olay esas alınsaydı dosya Dal A'da kilitli kalırdı.
    """
    decided = case.events.filter(stage=CaseStage.DECIDED).order_by("-recorded_at", "-id").first()
    pds = (decided.principal_decisions or []) if decided else []
    return any(
        d in (PrincipalDecision.HONOR_COMMITTEE, PrincipalDecision.DISCIPLINE_COMMITTEE)
        for d in pds
    )


def _keep_title_with_source(doc: Any) -> None:
    """Dizi pusulasında "kimden" girilmiş HARİCİ evrakın başlığı kaybolmasın.

    AYNEN şablon (index_sheet) `source_label` doluysa başlık yerine yalnız "kimden"i
    basar (Tur 140 — katılımcı belgelerinde ifade/savunma/çağrı kategorisi türü zaten
    söyler). Katılımcı belgesi OLMAYAN evrakta (elle eklenen "Diğer Evrak" vb.)
    kullanıcının yazdığı başlık tek ayırt edici bilgidir → "Başlık — Sıfat: Ad"
    biçiminde sunulur. Yalnız bellekteki nesne değişir; kütük kaydı YAZILMAZ.
    """
    if not doc.source_label or doc.document_type in PARTICIPANT_REQUIRED:
        return
    title = (doc.title or "").strip()
    if title:
        doc.source_label = f"{title} — {doc.source_label}"


def _index_sheet_context(case: DisciplineCase) -> dict[str, Any]:
    """Dizi pusulası bağlamı — ana evraklar + alt evraklar + toplam sayfa (Tur 104).

    Düzenleyen dala göre (Tur 109): kurula sevk edilen (Dal B) dosyayı kurul başkanı,
    uyarıyla/triajla yürüyen (Dal A) dosyayı okul müdürü düzenler. Antet birimi de
    dala göre (Tur 213, talep 3): Dal A "Okul Müdürlüğü", Dal B kurul birimi.
    """
    documents = selectors.document_timeline(case)
    for doc in documents:
        _keep_title_with_source(doc)
        for sub in doc.sub_documents.all():
            _keep_title_with_source(sub)
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
        committee = selectors.committee_for_case(case)
        chair = committee.chair if committee else None
        ctx["compiler_name"] = chair.full_name if chair else ""
        ctx["compiler_role"] = "Düzenleyen / Disiplin Kurulu Başkanı"
        acting = _acting_chair_member(case) if committee is not None else None
        if acting is not None:
            # Kullanıcı kararı, 15.11.2026: dosyanın SON toplantı kaydı vekâletliyse (başkan
            # şikâyetçi / zarar gören ya da yalnız izinli) düzenleyen, kurula başkanlık eden
            # üyedir (md. 188 ifadesiyle) — öteki kurul evrakıyla aynı kişi (`_case_committee`).
            ctx["compiler_name"] = acting.member_name
            ctx["compiler_role"] = f"Düzenleyen / {ACTING_CHAIR_ROLE}"
        elif committee is not None and services.committee.chair_conflicted(case, committee):
            # S7/K3 (14.11.2026): şikâyetçi / zarar gören başkan dosyayı düzenleyen olarak da
            # basılmaz (md. 191/2); vekâlet kaydı yoksa ad boş — şablon noktalı çizgi basar.
            ctx["compiler_name"] = ""
    else:
        ctx["compiler_name"] = ctx.get("principal_name", "")
        ctx["compiler_role"] = "Düzenleyen / Okul Müdürü"
    return ctx


def _committee_context(case: DisciplineCase) -> dict[str, Any]:
    """Tebliğ eden (müdür yrd. / kurul başkanı) için dosyanın kurulu (md. 185/4).

    S7/K3: başkan dosyada şikâyetçi / zarar gören ise tebliğ eden hanesinin ad satırı boş
    (noktalı) basılır. İzinli başkanın vekâletli dosyasında (15.11.2026 kararı kapsam DIŞI)
    asıl başkan basılmaya devam eder — bkz. `_case_committee(acting=False)`.
    """
    return {"committee": _case_committee(case, acting=False)}


def _penalty_notice_context(case: DisciplineCase, student: Any) -> dict[str, Any]:
    """Ceza tebliği (Form-14/15) bağlamı — karar + (veli sürümünde) veli + kurul.

    Tebliğ YÜRÜRLÜKTEKİ cezayı bildirir: `decision` karar kaydının KENDİSİDİR (kurulun
    verdiği ceza görünümü değil) — öğrenci (Form-14) ve veli (Form-15) suretleri aynı
    cezayı taşır. Ceza üst kurulca değiştirildiyse kurulun verdiği ceza yalnız
    `penalty_change_note` ile, İKİ surette de ayrı paragrafta anlatılır (Form-14'e
    kullanıcı kararıyla eklendi, 14.11.2026 — S3). EK-1, karar
    defteri, Form-18 ve onaya sevk/iade/ilçe yazıları kurulun verdiği cezayı basmayı
    sürdürür (`_board_decision_context`).
    """
    decision = case.decisions.filter(student_id=student.pk).first()
    if decision is not None:
        from apps.disiplin.services.decisions import ensure_decision_no

        ensure_decision_no(decision)
    shown = _board_decision_context(decision)
    change_note = shown["penalty_change_note"]
    if change_note:
        change_note = f"İşbu yazı ile tebliğ edilen ceza yürürlükteki cezadır. {change_note}"
    return {
        **_common_context(case),
        **_committee_context(case),
        "student": _student_context(student),
        "parent": _parent_context(student),
        **shown,
        "decision": decision,
        "statute_label": statute_label(decision),
        "penalty_change_note": change_note,
        # md. 194/1: "savunması alınmış" yalnız Form-11 kaydı varsa basılır.
        "defense_taken": selectors.defense_recorded(case, student.pk),
    }


def _suspension_dates(decision: Any) -> dict[str, Any]:
    """Uzaklaştırma başlangıç/bitiş/okula-başlama (md. 164/2, 172) — iş günü (tatil hariç).

    `enforcement_start_date` + `suspension_days` varsa hesaplanır; biri yoksa hepsi
    None (şablon "…/…/202…" gösterir). İş günü yüklemi `core.services.is_working_day`
    (resmî/idari tatilleri atlar; ADR-0002 açık servis arayüzü, Tur 90 deseni).
    """
    from apps.disiplin import discipline_periods
    from apps.okul.services.calendar import is_school_open_day

    start = getattr(decision, "enforcement_start_date", None) if decision else None
    days = getattr(decision, "suspension_days", None) if decision else None
    if start is None or not days:
        return {"enforcement_start": None, "enforcement_end": None, "school_return": None}
    # md. 172/1-a: uzaklaştırma "okulun AÇIK olduğu sürede" çekilir — ara tatil,
    # yarıyıl ve yaz günleri (idari iş günü olsalar da) ceza günü sayılmaz; okula
    # başlama da okulun açık olduğu ilk gündür.
    pred = is_school_open_day
    if not pred(start):
        raise ValueError(
            "Uzaklaştırma başlangıcı okulun açık olduğu bir gün değil (hafta sonu, tatil "
            "veya ara tatil); EK-1 anlatısından uygulama başlangıcını düzeltin (md. 172/1-a)."
        )
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
        **_committee_context(case),
        "student": _student_context(student),
        "parent": _parent_context(student),
        "decision": decision,
        "statute_label": statute_label(decision),
        # md. 194/1: "savunması alınmış" yalnız Form-11 kaydı varsa basılır.
        "defense_taken": selectors.defense_recorded(case, student.pk),
        "suspension_days_text": _SUSPENSION_DAYS_TEXT.get(days) if days else None,
        **_suspension_dates(decision),
    }


# Form-18 metin parçaları (kullanıcı kararı 26.09.2026: şablon kayıttan doldurulur).
_APPEAL_FILER_PHRASE: dict[str, str] = {
    "PARENT": "Öğrenci velisi",
    "STUDENT_ADULT": "18 yaşını tamamlamış öğrenci",
    "PRINCIPAL": "Okul müdürü olarak tarafımdan",
}
# İtiraz merciine göre md. 169 atfı (mercii kayıttan: onaylayan merciin bir üstü).
_APPEAL_BOARD_TEXT: dict[str, str] = {
    ApprovalAuthority.DISTRICT_BOARD: (
        'Yönetmeliğin 169. maddesi 3. fıkrası (a) bendi uyarınca; "Kınama ve okuldan '
        'kısa süreli uzaklaştırma cezalarına itiraz ilçe öğrenci disiplin kurulunca"'
    ),
    ApprovalAuthority.PROVINCIAL_BOARD: (
        'Yönetmeliğin 169. maddesi 3. fıkrası (b) bendi uyarınca; "Okul değiştirme '
        'cezasına itiraz il öğrenci disiplin kurulunca"'
    ),
    ApprovalAuthority.UPPER_BOARD: (
        'Yönetmeliğin 169. maddesi 3. fıkrası (c) bendi uyarınca; "Örgün eğitim dışına '
        'çıkarma cezasına itiraz öğrenci üst disiplin kurulunca"'
    ),
}
_APPEAL_BOARD_TEXT_REFERRED = (
    "Karar, Yönetmeliğin 197. maddesi uyarınca ilçe öğrenci disiplin kurulunca karara "
    'bağlandığından; 169. maddesi 4. fıkrası ("Kararı onayan kurul aynı karara yönelik '
    'itirazları görüşemez") ve 202. maddesi 1. fıkrası (b) bendi uyarınca itiraz il '
    "öğrenci disiplin kurulunca"
)


def _approval_phrase(decision: Any) -> str:
    """Kararı kimin onayladığı/bağladığı — "kesinleşmiştir" DENMEZ (itiraz derdest)."""
    if decision is None:
        return "……………… onaylanmıştır"
    if decision.referred_to_district:
        return (
            "müdürlüğümüzce Yönetmeliğin 197. maddesi uyarınca gönderildiği ilçe öğrenci "
            "disiplin kurulunca karara bağlanmıştır"
        )
    if decision.approval_authority == ApprovalAuthority.DISTRICT_BOARD:
        return "ilçe öğrenci disiplin kurulunca onaylanmıştır (md. 169/2-b)"
    if decision.approval_authority == ApprovalAuthority.PROVINCIAL_BOARD:
        return "il öğrenci disiplin kurulunca onaylanmıştır (md. 169/2-c)"
    return "tarafımdan onaylanmıştır (md. 169/2-a)"


def _appeal_letter_context(case: DisciplineCase, student: Any) -> dict[str, Any]:
    """İl/İlçe itiraz yazısı (Form-18) bağlamı — karar + en son itiraz dilekçesi.

    İtiraz eden (veli / 18+ öğrenci / müdür), süre içinde olup olmadığı ve itiraz
    mercii KAYITTAN basılır (md. 169/3-4, 202/1-b); onaylanan karar itiraz derdestken
    "kesinleşmiş" yazılmaz.
    """
    decision = case.decisions.filter(student_id=student.pk).first()
    appeal = None
    if decision is not None:
        appeal = selectors.appeals_for_decision(decision).first()
    filer_role = appeal.filed_by_role if appeal else "PARENT"
    if appeal is not None and decision is not None and decision.referred_to_district:
        board_text = _APPEAL_BOARD_TEXT_REFERRED
    elif appeal is not None:
        board_text = _APPEAL_BOARD_TEXT.get(
            appeal.appeal_authority, _APPEAL_BOARD_TEXT[ApprovalAuthority.DISTRICT_BOARD]
        )
    else:
        board_text = _APPEAL_BOARD_TEXT[ApprovalAuthority.DISTRICT_BOARD]
    return {
        **_common_context(case),
        "student": _student_context(student),
        # "İlgi (a) karar ile … cezası verilmiş": okul kurulunun VERDİĞİ ceza.
        **_board_decision_context(decision),
        "appeal": appeal,
        "appeal_filer_phrase": _APPEAL_FILER_PHRASE.get(filer_role, "Öğrenci velisi"),
        "appeal_by_principal": filer_role == "PRINCIPAL",
        "appeal_within_deadline": appeal.within_deadline if appeal else True,
        "approval_phrase": _approval_phrase(decision),
        "appeal_board_text": board_text,
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
    if kind == NOTICE_KIND_APPROVAL:
        # md. 169/2-a: kınama ve kısa süreli uzaklaştırmayı MÜDÜR onaylar; bu cezalarda
        # üst kurul kararı ancak md. 197 ısrar-sevkiyle doğar. İlçeye gönderilmemiş
        # kararda "ilçe kurulunca onaylanmıştır (md. 197)" basılamaz.
        if (
            decision.approval_authority == ApprovalAuthority.PRINCIPAL
            and not decision.referred_to_district
        ):
            raise ValueError(
                "Karar ilçe kuruluna gönderilmemiş (md. 197); bu cezayı okul müdürü onaylar "
                "(md. 169/2-a) — üst kurul onay tebliği üretilemez."
            )
        # md. 163/2, 169/2: onaysız karar tebliğ edilemez.
        if decision.approval_status != DecisionApprovalStatus.APPROVED:
            raise ValueError(
                "Karar henüz onaylanmamış; önce üst kurulun onay kararını kaydedin, "
                "sonra tebliği üretin (md. 169/2)."
            )

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
    current_text = _penalty_text(decision.penalty_type, decision.suspension_days)
    if kind == NOTICE_KIND_APPROVAL:
        # "Okul kurulunun kararı ile verilen … cezası … onaylanmıştır / değiştirilerek
        # onaylanmıştır": cümlenin öznesi kurulun VERDİĞİ cezadır (md. 200/1-a).
        decision_ctx = _board_decision_context(decision)
        appealed_text = current_text
    else:
        # "… cezasına karşı yapılan itiraz": itiraza KONU ceza — itiraz kurulu
        # değiştirdiyse yeni ceza değil, değişmeden önceki (md. 200/1-Ç).
        appealed = _appealed_penalty(decision)
        shown: Any = decision
        if appealed is not None:
            shown = _DecisionView(decision, penalty_type=appealed[0], suspension_days=appealed[1])
        appealed_text = _penalty_text(shown.penalty_type, shown.suspension_days)
        decision_ctx = {
            "decision": shown,
            "statute_label": statute_label(shown),
            "board_penalty_display": appealed_text,
            "current_penalty_display": current_text,
            "penalty_change_note": "",
        }
    return {
        **_common_context(case),
        **_committee_context(case),
        "student": _student_context(student),
        "parent": _parent_context(student),
        **decision_ctx,
        "appealed_penalty_display": appealed_text,
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


# --- M2 Grup 1 süreç yazıları (kullanıcı kararı 27.09.2026) ---

_MD197_REFER_MARK = "\n\nİlçeye sevk: "


def _split_md197_reasons(text: str) -> tuple[str, str]:
    """`return_reason` → (iade gerekçesi, ilçeye sevk görüş/teklifi).

    `services.decisions.record_principal_review` REFER'de sevk gerekçesini iade
    gerekçesinin altına "İlçeye sevk: " ile ekler; ikisi de yazıya ayrı basılır.
    """
    text = text or ""
    if _MD197_REFER_MARK in text:
        head, tail = text.split(_MD197_REFER_MARK, 1)
        return head.strip(), tail.strip()
    return text.strip(), ""


def _decision_for_letter(case: DisciplineCase, student: Any) -> Any:
    decision = case.decisions.filter(student_id=student.pk).first()
    if decision is None:
        raise ValueError("Dosyada bu öğrenci için kurul kararı yok.")
    return decision


def _md197_letter_context(case: DisciplineCase, student: Any) -> dict[str, Any]:
    """md. 197 iade / ilçeye gönderme yazısı bağlamı — karar + iki gerekçe."""
    decision = _decision_for_letter(case, student)
    return_part, refer_part = _split_md197_reasons(decision.return_reason)
    return {
        **_common_context(case, unit=""),  # müdür yazısı — kurul belgesi değil
        **_committee_context(case),
        "student": _student_context(student),
        **_board_decision_context(decision),
        "return_reason_text": return_part,
        "refer_reason_text": refer_part,
    }


def _approval_request_context(case: DisciplineCase, student: Any) -> dict[str, Any]:
    """md. 169/1 onaya sevk üst yazısı — onay mercii (169/2-b/c) karardan."""
    decision = _decision_for_letter(case, student)
    return {
        **_common_context(case, unit=""),
        "student": _student_context(student),
        # Onaya SUNULAN ceza kurulun verdiğidir (onayda değişmiş olsa bile).
        **_board_decision_context(decision),
        "to_provincial": decision.approval_authority == ApprovalAuthority.PROVINCIAL_BOARD,
    }


def _precaution_mem_context(case: DisciplineCase, student: Any) -> dict[str, Any]:
    """md. 175 MEM yazısı — yürürlükteki (yoksa en son) tedbir + sıradaki uzatma no."""
    precaution = selectors.active_precaution(case, student.pk) or (
        selectors.precautions_for_case(case).filter(student_id=student.pk).first()
    )
    if precaution is None:
        raise ValueError("Bu öğrenci için dosyada tedbir (md. 175) kaydı yok.")
    return {
        **_common_context(case, unit=""),
        "student": _student_context(student),
        "precaution": precaution,
        "next_extension_no": precaution.extension_count + 1,
    }


# --- M2 Grup 2 tutanakları (kullanıcı kararı 27.09.2026) ---


def _class_staff_context(student: Any) -> dict[str, Any]:
    """Öğrencinin şubesinin sınıf rehber öğretmeni / rehber öğretmeni / müdür yardımcısı.

    Ayarlar > Sınıf sorumluları eşleştirmesinden (aktif ders yılı); yoksa boş (elle).
    """
    from apps.okul import selectors as okul_selectors

    row = None
    if student.class_level is not None and student.class_section:
        row = (
            okul_selectors.class_responsibilities()
            .filter(class_level=student.class_level, class_section=student.class_section)
            .first()
        )

    def _name(person: Any) -> str:
        return person.full_name if person is not None else ""

    return {
        "class_teacher_name": _name(row.class_teacher) if row else "",
        "guidance_teacher_name": _name(row.guidance_teacher) if row else "",
        "assistant_principal_name": _name(row.assistant_principal) if row else "",
    }


def _parent_meeting_context(
    case: DisciplineCase, student: Any, extra: dict[str, Any]
) -> dict[str, Any]:
    """md. 157/7-b veli daveti / görüşme / gelmedi tutanağı — veli + sınıf sorumluları."""
    warning = case.warnings.filter(student_id=student.pk).order_by("-warning_date", "-pk").first()
    return {
        **_common_context(case, unit=""),  # müdür işlemi (Dal A)
        "student": _student_context(student),
        "parent": _parent_context(student),
        "warning": warning,
        **_class_staff_context(student),
        **_schedule_context(extra),
    }


def _guidance_assessment_context(case: DisciplineCase, student: Any) -> dict[str, Any]:
    """md. 157/7-a Form-01 — sınıf rehber + rehber öğretmenin değerlendirme ve önerileri.

    "Daha önce disiplin cezası almamış olmak kaydıyla ... ilk defa" koşulu için
    yürürlükteki önceki cezalar (`penalties_in_force`) listelenir; davranış özeti
    uyarı kaydından (yoksa elle).
    """
    warning = case.warnings.filter(student_id=student.pk).order_by("-warning_date", "-pk").first()
    prior = list(
        selectors.penalties_in_force(
            DisciplineDecision.objects.filter(student_id=student.pk).exclude(case=case)
        ).order_by("decision_date")
    )
    return {
        **_common_context(case, unit=""),
        "student": _student_context(student),
        "warning": warning,
        "prior_penalties": prior,
        **_class_staff_context(student),
    }


def _search_record_context(case: DisciplineCase, extra: dict[str, Any]) -> dict[str, Any]:
    """md. 158/3 arama tutanağı — iki nüsha; gerekçe/yer/bulunanlar elle, müdür onaylı."""
    return {
        **_common_context(case, unit=""),
        **_schedule_context(extra),
    }


def _non_compliance_context(
    case: DisciplineCase, participant: Any, extra: dict[str, Any]
) -> dict[str, Any]:
    """md. 195 tespit tutanağı — ifade vermeyen / savunmada bulunmayan / gelmeyen kişi."""
    return {
        **_common_context(case),
        **_committee_signers_context(case),
        "participant": _participant_context(participant),
        **_schedule_context(extra),
    }


# --- Dal B ifade/savunma/bilgi formları (Tur 106) — katılımcı + kurul + geçici alanlar ---


def _transaction_date(extra: dict[str, Any]) -> date | None:
    """Çağrı / ifade evrakının İŞLEM TARİHİ (K1, 15.11.2026).

    Çağrılan toplantının / ifadenin / savunmanın tarihi (`statement_date` — Form-3, 9, 10
    formlarında girilir); verilmediyse belgenin üretim tarihi (`generated_on` —
    `generate_document` bağlama taşır; Form-4/5/6 ve Form-7/8'de tarih alanı şablona
    basılmaz, istek de göndermezse ölçüt üretim tarihidir). İkisi de yoksa None: tarih aranmaz.
    """
    on = extra.get("statement_date") or extra.get("generated_on")
    return on if isinstance(on, date) else None


def _committee_with_members_context(
    case: DisciplineCase, *, on: date | None = None
) -> dict[str, Any]:
    """Dosyanın kurulu + üyeleri (asıl+yedek) — imza ızgaraları için (EK-1 deseni).

    Başkan hanesi `_case_committee` kuralıyla basılır (son toplantı kaydı vekâletliyse
    başkanlık eden üye; şikâyetçi / zarar gören başkan + vekâlet kaydı yoksa boş hane); üye
    listesi kurulun kendi listesidir.

    Kullanıcı kararı, 14.11.2026 — S7 (Form-3, 4-6, 7-8, 9, 10, 12, 13): başkan hanesine
    kurula başkanlık eden üye yazılıyorsa hane ETİKETİ (`chair_role`) ve Form-12 / Form-13
    gövde ifadeleri (`chair_presiding`, `chair_office`) de bağlamdan verilir; o üye üye
    listesinden çıkar — Form-12 ızgarasında iki kez imzalamaz, Form-10'da çağrıyı imzalayan
    kişi kendini çağırmaz. 15.11.2026 kararıyla bu, başkan şikâyetçi / zarar gören OLMASA DA
    (izinli başkan) geçerlidir. Dosyanın son toplantı kaydı vekâletli değilse bu anahtarlar
    VERİLMEZ, liste aynen kalır: şablon eski sabit metni basar.

    `on` — DÖNEN BAŞKAN (kullanıcı kararı, 15.11.2026 — K1): çağrı ve ifade evrakı (Form-3,
    4-6, 7-8, 9, 10) belgenin işlem tarihini (`_transaction_date`) verir. Başkan yalnız
    izinliyse (dosyada şikâyetçi / zarar gören DEĞİLSE) vekâlet toplantıya özgüdür: işlem
    tarihi dosyanın son (vekâletli) toplantısının tarihinden SONRA ise başkan dönmüştür —
    kurulun kendi kaydı, eski sabit etiket ve kurulun kendi üye listesi basılır. İşlem tarihi
    o toplantının tarihine eşit ya da öncesiyse başkanlık eden üye basılır. Şikâyetçi / zarar
    gören başkanda tarih ARANMAZ (md. 191/2: hiçbir oturuma katılamaz). `on` verilmezse
    (dizi pusulası, Form-12/13 — onların kendi kuralı: `_extension_panel`) tarih aranmaz.
    """
    committee = selectors.committee_for_case(case)
    members = list(selectors.committee_members(committee)) if committee else []
    if on is not None and committee is not None:
        last = selectors.meetings_for_case(case).first()
        if (
            last is not None
            and last.chair_absent
            and last.acting_chair_id is not None
            and on > last.meeting_date
            and not services.committee.chair_conflicted(case, committee)
        ):
            return {"committee": committee, "members": members}
    shown = _case_committee(case)
    panel: dict[str, Any] = {"committee": shown, "members": members}
    if isinstance(shown, _ActingCommittee) and isinstance(shown.chair, _ActingChair):
        acting = _acting_chair_member(case)
        if acting is not None:
            panel["members"] = [m for m in members if m.pk != acting.pk]
        panel["chair_role"] = ACTING_CHAIR_ROLE
        panel["chair_presiding"] = ACTING_CHAIR_PRESIDING
        panel["chair_office"] = ACTING_CHAIR_OFFICE
    return panel


def _committee_signers_context(case: DisciplineCase) -> dict[str, Any]:
    """Dosyanın kurulu + işlemi yapan HEYET — Form-11 "Savunmayı Alanlar" ve md. 195
    tutanağı imza ızgarası (EK-1 ile aynı heyet; bkz. `_signing_members`, `_signing_panel`)."""
    return _signing_panel(case)


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
        **_committee_with_members_context(case, on=_transaction_date(extra)),
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
        **_committee_with_members_context(case, on=_transaction_date(extra)),
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
        **_committee_with_members_context(case, on=_transaction_date(extra)),
        "participant": _participant_context(participant),
        "variant": (extra.get("variant") or "student").strip() or "student",
    }


def _defense_call_context(
    case: DisciplineCase, participant: Any, extra: dict[str, Any]
) -> dict[str, Any]:
    """Savunmaya çağrı (Form-9, md. 194) — suçlanan + tebliğ/tebellüğ + zaman."""
    return {
        **_common_context(case),
        **_committee_with_members_context(case, on=_transaction_date(extra)),
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
        **_committee_signers_context(case),
        "participant": _participant_context(participant),
        "statement_subject": (extra.get("statement_subject") or "").strip(),
        "statement_body": (extra.get("statement_body") or "").strip(),
        **_schedule_context(extra),
    }


def _meeting_call_context(case: DisciplineCase, extra: dict[str, Any]) -> dict[str, Any]:
    """Kurul toplantı çağrısı (Form-10, md. 190-191) — üye listesi + toplantı zamanı.

    S7 (14.11.2026; 15.11.2026'dan beri izinli başkanda da): çağrıyı kurula başkanlık eden
    öğretmen üye imzalıyorsa (dosyanın son toplantı kaydı vekâletli) o kayıtta KATILAN yedek üye
    çağrılanlar tablosunda basılır — md. 188/1 "Üyenin başkanlık yaptığı durumlarda yedek
    üye toplantıya katılır", md. 191/2 "yerine yedek üye toplantıya çağrılır". AYNEN şablon
    yedekleri (`is_substitute`) gizlediği için yedek üye bağlamda `_CalledSubstitute` ile
    sunulur (şablon değişmez). Kayıtta yedek yoksa ad uydurulmaz; öteki bütün durumlarda
    liste kurulun kendi listesidir (çıktı aynen).

    K1 (15.11.2026): izinli başkanda çağrılan toplantının tarihi (verilmediyse üretim tarihi)
    vekâletli toplantıdan SONRA ise çağrıyı asıl başkan imzalar, liste kurulun kendi listesidir.
    K6: tabloda basılan yedek üyenin görev sütunu "<görev> (Yedek Üye)" (`_CalledSubstitute`).
    """
    panel = _committee_with_members_context(case, on=_transaction_date(extra))
    if "chair_role" in panel:
        meeting = selectors.meetings_for_case(case).first()
        attended = (
            {m.pk for m in services.committee.meeting_attendees(meeting)} if meeting else set()
        )
        panel["members"] = [
            _CalledSubstitute(m) if m.is_substitute and m.pk in attended else m
            for m in panel["members"]
        ]
    return {
        **_common_context(case),
        **panel,
        **_schedule_context(extra),
    }


# Gün sayısının yazıyla hâli (Form-13 "… (beş) iş günü"; md. 192/3 uzatması 1-10 iş günü).
_DAYS_TEXT: dict[int, str] = {
    1: "bir",
    2: "iki",
    3: "üç",
    4: "dört",
    5: "beş",
    6: "altı",
    7: "yedi",
    8: "sekiz",
    9: "dokuz",
    10: "on",
}


def _extension_panel(case: DisciplineCase, extension: Any) -> dict[str, Any]:
    """Form-12 / Form-13 kurul bağlamı — izinli başkanda uzatma GÜNÜNDEKİ toplantıya bakar.

    Kullanıcı kararı, 15.11.2026 ("tarihe baksın"): başkan yalnız izinliyse (şikâyetçi / zarar
    gören değilse) vekâlet toplantıya özgüdür. Süre uzatma kararına (md. 192/3) o gün kim
    başkanlık ettiyse o basılır; ölçüt, tarihi uzatma tarihine eşit ya da ondan önceki EN GEÇ
    toplantı kaydıdır (uzatma kaydı toplantıya bağlı değildir):

    * öyle bir toplantı yoksa ya da vekâletli değilse o gün kurula asıl başkan başkanlık
      etmiştir — kurulun kendi kaydı basılır ("md. 188 gereğince … başkanlığında" denmez:
      tutanak gerçeğe aykırı olurdu);
    * vekâletliyse O toplantıda başkanlık eden üye basılır (dosyada daha sonra başka bir
      vekâletli toplantı olsa da — yalnız son toplantıya bakmak ilk oturumda alınan uzatmayı
      katılmamış başkanla basıyordu).

    Bu, dosyanın SON toplantı kaydı vekâletli olmasa da geçerlidir (16.11.2026): uzatma günü
    vekâletli toplantı varsa, sonradan başkanın katıldığı toplantı kaydedilmiş olsa da o günün
    başkanlık edeni basılır — yoksa Form-12 ızgarası (K4) o günün katılanlarını, başkan hanesi
    o gün katılmamış başkanı taşırdı. Başkan şikâyetçi / zarar gören ise (md. 191/2: hiçbir
    oturuma katılamaz) asıl başkan hiçbir durumda basılmaz: uzatma günündeki toplantı vekâletliyse
    O toplantının başkanlık edeni (iki vekâletli toplantıda başkanlık eden farklıysa doğru kişi),
    değilse `_committee_with_members_context` sonucu aynen döner.
    """
    panel = _committee_with_members_context(case)
    if extension is None:
        return panel
    committee = selectors.committee_for_case(case)
    if committee is None:
        return panel
    members = list(selectors.committee_members(committee))
    governing = (
        selectors.meetings_for_case(case).filter(meeting_date__lte=extension.decided_on).first()
    )
    acting = governing.acting_chair if governing is not None and governing.chair_absent else None
    if acting is None:
        # Şikâyetçi / zarar gören başkan hiçbir durumda basılmaz: panel aynen (son toplantının
        # başkanlık edeni ya da boş hane). Son toplantı da vekâletsizse panel zaten kurulun
        # kendi kaydıdır (aynen döner).
        if services.committee.chair_conflicted(case, committee) or "chair_role" not in panel:
            return panel
        return {"committee": committee, "members": members}
    return {
        "committee": _ActingCommittee(committee, _ActingChair(acting)),
        "members": [m for m in members if m.pk != acting.pk],
        "chair_role": ACTING_CHAIR_ROLE,
        "chair_presiding": ACTING_CHAIR_PRESIDING,
        "chair_office": ACTING_CHAIR_OFFICE,
    }


def _extension_grid(case: DisciplineCase, extension: Any, panel: dict[str, Any]) -> dict[str, Any]:
    """Form-12 imza ızgarası — uzatma GÜNÜNDEKİ toplantıya katılanlar (K4, 15.11.2026).

    Süre uzatma kararının tarihiyle (`decided_on`) AYNI tarihli dosya toplantısı kayıtlıysa
    ızgara o toplantıya KATILAN üyeleri basar (yedek dahil, sonradan kuruldan çıkarılan dahil —
    `services.committee.meeting_attendees`; md. 196/1 "karar bütün üyelerce imzalanır"). Öyle
    bir toplantı kaydı yoksa (ya da kayıt katılımcısızsa) liste aynen kalır: kurulun asıl
    üyeleri. Kural başkan şikâyetçi, izinli ya da olağan olsun geçerlidir; başkan hanesi
    DEĞİŞMEZ (`_extension_panel`). Başkan hanesine yazılan başkanlık eden üye ızgarada ikinci
    kez basılmaz. AYNEN şablon yedekleri (`is_substitute`) gizlediği için katılanlar EK-1'deki
    `_Signer` kalıbıyla sunulur (şablon değişmez). Form-13 üye listesi basmaz — etkilenmez.
    """
    if extension is None:
        return panel
    meeting = selectors.meetings_for_case(case).filter(meeting_date=extension.decided_on).first()
    if meeting is None:
        return panel
    attendees = services.committee.meeting_attendees(meeting)
    if not attendees:
        return panel
    committee = panel.get("committee")
    chair_pk = getattr(getattr(committee, "chair", None), "member_pk", None)
    return {**panel, "members": [_Signer(m) for m in attendees if m.pk != chair_pk]}


def _deadline_extension_context(case: DisciplineCase, extra: dict[str, Any]) -> dict[str, Any]:
    """Süre uzatma (F-12 ara karar / F-13 dilekçe, md. 192/3) — uzatma kaydı + kurul + öğrenci.

    Uzatma dosya başına tektir (alive-unique) → `deadline_extensions.first()` ve dosya
    GENELİDİR (md. 192/3): çok öğrencili dosyada bütün öğrenciler yazılır. `students`
    dosyaya eklenme sırasıyla tam listedir (`case.students` sicil sırasıyla gelir —
    eskiden yalnız sicildeki ilk öğrenci basılıyordu). `student` ilk öğrencinin SAF
    künyesidir (`full_name` yalnız ad — tek öğrencili dosyada şablon çıktısı eskisiyle
    aynıdır); çok öğrencili dosyada şablonlar `students` üzerinden çoğul kalıp basar
    ("… öğrencileri hakkında"). `requested_days_text` gün sayısının yazıyla hâlidir
    (Form-13).
    """
    extension = case.deadline_extensions.first()
    panel = _extension_grid(case, extension, _extension_panel(case, extension))
    students = [
        _student_context(link.student)
        for link in case.case_students.select_related("student").order_by("pk")
    ]
    student: dict[str, Any] | None = students[0] if students else None
    days = extension.requested_days if extension is not None else None
    return {
        **_common_context(case),
        # S7/K3: başkanlık eden üye ızgarada bir kez imzalar — `_committee_with_members_context`.
        **panel,
        "extension": extension,
        "student": student,
        "students": students,
        "requested_days_text": _DAYS_TEXT.get(days, "") if days else "",
        # Form-12 "oy birliği / oy çoğunluğu ile" (md. 191/1; kullanıcı kararı 26.09.2026).
        "vote_majority": extra.get("vote_basis") == CouncilDecisionBasis.MAJORITY,
    }


# Belge türü → katılımcı-özgü bağlam üretici (Tur 106).
_ParticipantContextBuilder = Callable[[DisciplineCase, Any, dict[str, Any]], dict[str, Any]]
_PARTICIPANT_CONTEXT_BUILDERS: dict[str, _ParticipantContextBuilder] = {
    DocumentType.STATEMENT_CALL: _statement_call_context,
    DocumentType.STATEMENT_RECORD: _statement_record_context,
    DocumentType.INFO_GATHERING: _info_gathering_context,
    DocumentType.DEFENSE_CALL: _defense_call_context,
    DocumentType.DEFENSE_RECORD: _defense_record_context,
    DocumentType.NON_COMPLIANCE_RECORD: _non_compliance_context,
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
    DocumentType.RETURN_LETTER: _md197_letter_context,
    DocumentType.DISTRICT_REFERRAL_LETTER: _md197_letter_context,
    DocumentType.APPROVAL_REQUEST_LETTER: _approval_request_context,
    DocumentType.PRECAUTION_MEM_LETTER: _precaution_mem_context,
    DocumentType.GUIDANCE_ASSESSMENT: _guidance_assessment_context,
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
        return _deadline_extension_context(case, extra)
    if document_type == DocumentType.PARENT_MEETING:
        return _parent_meeting_context(case, student, extra)
    if document_type == DocumentType.SEARCH_RECORD:
        return _search_record_context(case, extra)
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
    vote_basis: str = "",
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
    if vote_basis and vote_basis not in CouncilDecisionBasis.values:
        raise ValueError("Geçersiz oylama esası (oy birliği / oy çoğunluğu).")
    # Dal A koruması (Tur 214, F17): yalnız-uyarı dalında (DECIDED kararı var,
    # kurula sevk yok) kurul formları üretilmez — Tur 213 (3c) UI filtresinin
    # sunucu karşılığı. DECIDED öncesi (dal belirsiz) ve Dal B'de tam liste.
    if document_type not in _BRANCH_A_ALLOWED:
        decided = (
            case.events.filter(stage=CaseStage.DECIDED).order_by("-recorded_at", "-id").first()
        )
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
        elif days_decision.penalty_type != PenaltyType.SHORT_TERM_SUSPENSION:
            # Form-16/17 "… gün kısa süreli uzaklaştırma" basar (md. 164/2, 172/1).
            final, reason = False, "ceza günleri tebliği yalnız kısa süreli uzaklaştırmada üretilir"
        else:
            final, reason = selectors.decision_is_final(days_decision)
        if not final:
            raise ValueError(f"Ceza kesinleşmeden ceza günleri tebliği üretilemez: {reason}.")
    _assert_process_letter_ready(case, document_type, student_id, variant)

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
        # Form-12 oylama esası (md. 191/1) — GEÇİCİ: DB'ye yazılmaz, yalnız PDF.
        "vote_basis": vote_basis,
        # K1: çağrı / ifade evrakında işlem tarihi verilmediyse ölçüt üretim tarihidir.
        "generated_on": generated_on,
    }
    context = _build_context(case, document_type, student, participant, extra)
    # NOT: eski DOC_CODES/doc_code altbilgi kodu Talep 1g'de (Tur 181) PDF
    # altbilgisinden kaldırılmıştı; ölü bağlam enjeksiyonu Tur 217'de temizlendi.
    # Form ↔ madde eşlemesi artık yalnız şablon alt başlıklarında yaşar.
    context["recipient"] = recipient
    # Belge tarihi = seçilen üretim tarihi (kütük ve dizi pusulasıyla aynı gün).
    context["generated_at"] = _document_datetime(generated_on)
    if document_type in (DocumentType.RETURN_LETTER, DocumentType.DISTRICT_REFERRAL_LETTER):
        _apply_md197_dates(context, document_type)
    # NOT: Form-14/15'te hesaplanan itiraz son günü BASILMAZ (Tur 181, Talep 1d —
    # tebligat günü belirsiz, PTT olabilir); şablonda yalnız "5 iş günü" hakkı yazılıdır.
    # Karar snapshot'ı (decision.appeal_deadline) tebliğ kaydında tutulur
    # (services.notify_decision); PDF bağlamına ayrıca işlenmez.
    if document_type == DocumentType.COMMITTEE_DECISION:
        pdf_bytes, page_count = render_ek1_paged(template, context)
    else:
        pdf_bytes, page_count = render_pdf_paged(template, context)

    # Kütükte öğrenci bağı: öğrenci-özgü belgede student_id; katılımcı belgesinde
    # katılımcı bir öğrenciyse onun id'si (zaman çizelgesinde öğrenciyle ilişkilensin).
    # Kütük bağı yalnız DOSYANIN öğrencisi (hakkında işlem yapılan) içindir: mağdur /
    # tanık öğrenci dosyaya "dahil" değildir (DisciplineCaseStudent yok) → bağ kurulmaz,
    # "kimden" bilgisi source_label/source_name ile taşınır. Aksi hâlde kütük servisi
    # belgeyi reddediyordu ve md. 193/1 tanık ifadesi evrakı üretilemiyordu.
    log_student_id: int | None = None
    if document_type in STUDENT_REQUIRED:
        log_student_id = student_id
    elif (
        participant is not None
        and participant.student_id is not None
        and case.case_students.filter(student_id=participant.student_id).exists()
    ):
        log_student_id = participant.student_id

    # "Kimden" snapshot (Tur 140): katılımcı belgelerinde rol/kaynak + ad → dizi pusulası.
    src_label, src_name = participant_source(document_type, participant, source_label)

    record: GeneratedDocument | None = None
    if log:
        record = services.log_generated_document(
            case,
            document_type=document_type,
            title=title or default_title(document_type, recipient, variant),
            generated_on=generated_on,
            document_no=document_no,
            student_id=log_student_id,
            source_label=src_label,
            source_name=src_name,
            page_count=page_count,  # WeasyPrint'ten otomatik
            pdf_content=pdf_bytes,
            stored_filename=_stored_filename(case.case_no, document_type, recipient, variant),
        )
    return pdf_bytes, record


def _assert_process_letter_ready(
    case: DisciplineCase, document_type: str, student_id: int | None, variant: str
) -> None:
    """Belgenin DAYANAK KAYDI ön koşulları — gerçekleşmemiş işlem "yapıldı" diye basılmaz.

    M2 Grup 1 yazıları (md. 197 / 169/1 / 175 MEM) baştan beri kayıt arar. Saha denetimi
    (14.11.2026) aynı kuralı kardeş belgelere yaydı: karar yokken Form-14/15 (ceza adı
    boş tırnakla basılıyordu), tedbir kaydı olmayan öğrenciye tedbir bildirimi (çok
    öğrencili dosyada yanlış öğrenci seçimi fark edilmiyordu), uzatma kaydı yokken
    Form-12/13 ve itiraz kaydı yokken Form-18. Önce kayıt girilir, sonra belge üretilir.
    """
    from apps.disiplin.models import DisciplinePrecaution

    # BİLİNÇLİ SAPMA (kullanıcı kararı, 14.11.2026 — S12; OYS'de bu denetim yoktur):
    # kurula sevk edilmiş (Dal B) dosyada öğrencinin O DOSYADA müdür uyarısı kaydı yoksa
    # müdür yazılı uyarısı (Form-02, öğrenci ve veli sürümü — md. 157/7-a) ve "yazılı
    # uyarıya rağmen…" diyen veli görüşme tutanağı (md. 157/7-b) üretilmez: yapılmamış
    # uyarı "yapıldı" diye belgelenmez. Kayıt varsa (uyarıdan sonra aşama geri alınıp
    # kurula sevk edilen dosya) üretilir. Veli davet yazısı ve "veli gelmedi" tutanağı
    # kararın kapsamında değildir. Dal A (yazılı uyarıyla kapanan) ve müdür kararı henüz
    # verilmemiş dosyada davranış DEĞİŞMEZ.
    warning_document = ""
    if document_type == DocumentType.WARNING_LETTER:
        warning_document = "müdür yazılı uyarısı (Form-02)"
    elif (
        document_type == DocumentType.PARENT_MEETING
        and _effective_variant(document_type, variant) == VARIANT_PARENT_MEETING
    ):
        warning_document = "veli görüşme tutanağı"
    if (
        warning_document
        and _case_referred_to_committee(case)
        and not case.warnings.filter(student_id=student_id).exists()
    ):
        raise ValueError(
            f"Dosya kurula sevk edilmiş ve bu öğrenci için dosyada müdür uyarısı kaydı yok; "
            f"{warning_document} üretilemez (md. 157/7). Kurula sevkli dosyada bu belge yalnız "
            "öğrencinin bu dosyada kayıtlı bir müdür uyarısı varsa üretilir; uyarı başka bir "
            "dosyada yapıldıysa belgeyi o dosyadan üretin."
        )

    if (
        document_type == DocumentType.PENALTY_NOTICE
        and not case.decisions.filter(student_id=student_id).exists()
    ):
        raise ValueError(
            "Dosyada bu öğrenci için kurul kararı yok; ceza tebliği (Form-14/15) "
            "üretilemez. Önce kurul kararını kaydedin."
        )
    if (
        document_type == DocumentType.PRECAUTION_NOTICE
        and not DisciplinePrecaution.objects.filter(case=case, student_id=student_id).exists()
    ):
        raise ValueError(
            "Bu öğrenci için dosyada tedbir (md. 175) kaydı yok; önce tedbir kaydını girin."
        )
    if document_type == DocumentType.DEADLINE_EXTENSION and not case.deadline_extensions.exists():
        raise ValueError(
            "Dosyada süre uzatma kaydı yok; önce kurulun süre uzatma ara kararını "
            "(md. 192/3) kaydedin, sonra Form-12/13'ü üretin."
        )
    if document_type == DocumentType.APPEAL_LETTER:
        # Form-18 itirazı üst kurula sevk eder: "karar … onaylanmıştır", "… tarihinde
        # tebliğ edilmiştir", "… itiraz etmiştir" cümleleri kayıttan basılır (md. 169/3).
        appeal_decision = case.decisions.filter(student_id=student_id).first()
        if appeal_decision is None:
            raise ValueError("Dosyada bu öğrenci için kurul kararı yok; itiraz yazısı üretilemez.")
        if not appeal_decision.appeals.exists():
            raise ValueError(
                "Bu karar için itiraz kaydı yok; itiraz yazısı (Form-18) itiraz dilekçesi "
                "kaydedildikten sonra üretilir (md. 169/3)."
            )
        if appeal_decision.notified_at is None:
            raise ValueError(
                "Karar onaylanıp tebliğ edilmeden itiraz yazısı (Form-18) üretilemez "
                "(md. 163/2, 169/3)."
            )

    if document_type in {
        DocumentType.RETURN_LETTER,
        DocumentType.DISTRICT_REFERRAL_LETTER,
        DocumentType.APPROVAL_REQUEST_LETTER,
    }:
        decision = case.decisions.filter(student_id=student_id).first()
        if decision is None:
            raise ValueError("Dosyada bu öğrenci için kurul kararı yok.")
        if document_type == DocumentType.RETURN_LETTER and decision.returned_at is None:
            raise ValueError("Karar kurula iade edilmemiş (md. 197); önce iadeyi kaydedin.")
        if (
            document_type == DocumentType.DISTRICT_REFERRAL_LETTER
            and not decision.referred_to_district
        ):
            raise ValueError(
                "Karar ilçe kuruluna gönderilmemiş (md. 197); önce ilçeye sevki kaydedin."
            )
        if document_type == DocumentType.APPROVAL_REQUEST_LETTER and (
            decision.referred_to_district
            or decision.approval_authority
            not in {ApprovalAuthority.DISTRICT_BOARD, ApprovalAuthority.PROVINCIAL_BOARD}
        ):
            raise ValueError(
                "Onaya sevk yazısı yalnız ilçe/il kurulu onayına bağlı cezada (okul "
                "değiştirme, örgün eğitim dışına çıkarma — md. 169/1-2) üretilir."
            )
    if document_type == DocumentType.PRECAUTION_MEM_LETTER:
        qs = DisciplinePrecaution.objects.filter(case=case, student_id=student_id)
        if not qs.exists():
            raise ValueError("Bu öğrenci için dosyada tedbir (md. 175) kaydı yok.")
        if variant == VARIANT_MEM_EXTENSION and all(p.extension_count >= 2 for p in qs):
            raise ValueError("Tedbir zaten iki kez uzatıldı; üçüncü uzatma yok (md. 175/2).")


def _apply_md197_dates(context: dict[str, Any], document_type: str) -> None:
    """md. 197 yazılarında İADE tarihi: bilinmiyorsa UYDURULMAZ (yalnız bağlam).

    `record_principal_review` REFER'de `returned_at`'i SEVK tarihiyle günceller (ilçe
    yazısının tarihi odur). İADE tarihi `decision.first_returned_at`'te saklanır
    (kullanıcı kararı 14.11.2026 — S11b) ve doluysa O basılır:
    - iade yazısı: şablon `decision.returned_at` okuduğundan vekil (`_DecisionView`)
      `returned_at` yerine iade tarihini verir — kayıt değişmez, şablona dokunulmaz;
    - ilçeye gönderme yazısı İlgi (b): `return_letter_date` = iade tarihi.
    Alan BOŞSA (S11 göçünden önce sevk edilmiş karar) tarih UYDURULMAZ: evrak
    kütüğündeki iade yazısının ÜRETİM tarihi güvenilir bir kaynak değildir (yazı sonradan,
    başka bir tarih seçilerek ya da hiç üretilmeden iade kaydedilmiş olabilir). O durumda
    sevkten sonra iade yazısı `return_date_unknown` ile noktalı basılır (vekilde
    `returned_at` None — sevk tarihi iade tarihi diye basılmaz), İlgi (b) noktalı kalır.
    Sevk edilmemiş eski kararda iade tarihi `decision.returned_at`'tir.
    """
    context["return_letter_date"] = None
    context["return_date_unknown"] = False
    decision = context.get("decision")
    if decision is None:
        return
    first_returned_at = getattr(decision, "first_returned_at", None)
    if document_type == DocumentType.DISTRICT_REFERRAL_LETTER:
        context["return_letter_date"] = first_returned_at
    elif first_returned_at is not None:
        context["decision"] = _DecisionView(decision, returned_at=first_returned_at)
    elif decision.referred_to_district:
        context["decision"] = _DecisionView(decision, returned_at=None)
        context["return_date_unknown"] = True
    # K10 (kullanıcı kararı, 15.11.2026): kurula iade yazısı kurulun İLK kararına ilişkindir.
    # Karar iadeden sonra başka toplantıya taşındıysa (ikinci görüşme) `decision_date` yeni
    # tarihtir; yazı `first_decision_date`'i basar (yalnız bağlam — şablon ve kayıt değişmez).
    # İlçeye gönderme yazısı ve öteki belgeler yürürlükteki karar tarihini kullanır.
    if document_type != DocumentType.RETURN_LETTER:
        return
    first_decision_date = getattr(decision, "first_decision_date", None)
    if first_decision_date is not None:
        context["decision"] = _DecisionView(context["decision"], decision_date=first_decision_date)
    # Kullanıcı kararı 16.11.2026: ikinci görüşmede sayı / ceza da değişebilir; iade yazısı
    # kurulun İLK kararının sayısını, cezasını ve maddesini basar (yalnız bağlam). İz
    # `first_penalty_type` doluysa vardır; boşsa (taşınmadı / 0019 öncesi taşındı)
    # yürürlükteki kayıt basılır — ilk sayı / ceza UYDURULMAZ.
    first_penalty_type = getattr(decision, "first_penalty_type", "")
    if first_penalty_type:
        view = _DecisionView(
            context["decision"],
            decision_no=decision.first_decision_no,
            penalty_type=first_penalty_type,
            suspension_days=decision.first_suspension_days,
            statute_ref=decision.first_statute_ref,
        )
        context["decision"] = view
        context["statute_label"] = statute_label(view)


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


def _decision_no_sort_key(decision_no: str) -> tuple[int, list[tuple[int, int, str]]]:
    """Karar numarası için DOĞAL sıralama anahtarı (kullanıcı kararı, 14.11.2026 — S1).

    Rakam öbekleri sayı olarak karşılaştırılır: "2026-2027/0002" < "2026-2027/0010" <
    "2026-2027/0100" (düz metin sıralaması elle girilmiş "9" ile "10"u ters dizer).
    Numarasız (boş) karar SONA düşer; eşit anahtarlarda `sorted` kararlıdır (model sırası).
    """
    text = (decision_no or "").strip()
    if not text:
        return (1, [])
    parts: list[tuple[int, int, str]] = [
        (0, int(part), "") if part.isdigit() else (1, 0, part)
        for part in re.split(r"(\d+)", text)
        if part
    ]
    return (0, parts)


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
    acting_note = ""
    if (
        chair is not None
        and meeting.council_type == "DISCIPLINE"
        and getattr(meeting, "chair_absent", False)
    ):
        # VEKÂLET KAYDI (kullanıcı kararı, 14.11.2026 — S7): başkan katılmadı; katılmayan
        # başkan zaten katılımcı değildir (basılmaz). Başkan işaretli satır kurula başkanlık
        # eden öğretmen üyedir — görevi md. 188 ifadesiyle basılır (katılanlar tablosu + imza
        # ızgarası); kayıt DEĞİŞMEZ. K1: `acting_chair` şablondaki sabit "(Başkan)" işaretini
        # kapatır, `chair_absence_note` tabloya tek cümle ekler. Vekâletsiz toplantıda bu
        # anahtarlar bağlamda YOKTUR ve liste aynen kalır.
        acting_note = _chair_absence_note(meeting, chair)
        chair = _ActingChairAttendee(chair)
        voting = [chair if a.is_chair else a for a in voting]
    dissenters = [a for a in attendees if (a.dissent_note or "").strip()]
    case = meeting.discipline_case if meeting.minutes_type == "CASE_REVIEW" else None
    case_decisions: list[dict[str, Any]] = []
    if case is not None:
        # BİLİNÇLİ SAPMA (kullanıcı kararı, 14.11.2026 — S1; CLAUDE.md §1/3): OYS kararları
        # model sırasıyla (yeniden eskiye — karar numarasına TERS) ve cezayı yalnız tür
        # etiketiyle basıyordu. Karar defterinde (md. 196/1) kararlar KARAR NUMARASI
        # sırasıyla dizilir ve uzaklaştırmada kaç gün verildiği de yazılır (md. 164/2:
        # 1-5 gün) — "… — 3 gün". Dosya görüşmesi olmayan tutanak etkilenmez.
        decisions = sorted(
            selectors.decisions_for_case(case).select_related("student"),
            key=lambda d: _decision_no_sort_key(d.decision_no),
        )
        for decision in decisions:
            student = decision.student
            # Karar defteri okul kurulunun kararını kaydeder (md. 196/1): ceza sonradan üst
            # kurulca değiştirildiyse basılan ceza (ve gün sayısı) kurulun VERDİĞİ cezadır.
            shown = _board_decision_context(decision)
            case_decisions.append(
                {
                    "full_name": student.full_name or "",
                    "class_label": student.class_label,
                    "student_number": student.student_number or "",
                    "penalty_display": shown["board_penalty_display"],
                    "penalty_detail": decision.penalty_detail,
                    "decision_no": decision.decision_no,
                    "decision_date": decision.decision_date,
                    "statute_label": shown["statute_label"],
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
        "signer_rows": _signer_rows(chair, voting),
        "invitees": invitees,
        "dissenters": dissenters,
        "case": case,
        "case_decisions": case_decisions,
        "agenda_items": _council_agenda_rows(meeting),
    }
    if acting_note:
        context["acting_chair"] = True
        context["chair_absence_note"] = acting_note
    return context


def _chair_absence_note(meeting: Any, acting: Any) -> str:
    """Karar defterine düşülen vekâlet cümlesi (md. 188) — K1, kullanıcı kararı 14.11.2026.

    K5 (kullanıcı kararı, 15.11.2026): katılmayan başkanın adı vekâlet KAYDEDİLİRKEN kayda
    yazılır (`absent_chair_name`) ve cümle ONU basar — başkan sonradan değişse de tutanak
    aynı kalır. Alan boşsa (K5 öncesi kayıt) eski davranış: ad kurulun BUGÜNKÜ başkanından
    okunur (o kayıtlarda başkan değişikliğinin geçmişi yoktur — bilinen sınır); bugünkü başkan,
    o toplantıda kurula başkanlık eden kişinin kendisiyse (sonradan başkan yapılmış öğretmen
    üye) ad yazılmaz: cümle kendisiyle çelişmesin.
    """
    from apps.disiplin.services.council import _name_key, meeting_committee

    committee = meeting_committee(meeting)
    chair_name = ""
    recorded = str(getattr(meeting, "absent_chair_name", "") or "").strip()
    if recorded:
        chair_name = f" {recorded}"
    elif committee is not None:
        same_person = (
            acting.member_user_id == committee.chair_id
            if acting.member_user_id is not None
            else _name_key(acting.person_name) == _name_key(committee.chair.full_name)
        )
        if not same_person:
            chair_name = f" {committee.chair.full_name}"
    return (
        f"Kurul başkanı{chair_name} toplantıya katılmamış; kurula öğretmen üye "
        f"{acting.person_name} başkanlık etmiştir (md. 188)."
    )


class _ActingChairAttendee:
    """Karar defterinde kurula başkanlık eden öğretmen üyeyi md. 188 unvanıyla sunan vekil.

    Yalnız `title` farklıdır: öteki belgelerle AYNI ifade (`ACTING_CHAIR_ROLE`); diğer
    alanlar katılımcı kaydına devredilir.
    """

    def __init__(self, attendee: Any) -> None:
        self._attendee = attendee
        self.title = ACTING_CHAIR_ROLE

    def __getattr__(self, name: str) -> Any:
        return getattr(self._attendee, name)


# Karar defteri imza ızgarasında satır başına hane. 5: ÖDK ve Onur Kurulu (başkan + 4
# üye) tek satırda kalır — az imzacılı çıktı eski tek satırlı ızgarayla aynıdır.
_SIGNERS_PER_ROW = 5


def _signer_rows(chair: Any, voting: list[Any]) -> list[list[Any]]:
    """İmza ızgarası satırları: başkan + oy hakkı olan diğer üyeler, 5'erli.

    Tek satırlı ızgara kalabalık Onur Genel Kurulunda (md. 178: her şubeden bir öğrenci)
    sayfa dışına taşıyordu (saha denetimi 14.11.2026). Birden çok satır varsa son satır
    `None` ile tamamlanır ki haneler aynı genişlikte kalsın.
    """
    signers = ([chair] if chair is not None else []) + [a for a in voting if not a.is_chair]
    rows: list[list[Any]] = [
        signers[i : i + _SIGNERS_PER_ROW] for i in range(0, len(signers), _SIGNERS_PER_ROW)
    ]
    if len(rows) > 1:
        rows[-1] += [None] * (_SIGNERS_PER_ROW - len(rows[-1]))
    return rows or [[]]


def _council_agenda_rows(meeting: Any) -> list[dict[str, Any]]:
    """Karar defterine basılacak gündem maddeleri (04.10.2026 — yalnız ekleme).

    Konu teklifin öğrencisinden ve kriter maddelerinden derlenir; karar adı kurula
    göre (uygun görüldü / kabul edildi …). Karar esası yalnız karara bağlanmış maddede.
    """
    from apps.disiplin.honor_documents import _regulation_articles
    from apps.disiplin.models import AGENDA_OUTCOME_LABELS, AgendaItemOutcome

    labels = AGENDA_OUTCOME_LABELS.get(meeting.council_type, {})
    rows: list[dict[str, Any]] = []
    for item in meeting.agenda_items.all():
        certificate = item.honor_certificate
        subject = ""
        if certificate is not None:
            student = certificate.student
            subject = (
                f"{student.full_name} ({student.class_label}) — onur belgesi teklifi "
                f"({_regulation_articles(certificate)})"
            )
        decided = item.outcome != AgendaItemOutcome.PENDING
        rows.append(
            {
                "subject": subject,
                "outcome_display": labels.get(item.outcome, item.get_outcome_display()),
                "decision_text": item.decision_text,
                "basis_display": item.get_decision_basis_display() if decided else "",
                "dissent_note": item.dissent_note,
            }
        )
    return rows


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
