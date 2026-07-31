"""'Yaklaşan Süreler' paneli — Celery ikamesi (tasarım §4.5).

OYS'de günlük Celery görevi (`daily_discipline_deadline_check`) bildirim
yayınlıyordu; standalone'da panel açılışta + periyodik senkron çağrılan tek
fonksiyondan beslenir: `collect_deadline_items(today)`.

Beş bölüm (tasarım §4.5):
1. İtiraz sevk süreleri (md. 169/3 — başvuru + 5 iş günü)
2. Kurul karar süreleri (md. 192/3 — kurula geliş + 10 iş günü, uzatma dahil)
3. Tedbir süreleri (md. 175 — bitiş / işleme başlama)
4. Tebliğ bekleyen kararlar (tarihsiz — BİLGİ)
5. e-Okul'a işlenmesi beklenen kesinleşmiş cezalar (BİLGİ)
6. Kapanışa hazır dosyalar (`close_eligible` — BİLGİ)

Öğe biçimi: {severity, case_no, title, due_date, statute_ref, link}.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from typing import Any

from apps.disiplin import selectors
from apps.okul.services.calendar import is_working_day
from shared.working_days import add_working_days


class Severity:
    """Panel önem düzeyleri (Türkçe görüntü değerleri — FE rozetleri bunları basar)."""

    OVERDUE = "GEÇTİ"
    UPCOMING = "YAKLAŞIYOR"
    INFO = "BİLGİ"


#: "Yaklaşıyor" penceresi: bugünden itibaren bu kadar İŞ GÜNÜ içinde dolan süreler.
UPCOMING_WORKING_DAYS = 5


@dataclass
class DeadlineItem:
    """Paneldeki tek satır."""

    severity: str
    case_no: str
    title: str
    due_date: date | None
    statute_ref: str
    link: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["due_date"] = self.due_date.isoformat() if self.due_date else None
        return data


def _severity_for(due: date, today: date) -> str:
    return Severity.OVERDUE if due < today else Severity.UPCOMING


def collect_deadline_items(today: date) -> list[DeadlineItem]:
    """Panelin tüm bölümlerini tek listede toplar (GEÇTİ → YAKLAŞIYOR → BİLGİ sıralı).

    Tarama ufku: bugün + UPCOMING_WORKING_DAYS iş günü (yerel tatil takvimi
    dahil). Geçmiş süreler her zaman listelenir (GEÇTİ).
    """
    horizon = add_working_days(today, UPCOMING_WORKING_DAYS, is_working_day=is_working_day)
    items: list[DeadlineItem] = []

    # 1) İtiraz sevk süreleri (md. 169/3).
    for appeal in selectors.appeals_awaiting_forward(horizon):
        case = appeal.decision.case
        due = appeal.forward_deadline
        assert due is not None  # selector forward_deadline__isnull=False süzer
        items.append(
            DeadlineItem(
                severity=_severity_for(due, today),
                case_no=case.case_no,
                title="İtiraz üst kurula sevk edilmeli (başvuru + 5 iş günü)",
                due_date=due,
                statute_ref="md. 169/3",
                link=f"/disiplin/{case.pk}",
            )
        )

    # 2) Kurul karar süreleri (md. 192/3; onaylı uzatma dahil).
    for case, deadline in selectors.cases_awaiting_committee_decision(horizon):
        items.append(
            DeadlineItem(
                severity=_severity_for(deadline, today),
                case_no=case.case_no,
                title="Kurul karar süresi doluyor (kurula geliş + 10 iş günü)",
                due_date=deadline,
                statute_ref="md. 192/3",
                link=f"/disiplin/{case.pk}",
            )
        )

    # 3) Tedbir süreleri (md. 175) — İKİ eşik ayrı satır: işleme-başlama (175/2)
    #    ve bitiş (175/1). min() tekleştirmesi uzun tedbirlerde bitişi gizliyordu.
    for precaution in selectors.precautions_awaiting_deadline(horizon):
        thresholds = (
            (
                precaution.process_start_deadline,
                "Tedbir sonrası disiplin işlemine başlanmalı (tedbir + 3 iş günü)",
            ),
            (precaution.end_date, "Tedbir süresi doluyor (en fazla 10 iş günü)"),
        )
        for due, title in thresholds:
            if due > horizon:
                continue
            items.append(
                DeadlineItem(
                    severity=_severity_for(due, today),
                    case_no=precaution.case.case_no,
                    title=title,
                    due_date=due,
                    statute_ref="md. 175",
                    link=f"/disiplin/{precaution.case_id}",
                )
            )

    # 4) Tebliğ bekleyen kararlar (tarihsiz — BİLGİ). NOT: öğrenci adı tek
    #    kullanıcılı cihazın panelinde görünür — KVKK açısından kabul (inceleme #19).
    for decision in selectors.decisions_awaiting_notification():
        items.append(
            DeadlineItem(
                severity=Severity.INFO,
                case_no=decision.case.case_no,
                title=f"Karar tebliğ bekliyor ({decision.student.full_name})",
                due_date=None,
                statute_ref="md. 169/5",
                link=f"/disiplin/{decision.case_id}",
            )
        )

    # 5) Kesinleşmiş, ancak e-Okul'a işlendi onayı bekleyen cezalar.
    for case in selectors.open_cases_for_close_scan():
        for decision in selectors.decisions_for_case(case):
            final, _reason = selectors.decision_is_final(decision, today=today)
            if (
                final
                and decision.penalty_type != "NO_PENALTY"
                and decision.e_school_processed_on is None
            ):
                items.append(
                    DeadlineItem(
                        severity=Severity.INFO,
                        case_no=case.case_no,
                        title=f"Kesinleşen ceza e-Okul'a işlenmeli ({decision.student.full_name})",
                        due_date=None,
                        statute_ref="md. 171",
                        link=f"/disiplin/{case.pk}",
                    )
                )

    # 6) Kapanışa hazır dosyalar (BİLGİ) — açık ve karar/sevk aşamasını geçmiş.
    #    Disiplin kuruluna sevkli ama HENÜZ KARARSIZ dosya atlanır: kurul kararı
    #    bekleniyor (2. bölüm izliyor); "kapatılabilir" önerisi yanıltıcı olur.
    for case in selectors.open_cases_for_close_scan():
        if not case.decisions.exists() and selectors.committee_referred_on(case) is not None:
            continue
        eligible, _eligible_on = selectors.close_eligible(case, today=today)
        if eligible:
            items.append(
                DeadlineItem(
                    severity=Severity.INFO,
                    case_no=case.case_no,
                    title="Dosya kapatılabilir (itiraz süresi + tampon doldu)",
                    due_date=None,
                    statute_ref="md. 169",
                    link=f"/disiplin/{case.pk}",
                )
            )

    order = {Severity.OVERDUE: 0, Severity.UPCOMING: 1, Severity.INFO: 2}
    items.sort(key=lambda i: (order[i.severity], i.due_date or date.max, i.case_no))
    return items
