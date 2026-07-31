"""Disiplin kararı + itiraz salt-okunur sorguları (md. 163-171) — davranış puanı dahil.

OYS `selectors/discipline_decisions.py`'den uyarlama: `decisions_for_student`
görünürlük filtresiz (tek kullanıcı); iş günü yüklemi yerel takvimden; ders yılı
`okul.selectors`'tan çözülür. Kesinleşme/kapanış kuralları AYNEN.
"""

from __future__ import annotations

from datetime import date

from django.db.models import QuerySet, Sum
from django.utils import timezone

from apps.disiplin import discipline_periods
from apps.disiplin.discipline_periods import BEHAVIOR_POINT_START
from apps.disiplin.models import (
    AppealResult,
    DecisionApprovalStatus,
    DisciplineAppeal,
    DisciplineCase,
    DisciplineDecision,
)
from apps.okul import selectors as okul_selectors
from apps.okul.models import SchoolYear
from apps.okul.services.calendar import is_working_day


def decisions_for_case(case: DisciplineCase) -> QuerySet[DisciplineDecision]:
    """Bir dosyanın resmî kararları (itirazları + öğrenci önceden çekilir)."""
    return case.decisions.select_related("student").prefetch_related("appeals")


def close_eligibility_details(
    case: DisciplineCase, *, today: date | None = None
) -> tuple[bool, date | None, str]:
    """Dosya ELLE kapatılabilir mi + en erken uygun gün + engel açıklaması.

    Gerçek kapanış kararın KESİNLEŞMESİNE bağlıdır (md. 169). Her CANLI ceza
    kararı için: md. 197 askısı → uygun değil; itirazı İNCELENİYOR → uygun değil;
    itiraz sonuçlanmış → kesin; tebliğ edilmiş + itirazsız → itiraz son günü +
    tampon sonrası uygun; tebliğsiz (REJECTED değil) → uygun değil. Kesinleşen
    uygulanabilir cezaların e-Okul'a işlendiği de onaylanmalıdır. Hiç karar yoksa
    hemen uygun.
    """
    if today is None:
        today = timezone.localdate()
    decisions = list(case.decisions.prefetch_related("appeals"))
    if not decisions:
        return (True, None, "")

    eligible_dates: list[date] = []
    for d in decisions:
        if d.approval_status in (
            DecisionApprovalStatus.RETURNED_TO_COMMITTEE,
            DecisionApprovalStatus.REFERRED_TO_DISTRICT,
        ):
            return (False, None, "Karar müdür incelemesinde veya ilçe kurulunda.")
        appeals = list(d.appeals.all())
        if any(a.result == AppealResult.PENDING for a in appeals):
            return (False, None, "İtiraz incelemesi sonuçlanmadı.")
        if any(a.resulted_on is not None for a in appeals):
            continue  # itiraz kesinleşti → bu karar kapanışa engel değil
        if d.approval_status == DecisionApprovalStatus.REJECTED:
            continue  # itiraz bozması ile kaldırılmış → kesin
        if d.notified_at is None or d.appeal_deadline is None:
            return (False, None, "Karar önce öğrenciye/veliye tebliğ edilmelidir.")
        eligible_dates.append(
            discipline_periods.close_eligible_deadline(
                d.appeal_deadline, is_working_day=is_working_day
            )
        )

    latest = max(eligible_dates) if eligible_dates else None
    if latest is not None and today < latest:
        return (False, latest, "İtiraz süresi ve kapanış tamponu henüz dolmadı.")

    for d in decisions:
        if (
            d.penalty_type != "NO_PENALTY"
            and d.approval_status != DecisionApprovalStatus.REJECTED
            and d.e_school_processed_on is None
        ):
            return (
                False,
                None,
                "Kesinleşen cezanın e-Okul'a işlendiği onaylanmalıdır.",
            )
    return (True, latest, "")


def close_eligible(case: DisciplineCase, *, today: date | None = None) -> tuple[bool, date | None]:
    """Geriye uyumlu kısa kapanış sonucu."""
    eligible, eligible_on, _reason = close_eligibility_details(case, today=today)
    return eligible, eligible_on


def decision_is_final(
    decision: DisciplineDecision, *, today: date | None = None
) -> tuple[bool, str]:
    """Tek kararın KESİNLEŞME durumu (md. 169/3-4) — (kesin_mi, değilse Türkçe sebep).

    Ceza günleri tebliği (Form-16/17) kilidi için: ceza ancak kesinleştikten
    sonra uygulanır/tebliğ edilir. (`close_eligible`'dan farklı soru — REJECTED
    orada "kapanışa engel değil", burada "uygulanacak ceza yok" sayılır.)
    """
    if today is None:
        today = timezone.localdate()
    if decision.approval_status in (
        DecisionApprovalStatus.RETURNED_TO_COMMITTEE,
        DecisionApprovalStatus.REFERRED_TO_DISTRICT,
    ):
        return (False, "karar müdür incelemesinde/ilçe kurulunda (md. 197)")
    if decision.approval_status == DecisionApprovalStatus.REJECTED:
        return (False, "karar itiraz sonucu bozulmuş/kaldırılmış")
    appeals = list(decision.appeals.all())
    if any(a.result == AppealResult.PENDING for a in appeals):
        return (False, "itiraz incelemesi sürüyor (md. 172/2-ç)")
    if any(a.resulted_on is not None for a in appeals):
        return (True, "")  # itiraz sonuçlandı → kesin (md. 169/4)
    if decision.notified_at is None or decision.appeal_deadline is None:
        return (False, "ceza henüz tebliğ edilmedi (itiraz süresi tebliğle başlar)")
    if today <= decision.appeal_deadline:
        return (
            False,
            f"itiraz süresi dolmadı (son gün {decision.appeal_deadline.strftime('%d.%m.%Y')})",
        )
    return (True, "")


