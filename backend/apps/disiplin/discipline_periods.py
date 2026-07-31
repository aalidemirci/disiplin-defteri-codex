"""Disiplin yasal süreleri + mevzuat eşleme tabloları (Tur 72, Faz 6).

Saf mantık: ORM/Django'ya bağlı değildir (state_machine.py gibi), kolay test edilir.
Sihirli sayı yok — tüm süreler/eşlemeler adlandırılmış sabit + mevzuat madde atfı.

**İş günü (`add_working_days`):** varsayılan olarak yalnız hafta sonunu (Cmt/Pazar)
atlar. Resmî/idari tatilleri de saymak için opsiyonel `is_working_day` yüklemi
(predicate) geçilir — üretimde çağıran katman `apps.okul.services.calendar.is_working_day`'i
(CalendarEvent tatillerini gören) enjekte eder; böylece bu modül ORM'siz/saf kalır
(test'te basit bir lambda yeterli). Tur 90 (Faz 5): ADR-0009 "resmî tatil açık soru"
bu predicate ile kapatıldı.

Mevzuat: Ortaöğretim Kurumları Yönetmeliği md. 163 (ceza/onay), 169 (itiraz/tebliğ),
170 (davranış puanı) — data/mevzuat/ortaogretim-kurumlari-yonetmeligi.md.
"""

from __future__ import annotations

from datetime import date

from apps.disiplin.models import ApprovalAuthority, PenaltyType

# İş günü aritmetiği `shared.working_days`'e taşındı (Tur 189 — rehberlik de kullanır).
# Geriye uyumluluk için buradan AÇIKÇA re-export edilir (`X as X` — mypy explicit
# re-export); mevcut `discipline_periods.add_working_days` importları çalışmaya devam eder.
from shared.working_days import WorkingDayPredicate as WorkingDayPredicate
from shared.working_days import add_working_days as add_working_days

# --- Yasal süreler (iş günü) — md. 169/3 ---
APPEAL_FILING_WORKING_DAYS = 5  # cezanın tebliğini izleyen 5 iş günü içinde itiraz
APPEAL_FORWARD_WORKING_DAYS = 5  # müdürlük en geç 5 iş günü içinde üst kurula sevk eder

# --- Dosya kapanış tamponu (Tur 180, Talep 1a) ---
# Mevzuat süresi DEĞİL — okul tercihi. İtiraz süresi (tebliğ + 5 iş günü) dolduktan
# SONRA, geç ulaşan tebligatları (örn. veli elden almayıp PTT'yle tebliğ) yakalamak
# için ek güvenlik tamponu. Kurul başkanı dosyayı en erken (itiraz son günü + bu
# tampon) ELLE kapatabilir (itirazsız hâl); itiraz varsa kapanış sonuç kesinleşmesine bağlıdır.
CLOSE_BUFFER_WORKING_DAYS = 5

# --- Kurul karar süresi — md. 192/3 ---
# Kurul, konuyu "kurula gelişinden itibaren" en geç 10 iş günü içinde karara bağlar.
# Süre yetmezse ara karar + müdür onayıyla (Form-12/13) ANCAK BİR KEZ uzatılabilir.
COMMITTEE_DECISION_WORKING_DAYS = 10
COMMITTEE_EXTENSION_MAX_COUNT = 1  # md. 192/3: "ancak bir kez uzatılabilir"

# --- Tedbir (geçici uzaklaştırma) — md. 175 ---
# md. 175/1: acele tedbir olmak üzere "on iş gününü geçmemek" kaydıyla uzaklaştırma.
# md. 175/2: tedbir kararını izleyen en geç 3 iş günü içinde disiplin işlemine başlanır;
# haklı/zorlayıcı sebep devam ederse milli eğitim müdürü onayıyla iki kez daha uzatılabilir.
PRECAUTION_MAX_WORKING_DAYS = 10
PRECAUTION_PROCESS_START_WORKING_DAYS = 3
PRECAUTION_EXTENSION_MAX_COUNT = 2  # md. 175/2: "iki kez daha uzatılabilir"

# --- Kısa süreli uzaklaştırma uygulaması — md. 164/2, 172 ---
# md. 164/2: "Okuldan 1-5 gün arasında kısa süreli uzaklaştırma". Uzaklaştırma günleri
# iş günü (tatil hariç) sayılır; uygulama başlangıcından itibaren.
SUSPENSION_MIN_DAYS = 1
SUSPENSION_MAX_DAYS = 5

# --- Davranış puanı indirimi — md. 170 ---
BEHAVIOR_POINT_START = 100
BEHAVIOR_POINT_DEDUCTION: dict[str, int] = {
    PenaltyType.REPRIMAND: 10,
    PenaltyType.SHORT_TERM_SUSPENSION: 20,
    PenaltyType.SCHOOL_CHANGE: 40,
    PenaltyType.EXPULSION: 80,
    PenaltyType.NO_PENALTY: 0,  # ceza yok → davranış puanı düşmez (Tur 181, md. 191)
}

# --- Onay mercii — md. 163/2 ---
APPROVAL_AUTHORITY: dict[str, str] = {
    PenaltyType.REPRIMAND: ApprovalAuthority.PRINCIPAL,
    PenaltyType.SHORT_TERM_SUSPENSION: ApprovalAuthority.PRINCIPAL,
    PenaltyType.SCHOOL_CHANGE: ApprovalAuthority.DISTRICT_BOARD,
    PenaltyType.EXPULSION: ApprovalAuthority.PROVINCIAL_BOARD,
    PenaltyType.NO_PENALTY: ApprovalAuthority.PRINCIPAL,  # üst mercie gitmez (Tur 181)
}

