"""Ödül / Onur evrak üretimi (Tur 115, ADR-0011) — md. 159-184.

Onur belgesi süreci için iki resmî PDF; disiplin `documents.py` motorunu (render_pdf +
`documents/base.html` + `shared.letterhead`) **case'e bağlı olmadan** yeniden kullanır:

- **Onur Belgesi Teklif Formu** (md. 161): öğretmenin çok-öğrencili teklifi. Boş yazdırılabilir
  şablon VEYA dijital tekliften (HonorCertificate satırları) doldurulmuş.
- **Onur Kurulu Teklif Tutanağı** (md. 161 + 183/b): uygun görülen öğrencileri gerekçeleriyle
  listeleyen, Okul Öğrenci Ödül ve Disiplin Kurulu'na sunulan tutanak.

İçerik DB'de saklanmaz (disiplin evrak felsefesi; kütük tutulmaz). Modül sınırı (ADR-0002):
`core.services` + `shared.letterhead` açık arayüzleri kullanılır.
"""

from __future__ import annotations

from typing import Any

from django.utils import timezone

from apps.disiplin.documents import render_pdf
from apps.disiplin.models import HonorCertificate, HonorCriterion, HonorProposerRole
from shared.letterhead import letterhead_context

_UNIT = "Onur Kurulu"

PROPOSAL_FORM_TEMPLATE = "disiplin/documents/honor_proposal_form.html"
RECOMMENDATION_RECORD_TEMPLATE = "disiplin/documents/honor_recommendation_record.html"
AWARD_DECISION_RECORD_TEMPLATE = "disiplin/documents/honor_award_decision_record.html"

_AWARD_UNIT = "Okul Öğrenci Ödül ve Disiplin Kurulu"

# md. 161 kriter kodu → "İstek Nedeni (1-a gibi)" sütununda kullanılan harf (md. 161/1 a-ğ,
# md. 161/2 = "1/2"). Resmî teklif formundaki gösterimi izler.
CRITERION_LETTER: dict[str, str] = {
    HonorCriterion.LANGUAGE: "1-a",
    HonorCriterion.ACHIEVEMENT: "1-b",
    HonorCriterion.RESOURCES: "1-c",
    HonorCriterion.MANNERS: "1-ç",
    HonorCriterion.TRAFFIC: "1-d",
    HonorCriterion.IT: "1-e",
    HonorCriterion.ATTENDANCE: "1-f",
    HonorCriterion.SOCIAL_RESPONSIBILITY: "1-g",
    HonorCriterion.SAFETY: "1-ğ",
    HonorCriterion.OTHER: "1/2",
}

# md. 161 a-ğ referans metni (teklif formu altına basılır; etiketler "(a) …" ile başlar).
CRITERIA_REFERENCE: list[str] = [HonorCriterion(c).label for c in HonorCriterion.values]

# Boş formdaki yazılabilir satır sayısı (md. 161 resmî örneğe göre 5 öğrenci).
_BLANK_ROW_COUNT = 5


def _base_context(*, unit: str = _UNIT) -> dict[str, Any]:
    """Antet (T.C. + kaymakamlık + okul + birim) + müdür adı + üretim zamanı (case'siz)."""
    from apps.okul.services import setup as okul_setup

    # Antet kimliği: kurulum sihirbazında girilen okul/ilçe/müdür (SchoolConfig).
    identity = okul_setup.get_letterhead_identity()
    ctx: dict[str, Any] = {
        **letterhead_context(
            school_name=identity["school_name"],
            unit=unit,
            district=identity["district"],
            principal_name=identity["principal_name"],
        ),
        "generated_at": timezone.now(),
        "criteria_reference": CRITERIA_REFERENCE,
    }
    return ctx


def _regulation_articles(certificate: HonorCertificate) -> str:
    """Belgenin kriterlerini yönetmelik madde referansına çevirir: 'md. 161/1-a, md. 161/2'."""
    seen: list[str] = []
    for c in certificate.criteria or []:
        code = CRITERION_LETTER.get(c, "")
        if code == "1/2":
            article = "md. 161/2"
        elif code:
            article = f"md. 161/{code}"
        else:
            article = "md. 161"
        if article not in seen:
            seen.append(article)
    return ", ".join(seen)


def _proposer_display(certificate: HonorCertificate) -> str:
    """Teklif edeni 'Ad Soyad – Rol' biçiminde döndürür (proposer_name snapshot'ı).

    OYS'deki created_by fallback'i yok (kullanıcı kavramı kalktı) — ad,
    teklif kaydında tutulan snapshot'tan gelir.
    """
    name = (certificate.proposer_name or "").strip()
    role = ""
    if certificate.proposer_role:
        try:
            role = HonorProposerRole(certificate.proposer_role).label
        except ValueError:
            role = certificate.proposer_role
    if name and role:
        return f"{name} – {role}"
    return name or role