def get_decision(case: DisciplineCase, decision_id: int) -> DisciplineDecision | None:
    """Belirli dosyaya ait tek karar (silinmemiş) — yoksa None."""
    return DisciplineDecision.objects.filter(case=case, pk=decision_id).first()


def get_any_decision(case: DisciplineCase, decision_id: int) -> DisciplineDecision | None:
    """Belirli dosyaya ait tek karar — SİLİNMİŞLER DAHİL (geri yükleme için)."""
    return DisciplineDecision.all_objects.filter(case=case, pk=decision_id).first()


def deleted_decisions(case: DisciplineCase) -> list[DisciplineDecision]:
    """Dosyanın SİLİNMİŞ kararları (çöp kutusu) — en son silinen önce."""
    return list(
        DisciplineDecision.all_objects.filter(case=case, deleted_at__isnull=False)
        .select_related("student")
        .order_by("-deleted_at")
    )


def get_decision_by_id(decision_id: int) -> DisciplineDecision | None:
    """Tek karar (id ile) — dosyasıyla birlikte. Yoksa None."""
    return DisciplineDecision.objects.select_related("case").filter(pk=decision_id).first()


def appeals_for_decision(decision: DisciplineDecision) -> QuerySet[DisciplineAppeal]:
    """Bir kararın itirazları (en yeni önce)."""
    return decision.appeals.all()


def latest_resolved_appeal(decision: DisciplineDecision) -> DisciplineAppeal | None:
    """Kararın EN SON sonuçlanmış itirazı (md. 169/4) — yoksa None.

    Üst kurul kararı tebliğinde (BOARD_DECISION_NOTICE) merci/sonuç ön-dolumu için.
    """
    return (
        decision.appeals.filter(resulted_on__isnull=False)
        .exclude(result=AppealResult.PENDING)
        .order_by("-resulted_on", "-created_at")
        .first()
    )


def get_appeal_by_id(appeal_id: int) -> DisciplineAppeal | None:
    """Tek itiraz (id ile) — kararı + dosyası ile. Yoksa None."""
    return DisciplineAppeal.objects.select_related("decision__case").filter(pk=appeal_id).first()


def decisions_for_student(student_id: int) -> QuerySet[DisciplineDecision]:
    """Öğrencinin (tüm dosyalardaki) kararları — sicil ekranı için."""
    return DisciplineDecision.objects.filter(student_id=student_id).select_related("case")


def behavior_point_for_student(student_id: int, school_year_id: int | None = None) -> int:
    """Öğrencinin güncel davranış puanı (md. 170): 100 − bozulmamış kararların indirimi.

    Ders yılı `decision_date` aralığından çözülür (verilmezse aktif yıl). İtirazı
    "bozuldu" (OVERTURNED) ile sonuçlanan kararlar puan iadesi gereği hariç
    tutulur (md. 171). Aktif yıl yoksa tüm kararlar dikkate alınır.
    """
    year: SchoolYear | None
    if school_year_id is not None:
        year = SchoolYear.objects.filter(pk=school_year_id).first()
    else:
        year = okul_selectors.active_school_year()
    qs = DisciplineDecision.objects.filter(student_id=student_id)
    if year is not None:
        qs = qs.filter(decision_date__gte=year.start_date, decision_date__lte=year.end_date)
    overturned = DisciplineAppeal.objects.filter(result=AppealResult.OVERTURNED).values_list(
        "decision_id", flat=True
    )
    qs = qs.exclude(pk__in=overturned)
    total = qs.aggregate(s=Sum("behavior_point_deduction"))["s"] or 0
    return max(0, BEHAVIOR_POINT_START - int(total))


def decisions_awaiting_notification() -> QuerySet[DisciplineDecision]:
    """Tebliğ bekleyen kararlar (md. 169/5) — açık dosyada, askıda/bozulmuş olmayan.

    "Yaklaşan Süreler" paneli 4. bölümü bunu okur.
    """
    return (
        DisciplineDecision.objects.filter(notified_at__isnull=True)
        .exclude(
            approval_status__in=[
                DecisionApprovalStatus.RETURNED_TO_COMMITTEE,
                DecisionApprovalStatus.REFERRED_TO_DISTRICT,
                DecisionApprovalStatus.REJECTED,
            ]
        )
        .filter(case__closed_at__isnull=True)
        .select_related("case", "student")
    )


def appeals_awaiting_forward(through_date: date) -> QuerySet[DisciplineAppeal]:
    """Sevk edilmemiş, sonucu bekleyen ve sevk süresi `through_date`'e kadar olan itirazlar.

    "Yaklaşan Süreler" paneli (deadlines.py) bunu okur — müdürlüğün üst kurula
    sevk yükümlülüğü (md. 169/3, en geç 5 iş günü).
    """
    return DisciplineAppeal.objects.filter(
        forwarded_on__isnull=True,
        result=AppealResult.PENDING,
        forward_deadline__isnull=False,
        forward_deadline__lte=through_date,
    ).select_related("decision__case")