# --- İtiraz mercii (bir üst kurul) — md. 169/3 ---
APPEAL_AUTHORITY: dict[str, str] = {
    PenaltyType.REPRIMAND: ApprovalAuthority.DISTRICT_BOARD,
    PenaltyType.SHORT_TERM_SUSPENSION: ApprovalAuthority.DISTRICT_BOARD,
    PenaltyType.SCHOOL_CHANGE: ApprovalAuthority.PROVINCIAL_BOARD,
    PenaltyType.EXPULSION: ApprovalAuthority.UPPER_BOARD,
}


def deduction_for(penalty_type: str) -> int:
    """Ceza türünün davranış puanı indirimi (md. 170). Bilinmeyen tür → 0."""
    return BEHAVIOR_POINT_DEDUCTION.get(penalty_type, 0)


def approval_authority_for(penalty_type: str) -> str:
    """Cezayı onaylayacak merci (md. 163/2). Varsayılan: okul müdürü."""
    return APPROVAL_AUTHORITY.get(penalty_type, ApprovalAuthority.PRINCIPAL)


def appeal_authority_for(penalty_type: str) -> str:
    """İtirazı görüşecek üst merci (md. 169/3). Varsayılan: ilçe kurulu."""
    return APPEAL_AUTHORITY.get(penalty_type, ApprovalAuthority.DISTRICT_BOARD)


def appeal_deadline(
    notified_on: date, *, is_working_day: WorkingDayPredicate | None = None
) -> date:
    """İtiraz son günü: tebliğ + 5 iş günü (md. 169/3)."""
    return add_working_days(notified_on, APPEAL_FILING_WORKING_DAYS, is_working_day=is_working_day)


def forward_deadline(filed_on: date, *, is_working_day: WorkingDayPredicate | None = None) -> date:
    """Müdürlüğün üst kurula sevk son günü: itiraz başvuru + 5 iş günü (md. 169/3)."""
    return add_working_days(filed_on, APPEAL_FORWARD_WORKING_DAYS, is_working_day=is_working_day)


def close_eligible_deadline(
    deadline: date, *, is_working_day: WorkingDayPredicate | None = None
) -> date:
    """İtirazsız kapanış için en erken uygun gün: itiraz son günü + tampon (Tur 180, Talep 1a).

    `deadline` = kararın itiraz son günü (tebliğ + 5 iş günü). Üstüne CLOSE_BUFFER_WORKING_DAYS
    eklenir (okul tercihi tampon; mevzuat süresi değil).
    """
    return add_working_days(deadline, CLOSE_BUFFER_WORKING_DAYS, is_working_day=is_working_day)


def committee_decision_deadline(
    referred_on: date, *, is_working_day: WorkingDayPredicate | None = None
) -> date:
    """Kurul karar son günü: kurula geliş + 10 iş günü (md. 192/3).

    `referred_on` = dosyanın kurula sevk edildiği gün (müdürün DISCIPLINE_COMMITTEE
    kararının olay tarihi). Uzatma varsa son gün ayrıca hesaplanır (extension snapshot).
    """
    return add_working_days(
        referred_on, COMMITTEE_DECISION_WORKING_DAYS, is_working_day=is_working_day
    )


def precaution_process_start_deadline(
    precaution_start: date, *, is_working_day: WorkingDayPredicate | None = None
) -> date:
    """Tedbir sonrası disiplin işlemine başlama son günü: tedbir + 3 iş günü (md. 175/2)."""
    return add_working_days(
        precaution_start, PRECAUTION_PROCESS_START_WORKING_DAYS, is_working_day=is_working_day
    )


def suspension_end_date(
    start: date, days: int, *, is_working_day: WorkingDayPredicate | None = None
) -> date:
    """Kısa süreli uzaklaştırmanın son (bitiş) günü: başlangıç + (days-1) iş günü.

    `days` 1..SUSPENSION_MAX_DAYS aralığında olmalı (md. 164/2 "1-5 gün"). Başlangıç
    günü dahil sayılır (1 gün → start'ın kendisi). İş günü tanımı `is_working_day`
    yüklemiyle (üretimde resmî/idari tatilleri de atlar). Aralık dışı → ValueError.
    """
    if not (SUSPENSION_MIN_DAYS <= days <= SUSPENSION_MAX_DAYS):
        raise ValueError(
            f"Uzaklaştırma süresi {SUSPENSION_MIN_DAYS}-{SUSPENSION_MAX_DAYS} "
            "gün olmalıdır (md. 164/2)."
        )
    return add_working_days(start, days - 1, is_working_day=is_working_day)


def school_return_date(end: date, *, is_working_day: WorkingDayPredicate | None = None) -> date:
    """Okula başlama günü: uzaklaştırmanın bitişinden sonraki ilk iş günü (md. 172)."""
    return add_working_days(end, 1, is_working_day=is_working_day)


def precaution_end_date(
    precaution_start: date, days: int, *, is_working_day: WorkingDayPredicate | None = None
) -> date:
    """Tedbirin (geçici uzaklaştırma) bitiş günü: başlangıç + `days` iş günü (md. 175/1).

    `days` 1..PRECAUTION_MAX_WORKING_DAYS aralığında olmalıdır (md. 175/1 "on iş gününü
    geçmemek"). Aralık dışı → ValueError. Bitiş, son uzaklaştırma gününü gösterir
    (start dahil sayılır: 1 iş günü → start'ın kendisi).
    """
    if not (1 <= days <= PRECAUTION_MAX_WORKING_DAYS):
        raise ValueError(
            f"Tedbir süresi 1-{PRECAUTION_MAX_WORKING_DAYS} iş günü olmalıdır (md. 175/1)."
        )
    # 1 iş günü = yalnız start günü; bu yüzden days-1 iş günü eklenir.
    return add_working_days(precaution_start, days - 1, is_working_day=is_working_day)