def _proposal_rows(certificates: list[HonorCertificate]) -> list[dict[str, Any]]:
    """Tablo satırları: sınıf + no + ad + teklif eden (ad-rol) + gerekçe (+ yönetmelik maddesi)."""
    rows: list[dict[str, Any]] = []
    for c in certificates:
        student = c.student
        rows.append(
            {
                "class_label": student.class_label,
                "student_number": student.student_number or "",
                "full_name": student.full_name or f"#{c.student_id}",
                "proposer": _proposer_display(c),
                "justification": c.justification,
                "regulation": _regulation_articles(c),
            }
        )
    return rows


def _proposer_name(certificates: list[HonorCertificate], explicit: str = "") -> str:
    """Dolu form imza adı: açıkça verilen ad; yoksa ilk teklifin proposer_name'i."""
    if explicit.strip():
        return explicit.strip()
    if not certificates:
        return ""
    return certificates[0].proposer_name or ""


def render_proposal_form_blank() -> bytes:
    """Boş Onur Belgesi Teklif Formu (öğretmen elle doldurur) — md. 161."""
    ctx = _base_context()
    empty = {
        "class_label": "",
        "student_number": "",
        "full_name": "",
        "justification": "",
        "regulation": "",
    }
    ctx.update(
        {
            "rows": [dict(empty) for _ in range(_BLANK_ROW_COUNT)],
            "proposer_name": "",
            "show_proposer": False,
        }
    )
    return render_pdf(PROPOSAL_FORM_TEMPLATE, ctx)


def render_proposal_form(certificates: list[HonorCertificate], *, proposer_name: str = "") -> bytes:
    """Dolu Onur Belgesi Teklif Formu (dijital tekliften) — md. 161."""
    ctx = _base_context()
    ctx.update(
        {
            "rows": _proposal_rows(certificates),
            "proposer_name": _proposer_name(certificates, proposer_name),
            "show_proposer": True,
        }
    )
    return render_pdf(PROPOSAL_FORM_TEMPLATE, ctx)


def render_recommendation_record(
    certificates: list[HonorCertificate], *, board: Any = None, committee: Any = None
) -> bytes:
    """Onur Kurulu Teklif Tutanağı — uygun görülenleri gerekçeleriyle listeler (md. 161 + 183/b).

    `board` verilirse imza ızgarasında onur kurulu başkanı + asıl üyeler yer alır.
    `committee` (ödül-disiplin kurulu) verilirse tutanağın altına teslim-tesellüm bölümü
    eklenir (talep i): Onur Kurulu Başkanı teslim eder → Ödül-Disiplin Kurulu Başkanı tesellüm
    eder. Teslim tarihi PDF'te boş bırakılır (elle yazılır; teslim günü değişebilir).
    """
    ctx = _base_context()
    members = [m for m in board.members.all() if not m.is_substitute] if board is not None else []
    chair_name = ""
    if board is not None and board.chair_id:
        chair_name = board.chair.full_name
    committee_chair_name = ""
    if committee is not None and committee.chair_id:
        committee_chair_name = committee.chair.full_name
    ctx.update(
        {
            "rows": _proposal_rows(certificates),
            "term_name": (
                certificates[0].school_term.name
                if certificates and certificates[0].school_term is not None
                else ""
            ),
            "members": members,
            "chair_name": chair_name,
            "committee_chair_name": committee_chair_name,
        }
    )
    return render_pdf(RECOMMENDATION_RECORD_TEMPLATE, ctx)


def _award_rows(certificates: list[HonorCertificate]) -> list[dict[str, Any]]:
    """Nihai tutanak satırları: sınıf + no + ad + yönetmelik maddesi + belge tarihi."""
    rows: list[dict[str, Any]] = []
    for c in certificates:
        student = c.student
        rows.append(
            {
                "class_label": student.class_label,
                "student_number": student.student_number or "",
                "full_name": student.full_name or f"#{c.student_id}",
                "regulation": _regulation_articles(c),
                "awarded_at": c.awarded_at,
            }
        )
    return rows


def render_award_decision_record(
    certificates: list[HonorCertificate], *, committee: Any = None
) -> bytes:
    """Ödül-Disiplin Kurulu Kararı — Onur Belgesi verilen öğrencileri listeler (talep 3).

    Onur kurulunca uygun görülüp ödül-disiplin kuruluna sevk edilen ve kurulca belge
    verilmesine karar verilen (AWARDED) öğrencilerin nihai listesi; Okul Müdürlüğüne
    sunulur (md. 161, md. 183/b). İmza ızgarasında ödül-disiplin kurulu başkanı + asıl
    üyeler yer alır (`committee` verilirse). İçerik DB'de saklanmaz.
    """
    ctx = _base_context(unit=_AWARD_UNIT)
    members = (
        [m for m in committee.members.all() if not m.is_substitute] if committee is not None else []
    )
    committee_chair_name = ""
    if committee is not None and committee.chair_id:
        committee_chair_name = committee.chair.full_name
    ctx.update(
        {
            "rows": _award_rows(certificates),
            "term_name": (
                certificates[0].school_term.name
                if certificates and certificates[0].school_term is not None
                else ""
            ),
            "decision_date": certificates[0].awarded_at if certificates else None,
            "members": members,
            "committee_chair_name": committee_chair_name,
        }
    )
    return render_pdf(AWARD_DECISION_RECORD_TEMPLATE, ctx)
