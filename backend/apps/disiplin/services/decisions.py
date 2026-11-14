"""Disiplin kararı + yasal süreler + itiraz — md. 163-175.

OYS `services/discipline_decisions.py`'den temizlenerek taşındı: audit +
kullanıcı/ip parametreleri silindi; iş günü yüklemi yerel takvimden
(`apps.okul.services.calendar.is_working_day`). İş kuralları AYNEN.
"""

from __future__ import annotations

import re
from datetime import date

from django.db import transaction
from django.utils import timezone

from apps.disiplin import discipline_periods
from apps.disiplin.models import (
    AppealFiledByRole,
    AppealResult,
    ApprovalAuthority,
    CaseStage,
    DecisionApprovalStatus,
    DisciplineAppeal,
    DisciplineCase,
    DisciplineDecision,
    DisciplineEvent,
    DisciplineMeeting,
    PenaltyType,
)
from apps.disiplin.services.common import case_has_student
from apps.okul.services.calendar import is_school_open_day, is_working_day

#: Onaylayan merciden bir üst itiraz mercii (md. 169/3-4: kararı onaylayan kurul aynı
#: karara itirazı görüşemez; müdür onaylı ceza → ilçe; ilçe → il; il → üst kurul).
_NEXT_APPEAL_BOARD: dict[str, str] = {
    ApprovalAuthority.PRINCIPAL: ApprovalAuthority.DISTRICT_BOARD,
    ApprovalAuthority.DISTRICT_BOARD: ApprovalAuthority.PROVINCIAL_BOARD,
    ApprovalAuthority.PROVINCIAL_BOARD: ApprovalAuthority.UPPER_BOARD,
}


#: "Verilmedi" nöbetçisi — None'dan ayırt etmek için (None = alanı TEMİZLE).
_UNSET: object = object()


def appeal_authority_for_decision(decision: DisciplineDecision) -> str:
    """Kararın itiraz mercii — cezayı ONAYLAYAN merciinin bir üstü (md. 169/3-4).

    Normal akışta ceza türünden türeyen tabloyla aynıdır (kınama/uzaklaştırma →
    ilçe; okul değiştirme → il; örgün dışı → üst kurul). Fark md. 197'dedir:
    müdürün ilçeye gönderdiği kararı ilçe kurulu bağlar; ona itiraz il kurulundadır
    (md. 202/1-b).
    """
    approver = (
        ApprovalAuthority.DISTRICT_BOARD
        if decision.referred_to_district
        and decision.approval_authority == ApprovalAuthority.PRINCIPAL
        else decision.approval_authority
    )
    return _NEXT_APPEAL_BOARD.get(approver, ApprovalAuthority.UPPER_BOARD)


def _validate_enforcement_start(
    decision_penalty_type: str,
    enforcement_start_date: date | None,
    *,
    approved_at: date | None = None,
) -> None:
    """Uzaklaştırma uygulama başlangıcı okulun AÇIK olduğu bir gün olmalı (md. 172/1-a).

    Hafta sonu/tatil/ara tatil günü başlangıç olarak 1. ceza günü sayılır ve
    öğrenci fiilen eksik gün ceza çeker. Onay tarihi biliniyorsa başlangıç ondan
    önce olamaz (md. 163/2 "onayından sonra uygulanır").
    """
    if enforcement_start_date is None:
        return
    if decision_penalty_type != PenaltyType.SHORT_TERM_SUSPENSION:
        return
    if not is_school_open_day(enforcement_start_date):
        raise ValueError(
            "Uzaklaştırma başlangıcı okulun açık olduğu bir gün olmalıdır "
            "(hafta sonu, tatil, ara tatil veya ders yılı dışı olamaz — md. 172/1-a)."
        )
    if approved_at is not None and enforcement_start_date < approved_at:
        raise ValueError("Uzaklaştırma, karar onaylanmadan başlatılamaz (md. 163/2).")


def generate_decision_no(decision_date: date) -> str:
    """Ders yılı içinde sıradaki kurul karar numarasını üretir.

    Biçim ``2025-2026/0001``'dir. Silinmiş kararlar da numarayı tüketir; böylece
    resmî karar defterinde daha önce kullanılmış bir numara yeniden verilmez.
    """
    from apps.okul.models import SchoolYear

    year = (
        SchoolYear.objects.filter(
            start_date__lte=decision_date,
            end_date__gte=decision_date,
        ).first()
        or SchoolYear.objects.filter(is_active=True).first()
    )
    prefix = year.name if year is not None else str(decision_date.year)
    pattern = re.compile(rf"^{re.escape(prefix)}/(\d{{4}})$")
    highest = 0
    for value in DisciplineDecision.all_objects.values_list("decision_no", flat=True):
        match = pattern.match(value or "")
        if match:
            highest = max(highest, int(match.group(1)))
    return f"{prefix}/{highest + 1:04d}"


def ensure_decision_no(decision: DisciplineDecision) -> DisciplineDecision:
    """Eski/boş bir karara ilk belge üretiminde kalıcı karar numarası verir."""
    if not decision.decision_no.strip():
        decision.decision_no = generate_decision_no(decision.decision_date)
        decision.save(update_fields=["decision_no", "updated_at"])
    return decision


@transaction.atomic
def _check_md166(
    case: DisciplineCase,
    *,
    student_id: int,
    penalty_type: str,
    decision_date: date,
    override_reason: str,
) -> str:
    """md. 166: aynı öğretim yılında tekrar → bir derece ağır ceza (kullanıcı kararı B).

    Öğrencinin bu öğretim yılında yürürlükte cezası varsa, ondan ağır OLMAYAN bir ceza
    ancak gerekçeyle girilir (fiilin "aynı" olup olmadığı kurulun takdiridir).
    "Ceza verilmesine yer olmadığı" kararı ceza değildir, kural dışıdır. Temizlenmiş
    gerekçeyi döndürür (gerek yoksa boş).
    """
    from apps.disiplin import selectors
    from apps.disiplin.selectors.decisions import PENALTY_SEVERITY

    reason = (override_reason or "").strip()
    new_rank = PENALTY_SEVERITY.get(penalty_type)
    if new_rank is None:
        return ""
    prior = selectors.same_year_prior_penalty(student_id, decision_date, exclude_case_id=case.pk)
    if prior is None or new_rank > PENALTY_SEVERITY.get(prior.penalty_type, 0):
        return ""
    if not reason:
        raise ValueError(
            f"md. 166: öğrencinin bu öğretim yılında yürürlükte "
            f'"{prior.get_penalty_type_display()}" cezası var '
            f"({prior.decision_no}, {prior.decision_date:%d.%m.%Y}); tekrarında bir derece "
            f"ağır ceza uygulanır. Bu cezayı vermek için kurulun gerekçesini yazın."
        )
    return reason


#: Ceza kararının girilebildiği aşamalar: kurula sevk (DECIDED) ve sonrası. Kapalı
#: dosya ayrıca `closed_at` ile reddedilir.
_DECISION_ENTRY_STAGES = (CaseStage.DECIDED, CaseStage.COMMITTEE_DONE, CaseStage.CLOSED)


def _assert_case_referred(case: DisciplineCase) -> date:
    """md. 163/2: ceza kararı yalnız kurula SEVKLİ dosyada girilir — sevk tarihini döndürür.

    Sevk olayının varlığı yetmez: aşama geri alınmışsa (`revert_stage` olay silmez)
    dosyanın GÜNCEL aşaması sevk öncesindedir ve sevk hükümsüzdür (saha testi 14.11.2026).
    """
    from apps.disiplin import selectors

    if case.current_stage not in _DECISION_ENTRY_STAGES:
        raise ValueError(
            "Dosyanın kurula sevki geri alınmış (güncel aşama: "
            f'"{case.get_current_stage_display()}"); ceza kararı yalnız kurula sevkli '
            "dosyada girilir (md. 163/2). Önce müdür değerlendirmesinde "
            '"Disiplin Kuruluna Sevk" kararını yeniden kaydedin.'
        )
    referred_on = selectors.committee_referred_on(case)
    if referred_on is None:
        raise ValueError(
            "Dosya okul öğrenci ödül ve disiplin kuruluna sevk edilmemiş; ceza kararı "
            "yalnız kurulda görüşülüp karara bağlanan dosyada girilir (md. 163/2)."
        )
    return referred_on


# ---------------------------------------------------------------------------
# TOPLANTI ZORUNLU (kullanıcı kararı, 14.11.2026 — S8) — md. 191/1, 196/1
# ---------------------------------------------------------------------------
def _live_meeting(meeting_id: int | None) -> DisciplineMeeting | None:
    """Kararın bağlı olduğu toplantı — yalnız CANLI ise (silinmişse / bağ yoksa None)."""
    if meeting_id is None:
        return None
    return DisciplineMeeting.objects.filter(pk=meeting_id).first()


def _assert_meeting_usable(
    case: DisciplineCase,
    meeting: DisciplineMeeting,
    *,
    referred_on: date | None,
) -> None:
    """Karar bağlanacak toplantı: aynı dosyada, canlı, yeter sayılı ve sevkten sonra (S8)."""
    from apps.disiplin.services.committee import case_meeting_quorum, meeting_quorum_message

    if meeting.case_id != case.pk:
        raise ValueError("Seçilen toplantı bu dosyaya ait değil.")
    if meeting.deleted_at is not None:
        raise ValueError(
            "Seçilen toplantı kaydı silinmiş; kararı kayıtlı bir kurul toplantısına bağlayın."
        )
    quorum = case_meeting_quorum(meeting)
    if not quorum["ok"]:
        raise ValueError(meeting_quorum_message(meeting, quorum))
    if referred_on is not None and meeting.meeting_date < referred_on:
        # Sevk geri alınıp yeniden yapıldığında eski toplantı bu duruma düşebilir.
        raise ValueError(
            f"Seçilen toplantı ({meeting.meeting_date:%d.%m.%Y}) dosyanın kurula sevk "
            f"tarihinden ({referred_on:%d.%m.%Y}) önce; karar tarihi kurula sevk tarihinden "
            "önce olamaz. Sevkten sonraki toplantıyı seçin ya da yeni toplantı kaydedin."
        )


def _resolve_meeting(case: DisciplineCase, meeting: DisciplineMeeting | None) -> DisciplineMeeting:
    """Yeni kararın bağlanacağı toplantı: verilmişse o; verilmemişse dosyanın TEK toplantısı."""
    if meeting is not None:
        return meeting
    meetings = list(case.meetings.all())
    if not meetings:
        raise ValueError(
            "Bu dosya için kayıtlı kurul toplantısı yok. Disiplin kararı kurul toplantısında "
            "verilir (md. 191/1, 196/1): önce 'Kurul toplantıları' bölümünden toplantıyı "
            "(tarih ve katılan üyeler) kaydedin, sonra kararı o toplantıya bağlı girin."
        )
    if len(meetings) > 1:
        dates = ", ".join(f"{m.meeting_date:%d.%m.%Y}" for m in meetings)
        raise ValueError(
            f"Bu dosyada birden çok kurul toplantısı kayıtlı ({dates}); kararın hangi "
            "toplantıda verildiğini seçin."
        )
    return meetings[0]


def record_decision(
    case: DisciplineCase,
    *,
    student_id: int,
    penalty_type: str,
    meeting: DisciplineMeeting | None = None,
    decision_date: date | None = None,
    suspension_days: int | None = None,
    enforcement_start_date: date | None = None,
    statute_ref: str = "",
    penalty_detail: str = "",
    decision_no: str = "",
    event: DisciplineEvent | None = None,
    notes: str = "",
    md166_override_reason: str = "",
) -> DisciplineDecision:
    """Bir dosyadaki öğrenci için resmî disiplin kararı (ceza) kaydeder (md. 163).

    TOPLANTI ZORUNLU (kullanıcı kararı, 14.11.2026 — S8): karar yalnız dosyanın kayıtlı,
    yeter sayısı olan (md. 191/1) kurul toplantısına bağlı girilir; karar tarihi = toplantı
    tarihi (ayrı tarih girilemez). `meeting` verilmezse dosyanın TEK toplantısı seçilir;
    toplantı yoksa ya da birden çoksa eyleme dönük reddedilir. Toplantısız girilmiş ESKİ
    kararlar (`meeting IS NULL`) geçerlidir; onay/tebliğ/itiraz/kapanış toplantıya bakmaz.

    Davranış puanı indirimi (md. 170) ve onay mercii (md. 163/2) cezadan otomatik
    türetilir. Öğrenci dosyaya dahil olmalı; dosya başına öğrenciye tek (silinmemiş)
    karar (ikinci kez ValueError).
    """
    # Önce eski sıra (ileti ve sıra DEĞİŞMEZ): ceza türü → kapalı dosya → sevk.
    if penalty_type not in set(PenaltyType.values):
        raise ValueError("Geçersiz ceza türü.")
    if case.closed_at is not None:
        raise ValueError("Dosya kapatılmış; resmî karar girilemez.")
    referred_on = _assert_case_referred(case)
    meeting = _resolve_meeting(case, meeting)
    _assert_meeting_usable(case, meeting, referred_on=referred_on)
    if decision_date is not None and decision_date != meeting.meeting_date:
        raise ValueError(
            f"Karar tarihi toplantı tarihidir ({meeting.meeting_date:%d.%m.%Y}); ayrı tarih "
            "girilemez."
        )
    return _create_decision(
        case,
        student_id=student_id,
        penalty_type=penalty_type,
        decision_date=meeting.meeting_date,
        meeting=meeting,
        suspension_days=suspension_days,
        enforcement_start_date=enforcement_start_date,
        statute_ref=statute_ref,
        penalty_detail=penalty_detail,
        decision_no=decision_no,
        event=event,
        notes=notes,
        md166_override_reason=md166_override_reason,
    )


def _create_decision(
    case: DisciplineCase,
    *,
    student_id: int,
    penalty_type: str,
    decision_date: date,
    meeting: DisciplineMeeting | None,
    suspension_days: int | None = None,
    enforcement_start_date: date | None = None,
    statute_ref: str = "",
    penalty_detail: str = "",
    decision_no: str = "",
    event: DisciplineEvent | None = None,
    notes: str = "",
    md166_override_reason: str = "",
) -> DisciplineDecision:
    """Karar kaydının çekirdeği — toplantı şartını ARAMAZ (S8).

    Yalnız `record_decision` (toplantı çözülüp doğrulandıktan sonra) ve test fabrikası
    (`meeting=None` ile S8 öncesi toplantısız kayıt taklidi) çağırır; dışa aktarılmaz.
    """
    if penalty_type not in set(PenaltyType.values):
        raise ValueError("Geçersiz ceza türü.")
    if case.closed_at is not None:
        raise ValueError("Dosya kapatılmış; resmî karar girilemez.")
    referred_on = _assert_case_referred(case)
    if decision_date < referred_on:
        raise ValueError("Karar tarihi kurula sevk tarihinden önce olamaz.")
    if not case_has_student(case, student_id):
        raise ValueError("Öğrenci bu disiplin dosyasına dahil değil.")
    _validate_enforcement_start(penalty_type, enforcement_start_date)
    if DisciplineDecision.objects.filter(case=case, student_id=student_id).exists():
        raise ValueError(
            "Bu öğrenci için bu dosyada zaten bir karar var (düzeltme için mevcut "
            "karar güncellenir/silinir)."
        )
    md166_reason = _check_md166(
        case,
        student_id=student_id,
        penalty_type=penalty_type,
        decision_date=decision_date,
        override_reason=md166_override_reason,
    )

    from apps.disiplin import selectors

    # EK-1 "şimdiye kadar aldığı cezalar": anlık kopya + derleme izi (S11c — bayatlık
    # denetimi kullanıcının sonradan düzenleyebildiği kopyaya değil bu ize bakar).
    prior_summary = selectors.compile_prior_penalties(
        student_id, exclude_case_id=case.pk, on=decision_date
    )
    prior_signature = selectors.compile_prior_penalties(
        student_id, exclude_case_id=case.pk, on=decision_date, signature=True
    )
    decision = DisciplineDecision(
        case=case,
        student_id=student_id,
        event=event,
        meeting=meeting,
        penalty_type=penalty_type,
        statute_ref=statute_ref,
        penalty_detail=penalty_detail,
        decision_no=decision_no.strip() or generate_decision_no(decision_date),
        decision_date=decision_date,
        suspension_days=suspension_days,
        enforcement_start_date=enforcement_start_date,
        behavior_point_deduction=discipline_periods.deduction_for(penalty_type),
        approval_authority=discipline_periods.approval_authority_for(penalty_type),
        approval_status=DecisionApprovalStatus.PENDING,
        prior_penalties_summary=prior_summary,
        prior_penalties_compiled=prior_signature,
        notes=notes,
        md166_override_reason=md166_reason,
    )
    decision.full_clean(exclude=["event", "meeting"])
    decision.save()
    return decision


def _assert_case_open(decision: DisciplineDecision) -> None:
    """Kapanış dayanağı kilidi (kullanıcı kararı 27.09.2026).

    Dosya "onaylı + tebliğli + itiraz süresi dolmuş" olduğu için kapanır; kapalı
    dosyada karar, onay ve tebliğ değişmez. Sonradan gelen işlemler (süre dışı
    itiraz ve sonucu, e-Okul işlendi, md. 171/2 ceza kaldırma) bu kilide tabi değildir.
    """
    if decision.case.closed_at is not None:
        raise ValueError(
            "Dosya kapalı: karar, onay ve tebliğ bilgileri kapanışın dayanağıdır, "
            "değiştirilemez. Düzeltme gerekiyorsa önce dosyayı yeniden açın (aşama geri alma)."
        )


def _assert_decision_editable(decision: DisciplineDecision) -> None:
    """Karar düzenleme/silme koruması.

    Yalnız BEKLEMEDEKİ (PENDING) + tebliğ edilmemiş + itirazsız karar
    düzenlenebilir/silinebilir. Onaylanmış/tebliğ edilmiş karar resmî süreçtir;
    düzeltmesi kurula iade (md. 197) / itiraz kanalındandır.
    """
    _assert_case_open(decision)
    if decision.approval_status != DecisionApprovalStatus.PENDING:
        raise ValueError(
            "Yalnız beklemedeki (onaylanmamış) karar düzenlenebilir/silinebilir; onaylanmış "
            "karar için kurula iade (md. 197) veya itiraz kullanın."
        )
    if decision.notified_at is not None:
        raise ValueError("Tebliğ edilmiş karar düzenlenemez/silinemez.")
    if decision.appeals.exists():
        raise ValueError("İtirazı olan karar düzenlenemez/silinemez.")


@transaction.atomic
def update_decision(
    decision: DisciplineDecision,
    *,
    penalty_type: str,
    decision_date: date | None = None,
    suspension_days: int | None = None,
    enforcement_start_date: date | None = None,
    statute_ref: str = "",
    penalty_detail: str = "",
    decision_no: str = "",
    notes: str = "",
    md166_override_reason: str | None = None,
    meeting: DisciplineMeeting | None | object = _UNSET,
) -> DisciplineDecision:
    """BEKLEMEDEKİ bir kararın çekirdek alanlarını düzenler (md. 163).

    TOPLANTI BAĞI (S8): toplantıya bağlı kararda karar tarihi toplantı tarihidir — yalnız
    `meeting` verilerek (başka toplantıya bağlama; md. 197 iadesinden sonraki ikinci görüşme
    böyle kaydedilir) değişir; bağ KALDIRILAMAZ (`meeting=None` reddedilir). Toplantısız
    girilmiş ESKİ kararda tarih eskisi gibi düzenlenir, toplantı ZORLANMAZ; `meeting`
    verilirse karar o toplantıya bağlanır ve tarihi toplantı tarihine çekilir.

    md. 166 denetimi yeniden uygulanır; `md166_override_reason` verilmezse mevcut
    gerekçe korunur.

    Ceza türü değişirse davranış puanı indirimi + onay mercii yeniden türetilir.
    Uzaklaştırma alanları yalnız kısa süreli uzaklaştırmada saklanır.

    Özgün ceza (S11b): düzenleme yalnız PENDING + tebliğsiz + itirazsız kararda açıktır
    (`_assert_decision_editable`) ve o duruma geçiş (`set_decision_approval` → beklemede)
    üst kurul değişikliğini zaten geri alıp kurulun verdiği cezayı geri yükler; form
    kurulun GERÇEK cezasıyla açılır. Burada girilen ceza kurulun (yeniden görüşüp
    verdiği) kararıdır ve geçerlidir — `board_penalty_*` izi taşınmaz.

    EK-1 "önceki cezalar" (S11c): karar tarihi değişse de özet ve derleme izi YENİDEN
    YAZILMAZ (kullanıcının düzenlemesi ezilmesin). "Önceki" cezalar kümesi yeni tarihe
    göre değiştiyse `prior_penalties_summary_is_stale` uyarı verir; kullanıcı onayla
    yeniden derler.
    """
    from apps.disiplin import selectors

    _assert_decision_editable(decision)
    if penalty_type not in set(PenaltyType.values):
        raise ValueError("Geçersiz ceza türü.")
    referred_on = selectors.committee_referred_on(decision.case)
    bound = _live_meeting(decision.meeting_id)
    new_meeting: DisciplineMeeting | None = bound
    # Kararın ZATEN bağlı olduğu toplantı gönderildiyse değişiklik yoktur: bağ korunur,
    # toplantı yeniden doğrulanmaz (kurul sonradan büyüyüp eski toplantı yetersiz görünse de
    # beklemedeki karar düzenlenebilir kalır) — aşağıdaki "bağlı karar" dalı işler.
    same_meeting = (
        isinstance(meeting, DisciplineMeeting) and bound is not None and meeting.pk == bound.pk
    )
    if isinstance(meeting, DisciplineMeeting) and not same_meeting:
        _assert_meeting_usable(decision.case, meeting, referred_on=referred_on)
        if decision_date is not None and decision_date != meeting.meeting_date:
            raise ValueError(
                f"Karar tarihi toplantı tarihidir ({meeting.meeting_date:%d.%m.%Y}); ayrı "
                "tarih girilemez."
            )
        new_meeting = meeting
        decision_date = meeting.meeting_date
    elif bound is not None:
        if meeting is None:
            raise ValueError(
                "Karar toplantıya bağlıdır; bağ kaldırılamaz, başka toplantıya bağlanabilir."
            )
        if decision_date is not None and decision_date != bound.meeting_date:
            raise ValueError(
                f"Karar tarihi toplantı tarihidir ({bound.meeting_date:%d.%m.%Y}); değiştirmek "
                "için kararı başka bir toplantıya bağlayın."
            )
        if referred_on is not None and bound.meeting_date < referred_on:
            # md. 163/2 — eski (bağsız) karardaki kuralın aynısı. Sevk geri alınıp yeniden
            # yapıldıysa bağlı toplantı sevk öncesinde kalabilir; çıkış: başka toplantı / silme.
            raise ValueError(
                f"Kararın bağlı olduğu toplantı ({bound.meeting_date:%d.%m.%Y}) dosyanın kurula "
                f"sevk tarihinden ({referred_on:%d.%m.%Y}) önce; karar tarihi kurula sevk "
                "tarihinden önce olamaz. Kararı sevkten sonraki bir toplantıya bağlayın (yoksa "
                "önce o toplantıyı kaydedin)."
            )
        decision_date = bound.meeting_date
    else:
        # ESKİ (toplantısız) karar: tarih eskisi gibi düzenlenir; toplantı zorlanmaz.
        if decision_date is None:
            decision_date = decision.decision_date
        # record_decision ile aynı kural (md. 163/2): karar, kurula sevkten önce olamaz.
        if referred_on is not None and decision_date < referred_on:
            raise ValueError("Karar tarihi kurula sevk tarihinden önce olamaz.")

    md166_reason = _check_md166(
        decision.case,
        student_id=decision.student_id,
        penalty_type=penalty_type,
        decision_date=decision_date,
        override_reason=(
            decision.md166_override_reason
            if md166_override_reason is None
            else md166_override_reason
        ),
    )
    is_suspension = penalty_type == PenaltyType.SHORT_TERM_SUSPENSION
    if is_suspension:
        _validate_enforcement_start(penalty_type, enforcement_start_date)
    decision.md166_override_reason = md166_reason
    decision.penalty_type = penalty_type
    decision.decision_date = decision_date
    if new_meeting is not None:
        decision.meeting = new_meeting
    decision.suspension_days = suspension_days if is_suspension else None
    decision.enforcement_start_date = enforcement_start_date if is_suspension else None
    decision.statute_ref = statute_ref
    decision.penalty_detail = penalty_detail
    decision.decision_no = decision_no
    decision.notes = notes
    decision.behavior_point_deduction = discipline_periods.deduction_for(penalty_type)
    decision.approval_authority = discipline_periods.approval_authority_for(penalty_type)
    # Düzenleme kurulun KENDİ kararını yeniden yazar; girilen ceza kurulun cezasıdır.
    # Onay beklemeye alınırken özgün ceza zaten geri yüklenip iz temizlenmiştir
    # (`_restore_board_penalty`); buradaki temizlik yalnız savunmadır (S11b).
    decision.board_penalty_type = ""
    decision.board_suspension_days = None
    decision.full_clean(exclude=["event", "meeting"])
    decision.save()
    return decision


@transaction.atomic
def delete_decision(decision: DisciplineDecision) -> None:
    """BEKLEMEDEKİ bir kararı soft-delete eder (geri alınabilir)."""
    _assert_decision_editable(decision)
    decision.delete()  # soft delete (BaseModel)


@transaction.atomic
def restore_decision(decision: DisciplineDecision) -> DisciplineDecision:
    """Soft-delete edilmiş bir kararı geri yükler.

    Aynı öğrenci için bu dosyada zaten CANLI bir karar varsa reddedilir. Dosya artık
    kurula sevkli değilse (sevk geri alınmış / yazılı uyarıya dönülmüş) karar geri
    gelmez — md. 163/2 (`record_decision` ile aynı kural). Toplantıya bağlı karar (S8),
    toplantısı silinmişse ya da sevk yeniden yapıldığı için toplantı sevk öncesinde
    kaldıysa da geri gelmez.
    """
    if decision.deleted_at is None:
        raise ValueError("Karar zaten geri yüklenmiş (silinmemiş).")
    _assert_case_open(decision)
    referred_on = _assert_case_referred(decision.case)
    if not case_has_student(decision.case, decision.student_id):
        raise ValueError("Öğrenci artık bu dosyada değil; karar geri yüklenemez.")
    if DisciplineDecision.objects.filter(
        case_id=decision.case_id, student_id=decision.student_id
    ).exists():
        raise ValueError("Bu öğrenci için bu dosyada zaten (canlı) bir karar var; geri yüklenemez.")
    if decision.meeting_id is not None and _live_meeting(decision.meeting_id) is None:
        # S8: karar toplantıya dayanır. Toplantısız girilmiş ESKİ karar (bağ boş) bu denetime
        # girmez — eski kararlar geçerli kalır.
        gone = DisciplineMeeting.all_objects.filter(pk=decision.meeting_id).first()
        when = f" ({gone.meeting_date:%d.%m.%Y})" if gone is not None else ""
        raise ValueError(
            f"Kararın bağlı olduğu kurul toplantısı kaydı{when} silinmiş; karar geri "
            "yüklenemez. Toplantıyı yeniden kaydedip kararı yeniden girin."
        )
    if decision.meeting_id is not None and decision.decision_date < referred_on:
        # Karar silindikten sonra sevk geri alınıp yeniden yapılmış: bağlı toplantı artık
        # yürürlükteki sevkten ÖNCE (md. 163/2; `_assert_meeting_usable` ile aynı kural). Yalnız
        # sevk tarihi denetlenir — yeter sayı canlı karardaki gibi yeniden sorgulanmaz. Eski
        # (bağsız) karar bu denetime girmez: tarihi düzenlemede düzeltilir (S8 öncesi davranış).
        raise ValueError(
            f"Kararın bağlı olduğu toplantı ({decision.decision_date:%d.%m.%Y}) dosyanın "
            f"yürürlükteki kurula sevk tarihinden ({referred_on:%d.%m.%Y}) önce; karar geri "
            "yüklenemez. Sevkten sonraki toplantıyı kaydedip kararı yeniden girin."
        )
    decision.restore()
    return decision


@transaction.atomic
def rebind_decision_meeting(
    decision: DisciplineDecision, meeting: DisciplineMeeting
) -> DisciplineDecision:
    """Kararı AYNI TARİHLİ başka bir toplantı kaydına bağlar — karar tarihi DEĞİŞMEZ (S8).

    Yalnız kullanıcı isteğiyle; düzenlemeye kapalı (onaylı / tebliğli / itirazlı) kararlar ve
    toplantısız girilmiş eski kararlar içindir (beklemedeki karar başka tarihli toplantıya
    `update_decision` ile bağlanır). İki işlevi var: (a) eski karara, kullanıcı o tarihli
    toplantıyı kaydettiyse isteğe bağlı bağlama — geriye dönük tarih ÜRETİLMEZ; (b) §7.6
    çıkışı: yanlış kaydedilmiş (ör. vekâleti / katılanları hatalı) toplantıya karar bağlıysa
    toplantı silinemez — doğru kayıt aynı tarihle girilir, karar ona taşınır, eskisi silinir.
    Tarih değişmediği için onay / tebliğ / itiraz zinciri ve süreler etkilenmez. Kapalı dosyada
    reddedilir (kapanış dayanağı kilitli).
    """
    if decision.deleted_at is not None:
        raise ValueError("Silinmiş karar toplantıya bağlanamaz; önce kararı geri yükleyin.")
    _assert_case_open(decision)
    # Sevk tarihi yeniden denetlenmez: karar tarihi değişmiyor.
    _assert_meeting_usable(decision.case, meeting, referred_on=None)
    if meeting.meeting_date != decision.decision_date:
        raise ValueError(
            f"Karar tarihi ({decision.decision_date:%d.%m.%Y}) değişmez: karar yalnız aynı "
            f"tarihli bir toplantı kaydına bağlanabilir (seçilen toplantı: "
            f"{meeting.meeting_date:%d.%m.%Y}). Beklemedeki (onaylanmamış) kararı başka tarihli "
            "toplantıya bağlamak için kararı düzenleyin."
        )
    decision.meeting = meeting
    decision.save(update_fields=["meeting", "updated_at"])
    return decision


@transaction.atomic
def set_decision_approval(
    decision: DisciplineDecision,
    *,
    approval_status: str,
    approved_on: date | None = None,
    modified_penalty_type: str = "",
    modified_suspension_days: int | None = None,
) -> DisciplineDecision:
    """Kararın onay durumunu günceller (md. 163/2 — merci sistem dışı, manuel giriş).

    md. 197: müdür yalnız onaylar (APPROVED) ya da beklemede bırakır (PENDING);
    reddetme yoktur. APPROVED + kınama/kısa uzaklaştırma → uygulanır (md. 172).

    Geçiş korumaları: itirazla bozulmuş (REJECTED) karar yeniden onaylanamaz;
    tebliğ edilmiş karar onaysız hâle döndürülemez; onay tarihi karar tarihinden
    önce olamaz. İlçe kuruluna gönderilmiş (md. 197) kararda APPROVED = ilçe
    kurulunun kararı bağlaması; aynı kararda PENDING "müdür onayı bekliyor"a değil
    "ilçe kurulunda"ya (REFERRED) döner — müdür o kararı artık onaylayamaz, yanlış
    girilen ilçe kararı böyle geri alınır (saha testi 14.11.2026, tek yönlü kapan).

    `modified_penalty_type`: onay mercii bir KURUL ise (okul değiştirme → ilçe,
    örgün dışı → il; md. 197 ile ilçeye giden karar) kurul "onaylar veya
    DEĞİŞTİRİR" (md. 200/1-a, 202/1-a). Değiştirilen ceza türü + puan burada
    işlenir; itiraz mercii onaylayan kurulun bir üstü kalır.

    Onayın GERİ ALINMASI (beklemede / ilçe kurulunda) üst kurulun yaptığı ceza
    değişikliğini de geri alır (S11b — `_restore_board_penalty`): kararda itiraz kaydı
    yoksa ve özgün ceza kayıtlıysa ceza, gün ve puan kurulun verdiğine döner, özgün
    ceza alanları temizlenir. İtiraz kaydı varsa cezaya dokunulmaz.
    """
    _assert_case_open(decision)
    if approval_status not in {DecisionApprovalStatus.PENDING, DecisionApprovalStatus.APPROVED}:
        raise ValueError("Müdür kararı yalnız onaylayabilir veya beklemede bırakabilir (md. 197).")
    if decision.approval_status == DecisionApprovalStatus.REJECTED:
        raise ValueError("İtiraz sonucu bozulmuş (kaldırılmış) karar yeniden onaylanamaz.")
    if modified_penalty_type and (decision.notified_at is not None or decision.appeals.exists()):
        raise ValueError(
            "Tebliğ edilmiş ya da itiraz edilmiş kararın cezası onay ucundan "
            "değiştirilemez; itiraz sonucu kesindir (md. 169/4)."
        )
    if approval_status == DecisionApprovalStatus.PENDING and decision.notified_at is not None:
        raise ValueError("Tebliğ edilmiş karar onaysız duruma döndürülemez.")
    if approval_status == DecisionApprovalStatus.APPROVED:
        if approved_on is None:
            raise ValueError("Onay tarihi zorunludur.")
        if approved_on < decision.decision_date:
            raise ValueError("Onay tarihi karar tarihinden önce olamaz.")
        # Onaysız karar tebliğ edilemez (md. 163/2): yeniden onay, kaydı "onaydan
        # önce tebliğ" hâline getiremez.
        if decision.notified_at is not None and approved_on > decision.notified_at:
            raise ValueError("Onay tarihi tebliğ tarihinden sonra olamaz.")
        # md. 169/2-a "onayından sonra uygulanır": başlangıç karar formunda baştan
        # girilmişse onay tarihi onu geçemez (anlatı ucundaki denetimin eşi).
        keeps_start = modified_penalty_type in ("", PenaltyType.SHORT_TERM_SUSPENSION)
        if (
            keeps_start
            and decision.penalty_type == PenaltyType.SHORT_TERM_SUSPENSION
            and decision.enforcement_start_date is not None
            and decision.enforcement_start_date < approved_on
        ):
            raise ValueError(
                f"Uzaklaştırma başlangıcı ({decision.enforcement_start_date:%d.%m.%Y}) onay "
                "tarihinden önce kalıyor; ceza onaydan sonra uygulanır (md. 169/2-a). Önce "
                "uygulama başlangıcını düzeltin ya da boşaltın, sonra onayı kaydedin."
            )
    approving = approval_status == DecisionApprovalStatus.APPROVED
    if not approving:
        approved_on = None
        if decision.referred_to_district:
            approval_status = DecisionApprovalStatus.REFERRED_TO_DISTRICT
    fields = ["approval_status", "approved_at", "updated_at"]
    if modified_penalty_type:
        # Onay mercii kurul mu: ceza türünden (ilçe/il) ya da md. 197 sevkinden. Anlık
        # onay durumuna DEĞİL kalıcı `referred_to_district` işaretine bakılır; yoksa
        # yanlış girilen ilçe onayı düzeltilemezdi.
        board_approves = (
            decision.approval_authority != ApprovalAuthority.PRINCIPAL
            or decision.referred_to_district
        )
        if not approving or not board_approves:
            raise ValueError(
                "Ceza türü yalnız onay mercii kurul olan kararda, onay sırasında "
                "değiştirilebilir (md. 200/1-a, 202/1-a); okul kurulu kararı müdürce "
                "değiştirilemez (md. 197)."
            )
        fields += _apply_penalty_change(decision, modified_penalty_type, modified_suspension_days)
    elif not approving:
        fields += _restore_board_penalty(decision)
    decision.approval_status = approval_status
    decision.approved_at = approved_on
    decision.is_enforced = _enforced_state(decision)
    fields.append("is_enforced")
    decision.save(update_fields=fields)
    return decision


# Onay mercii cezadan türer ve ceza sonradan değişse de DEĞİŞMEZ: mercii ilçe/il olan
# ama cezası artık o olmayan karar, onay aşamasında değiştirilmiştir.
_BOARD_PENALTY_BY_AUTHORITY: dict[str, str] = {
    ApprovalAuthority.DISTRICT_BOARD: PenaltyType.SCHOOL_CHANGE,
    ApprovalAuthority.PROVINCIAL_BOARD: PenaltyType.EXPULSION,
}


def _legacy_board_penalty(decision: DisciplineDecision) -> tuple[str, int | None]:
    """Özgün ceza alanı BOŞKEN okul kurulunun verdiği cezayı belirler.

    Olağan durumda o andaki cezadır (ceza ilk kez değişiyor). İstisna — S11 göçünden
    ÖNCE onayda değiştirilmiş eski kayıt: ceza zaten üst kurulun cezasıdır, özgün ceza
    hiç kaydedilmemiştir. O durumda o andaki cezayı "kurulun verdiği ceza" diye yazmak
    yanlışı kalıcılaştırırdı (alan dolunca belgeler tahmine inmez). Md. 197 ile ilçeye
    gitmemiş ve mercii ilçe/il olan kararda özgün ceza merciden okunur
    (`documents._board_penalty` ile aynı ölçüt); md. 197 yolunda merciden okunamaz,
    o andaki ceza yazılır.
    """
    implied = _BOARD_PENALTY_BY_AUTHORITY.get(decision.approval_authority)
    if (
        implied is not None
        and not decision.referred_to_district
        and decision.penalty_type != implied
    ):
        return implied, None
    return decision.penalty_type, decision.suspension_days


def _apply_penalty_change(
    decision: DisciplineDecision, penalty_type: str, suspension_days: int | None
) -> list[str]:
    """Üst kurulun cezayı değiştirmesini karara işler (puan dahil — md. 170).

    `approval_authority` DEĞİŞMEZ: kararı bağlayan (onaylayan) merci aynı kalır;
    itiraz mercii ondan türer (`appeal_authority_for_decision`). Tür aynı kalabilir:
    yalnız kısa süreli uzaklaştırmada ve gün sayısı farklıysa — süre cezanın unsurudur
    (md. 164/2, 172/1-a), üst kurul yalnız günü değiştirmiş olabilir (md. 200/1-ç).
    Uzaklaştırma sürdükçe uygulama başlangıcı korunur; bitiş yeni günden hesaplanır.

    Özgün ceza (kullanıcı kararı 14.11.2026 — S11b): ceza İLK KEZ değişirken okul
    kurulunun VERDİĞİ ceza (tür + gün) `board_penalty_type` / `board_suspension_days`
    alanlarına yazılır — onay yolunda da itiraz yolunda da tek yer burasıdır. Sonraki
    değişiklikler (yanlış girilen üst kurul kararının düzeltilmesi, onaydan sonra
    itiraz) özgün cezayı EZMEZ. Yeni ceza kurulun verdiğine GERİ DÖNSE de alanlar
    BOŞALTILMAZ: "boş" yalnız "ceza hiç değişmedi / S11 göçünden önce değişti"
    demektir; boşaltılsaydı belgeler (`documents._board_penalty`) eski tahmine düşüp
    itiraza konu cezayı "kurulun verdiği ceza" diye basardı. Özgün ceza = yürürlükteki
    ceza ise fark yoktur (belge ve ekran satır basmaz). Alanlar yalnız üst kurul onayı
    geri alınırken (`_restore_board_penalty`) ve karar düzenlenirken temizlenir.
    İtiraz kaydındaki `previous_*` ayrı tutulur: o, itiraza KONU cezadır.
    Puan/yürürlük/itiraz mercii güncel cezadan türemeye devam eder.
    """
    if penalty_type not in set(PenaltyType.values):
        raise ValueError("Geçersiz ceza türü.")
    if penalty_type == decision.penalty_type:
        if penalty_type != PenaltyType.SHORT_TERM_SUSPENSION:
            raise ValueError(
                "Değiştirilen ceza mevcut cezayla aynı olamaz; ceza aynen kaldıysa "
                "değişiklik seçmeyin."
            )
        if suspension_days == decision.suspension_days:
            raise ValueError(
                f"Uzaklaştırma gün sayısı mevcut cezayla aynı ({decision.suspension_days} gün); "
                "üst kurul süreyi değiştirdiyse yeni gün sayısını girin, ceza aynen kaldıysa "
                "değişiklik seçmeyin."
            )
    is_suspension = penalty_type == PenaltyType.SHORT_TERM_SUSPENSION
    if not decision.board_penalty_type:
        board_type, board_days = _legacy_board_penalty(decision)
        decision.board_penalty_type = board_type
        decision.board_suspension_days = board_days
    decision.penalty_type = penalty_type
    decision.suspension_days = suspension_days if is_suspension else None
    if not is_suspension:
        decision.enforcement_start_date = None
    decision.behavior_point_deduction = discipline_periods.deduction_for(penalty_type)
    decision.full_clean(exclude=["event", "meeting"])
    return [
        "penalty_type",
        "suspension_days",
        "enforcement_start_date",
        "behavior_point_deduction",
        "board_penalty_type",
        "board_suspension_days",
    ]


def _restore_board_penalty(decision: DisciplineDecision) -> list[str]:
    """Üst kurul onayı geri alınırken cezayı kurulun VERDİĞİNE döndürür (S11b).

    Yanlış girilen "değiştirildi" onayı beklemeye çekilince ceza değiştirilmiş hâliyle
    kalıyordu: kart üst kurulun cezasını gösteriyor, düzenleme formu onunla açılıyor ve
    kaydedilince kurulun gerçek kararı (ve onay mercii) sessizce kayboluyordu (§7.6 tek
    yönlü kapan). Özgün ceza kayıtlıysa ve kararda İTİRAZ KAYDI YOKSA ceza + gün + puan
    geri yüklenir (`_apply_penalty_change` ile — tek yazım yeri) ve özgün ceza alanları
    temizlenir: onaysız kararda "değişiklik" kalmaz. İtiraz kaydı varsa dokunulmaz —
    ceza itiraz kanalında değişmiş olabilir, itiraz sonucu kesindir (md. 169/4).
    Kısıt: uzaklaştırma başka cezaya çevrilirken silinen uygulama başlangıcı geri gelmez
    (kayıtta tutulmaz); onay yeniden girilmeden önce karar formundan girilir.
    Döndürdüğü: kaydedilecek alan adları (değişiklik yoksa boş liste).
    """
    if not decision.board_penalty_type or decision.appeals.exists():
        return []
    board_type, board_days = decision.board_penalty_type, decision.board_suspension_days
    fields = ["board_penalty_type", "board_suspension_days"]
    if (board_type, board_days) != (decision.penalty_type, decision.suspension_days):
        fields = _apply_penalty_change(decision, board_type, board_days)
    decision.board_penalty_type = ""
    decision.board_suspension_days = None
    return fields


@transaction.atomic
def record_principal_review(
    decision: DisciplineDecision,
    *,
    action: str,
    reason: str,
    decided_on: date,
) -> DisciplineDecision:
    """md. 197 — müdürün kurul kararını uygun bulmaması (reddetme DEĞİL).

    `action="RETURN"`: kararı gerekçeyle kurula iade eder. `action="REFER"`:
    kurul ısrar edince ilçe kuruluna gönderir — yalnız önce iade edilmiş karar.
    İade edilmiş karar kurulun yeniden görüşmesi için "onay bekliyor"a alınmış olabilir
    (düzenleme yalnız orada açılır); `returned_at` dolu olduğu sürece sevk yolu açık
    kalır, ikinci iade ise kapalıdır ("bir defa daha" — saha testi 14.11.2026).

    Tarihler (kullanıcı kararı 14.11.2026 — S11b): `returned_at` SON md. 197 adımının
    tarihidir (iadede iade, sevkte sevk tarihi — ilçe yazısının tarihi budur);
    `first_returned_at` yalnız İADE'de yazılır ve sevkte EZİLMEZ (ilçe yazısı İlgi (b)
    ile sevkten sonra yeniden üretilen iade yazısı bunu basar).
    """
    reason = (reason or "").strip()
    _assert_case_open(decision)
    if not reason:
        raise ValueError("Kurula iade / ilçeye sevk için gerekçe zorunludur (md. 197).")
    if decision.notified_at is not None:
        raise ValueError("Tebliğ edilmiş karar kurula iade edilemez / ilçeye gönderilemez.")
    if decided_on < decision.decision_date:
        raise ValueError("İade / sevk tarihi karar tarihinden önce olamaz.")
    if action == "RETURN":
        if decision.approval_status != DecisionApprovalStatus.PENDING:
            raise ValueError("Yalnız onay bekleyen karar kurula iade edilebilir (md. 197).")
        if decision.returned_at is not None:
            raise ValueError(
                "Karar kurula zaten bir kez iade edildi; md. 197 yalnız 'bir defa daha "
                "görüşülmek üzere' iade öngörür. Kurul ısrar ediyorsa ilçeye gönderin."
            )
        new_status = DecisionApprovalStatus.RETURNED_TO_COMMITTEE
        decision.first_returned_at = decided_on
    elif action == "REFER":
        returned_before = (
            decision.approval_status == DecisionApprovalStatus.RETURNED_TO_COMMITTEE
            or (
                decision.approval_status == DecisionApprovalStatus.PENDING
                and decision.returned_at is not None
                and not decision.referred_to_district
            )
        )
        if not returned_before:
            raise ValueError(
                "İlçe kuruluna gönderme yalnız önce kurula iade edilmiş kararda yapılabilir "
                "(md. 197 — kurul ısrarı)."
            )
        new_status = DecisionApprovalStatus.REFERRED_TO_DISTRICT
        decision.referred_to_district = True
        # İade gerekçesi korunur; ilçeye sevk gerekçesi (müdürün görüş ve teklifleri)
        # alta eklenir — iki md. 197 adımı da kayıtta kalır.
        reason = f"{decision.return_reason}\n\nİlçeye sevk: {reason}".strip()
    else:
        raise ValueError("Geçersiz işlem; 'RETURN' veya 'REFER' olmalı.")

    decision.approval_status = new_status
    decision.return_reason = reason
    decision.returned_at = decided_on
    decision.approved_at = None
    decision.is_enforced = False
    decision.save(
        update_fields=[
            "approval_status",
            "return_reason",
            "returned_at",
            "first_returned_at",
            "approved_at",
            "is_enforced",
            "referred_to_district",
            "updated_at",
        ]
    )
    return decision


@transaction.atomic
def notify_decision(
    decision: DisciplineDecision,
    *,
    notified_on: date,
    notification_method: str = "",
) -> DisciplineDecision:
    """Kararın tebliğini kaydeder ve itiraz son gününü hesaplar (md. 169/3, 169/5).

    `appeal_deadline` = tebliğ + 5 iş günü (snapshot; yerel tatil takvimi dahil).
    Yalnız ONAYLANMIŞ karar tebliğ edilir (md. 163/2, 169/2 — ceza onaydan sonra
    uygulanır; onaysız kararın tebliği itiraz süresini erken başlatırdı). İtirazı
    olan kararın tebliğ tarihi değiştirilemez (itiraz süre bayrakları bayatlar).
    """
    _assert_case_open(decision)
    if decision.approval_status != DecisionApprovalStatus.APPROVED:
        raise ValueError(
            "Karar onaylanmadan tebliğ edilemez (md. 163/2, 169/2): önce onay "
            "durumunu (müdür / ilçe / il kurulu onayı) kaydedin."
        )
    if decision.appeals.exists():
        raise ValueError("İtirazı olan kararın tebliğ tarihi değiştirilemez.")
    if decision.approved_at is not None and notified_on < decision.approved_at:
        raise ValueError("Tebliğ tarihi onay tarihinden önce olamaz.")
    if notified_on < decision.decision_date:
        raise ValueError("Tebliğ tarihi karar tarihinden önce olamaz.")
    decision.notified_at = notified_on
    decision.notification_method = notification_method
    decision.appeal_deadline = discipline_periods.appeal_deadline(
        notified_on, is_working_day=is_working_day
    )
    decision.save(
        update_fields=["notified_at", "notification_method", "appeal_deadline", "updated_at"]
    )
    return decision


@transaction.atomic
def confirm_e_school_entry(
    decision: DisciplineDecision,
    *,
    processed_on: date,
) -> DisciplineDecision:
    """Kesinleşen cezanın e-Okul'a işlendiğini kaydeder.

    Ceza kesinleşmeden veya ceza verilmesine yer olmadığı kararında bu onay
    verilemez. Böylece arayüzdeki uyarı yalnız metin değil, sunucu tarafında da
    uygulanan bir süreç kuralıdır.
    """
    from apps.disiplin import selectors

    if decision.penalty_type == PenaltyType.NO_PENALTY:
        raise ValueError("Ceza verilmesine yer olmadığı kararı e-Okul'a işlenmez.")
    final, reason = selectors.decision_is_final(decision)
    if not final:
        raise ValueError(f"Ceza kesinleşmeden e-Okul onayı verilemez: {reason}.")
    if processed_on > timezone.localdate():
        raise ValueError("e-Okul'a işlenme tarihi gelecekte olamaz.")
    result_dates = [
        appeal.resulted_on for appeal in decision.appeals.all() if appeal.resulted_on is not None
    ]
    if result_dates:
        if processed_on < max(result_dates):
            raise ValueError("e-Okul'a işlenme tarihi itirazın sonuç tarihinden önce olamaz.")
    elif decision.appeal_deadline is not None and processed_on <= decision.appeal_deadline:
        raise ValueError("e-Okul'a işlenme tarihi itiraz süresinin bitiminden sonra olmalıdır.")
    decision.e_school_processed_on = processed_on
    decision.save(update_fields=["e_school_processed_on", "updated_at"])
    return decision


@transaction.atomic
def file_appeal(
    decision: DisciplineDecision,
    *,
    filed_on: date,
    filed_by_role: str,
    filed_by_name: str = "",
) -> DisciplineAppeal:
    """Karara itiraz kaydeder (md. 169/3). Tebliğ yapılmış olmalı.

    `within_deadline` = başvuru ≤ itiraz son günü. Okul değiştirmede süresi
    içinde itiraz → uygulama bekletilir (md. 172/2-ç → is_enforced=False).
    """
    if filed_by_role not in set(AppealFiledByRole.values):
        raise ValueError("Geçersiz itiraz eden rolü.")
    if decision.penalty_type == PenaltyType.NO_PENALTY:
        raise ValueError("'Ceza verilmesine yer olmadığı' kararına itiraz yolu yoktur (md. 169/3).")
    if decision.notified_at is None or decision.appeal_deadline is None:
        raise ValueError("İtiraz için karar önce tebliğ edilmelidir (md. 169/3).")
    if filed_on < decision.notified_at:
        raise ValueError("İtiraz tarihi tebliğ tarihinden önce olamaz (md. 169/3).")
    if decision.appeals.filter(resulted_on__isnull=False).exists():
        raise ValueError(
            "Bu karara yapılan itiraz sonuçlanmış; itiraz sonucu verilen karar kesindir, "
            "yeniden itiraz edilemez (md. 169/4)."
        )
    if filed_by_role == AppealFiledByRole.STUDENT_ADULT:
        _assert_adult(decision, filed_on)

    within = filed_on <= decision.appeal_deadline
    appeal = DisciplineAppeal(
        decision=decision,
        filed_on=filed_on,
        filed_by_role=filed_by_role,
        filed_by_name=filed_by_name,
        within_deadline=within,
        appeal_authority=appeal_authority_for_decision(decision),
        forward_deadline=discipline_periods.forward_deadline(
            filed_on, is_working_day=is_working_day
        ),
        result=AppealResult.PENDING,
    )
    appeal.full_clean()
    appeal.save()

    # md. 172/2-ç: okul değiştirmede süresi içinde itiraz → karar verilene kadar uygulanmaz.
    if within and decision.penalty_type == PenaltyType.SCHOOL_CHANGE and decision.is_enforced:
        decision.is_enforced = False
        decision.save(update_fields=["is_enforced", "updated_at"])

    return appeal


def _assert_adult(decision: DisciplineDecision, on: date) -> None:
    """md. 169/3: öğrenci kendisi ancak 18 yaşını tamamlamışsa itiraz eder."""
    birth = decision.student.birth_date
    if birth is None:
        raise ValueError(
            "Öğrencinin doğum tarihi kayıtlı değil; 18 yaşını tamamladığı doğrulanamadı "
            "(md. 169/3). Önce öğrenci kartına doğum tarihini girin."
        )
    try:
        eighteenth = birth.replace(year=birth.year + 18)
    except ValueError:  # 29 Şubat doğumlu → 1 Mart
        eighteenth = date(birth.year + 18, 3, 1)
    if on < eighteenth:
        raise ValueError(
            "Öğrenci itiraz tarihinde 18 yaşını tamamlamamış; itirazı veli veya okul "
            "müdürü yapar (md. 169/3)."
        )


@transaction.atomic
def forward_appeal(appeal: DisciplineAppeal, *, forwarded_on: date) -> DisciplineAppeal:
    """İtirazın üst kurula sevkini kaydeder (md. 169/3 — en geç 5 iş günü)."""
    if appeal.result != AppealResult.PENDING:
        raise ValueError("Sonuçlanmış itirazın sevk tarihi değiştirilemez.")
    if forwarded_on < appeal.filed_on:
        raise ValueError("Sevk tarihi itiraz başvuru tarihinden önce olamaz.")
    appeal.forwarded_on = forwarded_on
    appeal.save(update_fields=["forwarded_on", "updated_at"])
    return appeal


@transaction.atomic
def resolve_appeal(
    appeal: DisciplineAppeal,
    *,
    result: str,
    resulted_on: date,
    result_notes: str = "",
    new_penalty_type: str = "",
    new_suspension_days: int | None = None,
) -> DisciplineAppeal:
    """İtiraz sonucunu kaydeder (md. 169/4 — sonuç kesindir).

    OVERTURNED (bozuldu) → ceza kaldırılır: karar REJECTED + uygulama kalkar;
    davranış puanı iadesi selector tarafında bozulmuş kararlar hariç tutularak
    sağlanır (md. 171).

    REDUCED (değiştirildi — md. 200/Ç, 202/1-c, 204/1-b) → `new_penalty_type`
    zorunludur; karar yeni cezaya güncellenir (puan md. 170'e göre yeniden
    türer), eski tür ve (uzaklaştırmaysa) eski gün sayısı itiraz kaydında
    (`previous_penalty_type`, `previous_suspension_days`) saklanır. Yeni ceza aynı
    türde de olabilir: uzaklaştırmanın yalnız gün sayısı değişmişse.

    Sonuç kesin olduğundan bir kez girilir; yeniden sonuçlandırılamaz.
    """
    if result not in set(AppealResult.values) or result == AppealResult.PENDING:
        raise ValueError("Geçersiz itiraz sonucu.")
    if appeal.result != AppealResult.PENDING:
        raise ValueError("İtiraz zaten sonuçlanmış; itiraz sonucu kesindir (md. 169/4).")
    if resulted_on < appeal.filed_on:
        raise ValueError("Sonuç tarihi itiraz başvuru tarihinden önce olamaz.")
    decision = appeal.decision
    if result == AppealResult.REDUCED:
        if not new_penalty_type:
            raise ValueError(
                "'Değiştirildi' sonucunda itiraz kurulunun verdiği yeni ceza seçilmelidir "
                "(davranış puanı buna göre yeniden hesaplanır — md. 170)."
            )
        appeal.previous_penalty_type = decision.penalty_type
        appeal.previous_suspension_days = decision.suspension_days
        changed = _apply_penalty_change(decision, new_penalty_type, new_suspension_days)
        decision.save(update_fields=[*changed, "updated_at"])
    appeal.result = result
    appeal.resulted_on = resulted_on
    appeal.result_notes = result_notes
    appeal.save(
        update_fields=[
            "result",
            "resulted_on",
            "result_notes",
            "previous_penalty_type",
            "previous_suspension_days",
            "updated_at",
        ]
    )

    if result == AppealResult.OVERTURNED:
        decision = appeal.decision
        decision.approval_status = DecisionApprovalStatus.REJECTED
        decision.is_enforced = False
        decision.save(update_fields=["approval_status", "is_enforced", "updated_at"])
    else:
        # Onandı/değiştirildi: md. 172/2-ç bekletmesi biter, (yeni) ceza uygulanır.
        decision = appeal.decision
        decision.is_enforced = _enforced_state(decision)
        decision.save(update_fields=["is_enforced", "updated_at"])

    return appeal


# Onaydan sonra okulca "uygulanan" cezalar (md. 172). Okul değiştirme de onayla
# uygulanır; yalnız süresinde itiraz edilmişse itiraz sonuçlanana dek uygulanmaz
# (md. 172/2-ç — kullanıcı kararı 27.09.2026).
_ENFORCEABLE_PENALTIES = (
    PenaltyType.REPRIMAND,
    PenaltyType.SHORT_TERM_SUSPENSION,
    PenaltyType.SCHOOL_CHANGE,
)


def _enforced_state(decision: DisciplineDecision) -> bool:
    if decision.approval_status != DecisionApprovalStatus.APPROVED:
        return False
    if decision.penalty_type not in _ENFORCEABLE_PENALTIES:
        return False
    if decision.penalty_type == PenaltyType.SCHOOL_CHANGE:
        return not decision.appeals.filter(
            within_deadline=True, result=AppealResult.PENDING
        ).exists()
    return True


# EK-1 anlatı + öğrenci-bağlam alanları — karar sonrası da (dosya kapanana dek)
# güncellenebilir (OYS decision_narrative ucu paritesi).
NARRATIVE_FIELDS: tuple[str, ...] = (
    "accused_statement_summary",
    "witness_statement_summary",
    "other_evidence",
    "mitigating_aggravating",
    "committee_opinion",
    "psychosocial_summary",
    "boarding_status",
    "academic_standing",
    "health_status",
    "family_economic_status",
    "lives_with_family",
    "parents_alive",
    "parents_biological",
    "studies_near_family",
    "upbringing_environment",
    "family_residence_area",
    "incident_place",
    "incident_date",
    "prior_penalties_summary",
)


@transaction.atomic
def update_decision_narrative(
    decision: DisciplineDecision,
    *,
    fields: dict[str, object],
    enforcement_start_date: object = _UNSET,
    student_birth_date: object = _UNSET,
) -> DisciplineDecision:
    """EK-1 anlatı/bağlam alanlarını günceller — dosya kapanana kadar serbest.

    Karar çekirdeği (`update_decision`) tebliğ/onay sonrası kilitliyken EK-1
    anlatısı kapanışa dek düzenlenebilir (OYS Tur 107 davranışı).

    - `enforcement_start_date` (md. 164/2): uygulama başlangıcı genelde
      kesinleşme SONRASI belli olur → post-hoc set/temizlenebilir (OYS Tur 102).
    - `student_birth_date`: karara değil öğrenci SİCİLİNE yazılır (EK-1'de doğum
      tarihi boş kalan e-Okul veli ihracı senaryosu — OYS Tur 220); None/verilmemiş
      sicile dokunmaz.
    - Kapalı-dosya kilidi OYS kodunda YOKTUR — model dokümantasyonundaki niyet
      ("dosya kapanana kadar güncellenir") burada bilinçli olarak koda döküldü.
    """
    if decision.case.closed_at is not None:
        raise ValueError("Dosya kapatılmış; EK-1 alanları artık güncellenemez.")
    changed: list[str] = []
    for name in NARRATIVE_FIELDS:
        if name in fields and getattr(decision, name) != fields[name]:
            setattr(decision, name, fields[name])
            changed.append(name)
    if (
        enforcement_start_date is not _UNSET
        and decision.enforcement_start_date != enforcement_start_date
    ):
        _validate_enforcement_start(
            decision.penalty_type,
            enforcement_start_date,  # type: ignore[arg-type]
            approved_at=decision.approved_at,
        )
        decision.enforcement_start_date = enforcement_start_date  # type: ignore[assignment]
        changed.append("enforcement_start_date")
    if changed:
        decision.save(update_fields=[*changed, "updated_at"])
    if student_birth_date is not _UNSET and student_birth_date is not None:
        from apps.okul.services import persons as okul_persons

        okul_persons.update_student(decision.student, birth_date=student_birth_date)
    return decision


@transaction.atomic
def recompile_prior_penalties(decision: DisciplineDecision) -> DisciplineDecision:
    """EK-1 "önceki cezalar" özetini güncel durumdan yeniden derler (S11c, 14.11.2026).

    Yalnız kullanıcının isteğiyle çalışır (otomatik yeniden derleme YOK): özet anlık
    kopyadır ve elle düzenlenmiş olabilir — yeniden derleme o düzenlemeyi SİLER, arayüz
    bunu onaylatır. Kopya ile birlikte derleme izi de yenilenir; böylece "özet güncel
    değil" uyarısı kalkar. Kapalı dosyada reddedilir: EK-1 kapanışın dayanağıdır
    (`update_decision_narrative` ile aynı kilit); orada uyarı yalnız bilgidir.
    """
    from apps.disiplin import selectors

    if decision.case.closed_at is not None:
        raise ValueError(
            "Dosya kapalı: EK-1 'önceki cezalar' özeti kapanışın dayanağıdır, yeniden "
            "derlenemez. Düzeltme gerekiyorsa önce dosyayı yeniden açın (aşama geri alma)."
        )
    decision.prior_penalties_summary = selectors.compile_prior_penalties(
        decision.student_id,
        exclude_case_id=decision.case_id,
        on=decision.decision_date,
        before=decision,
    )
    # İz karar no'suz imzadır: önceki karara sonradan numara atanması bayatlatmaz.
    decision.prior_penalties_compiled = selectors.compile_prior_penalties(
        decision.student_id,
        exclude_case_id=decision.case_id,
        on=decision.decision_date,
        before=decision,
        signature=True,
    )
    decision.save(
        update_fields=["prior_penalties_summary", "prior_penalties_compiled", "updated_at"]
    )
    return decision


@transaction.atomic
def remove_penalty(
    decision: DisciplineDecision, *, removed_on: date, note: str = ""
) -> DisciplineDecision:
    """md. 171/2: öğretmenler kurulunca cezanın kaldırılması + davranış puanı iadesi.

    Yalnız kesinleşmiş, yürürlükteki gerçek ceza kaldırılabilir. Kaldırılan ceza
    davranış puanından, triajdan ve EK-1 "önceki cezalar"dan düşer; md. 171/3
    gereği öğrencinin "disiplin cezası bulunmadığı" kabul edilir. Kaldırılan ceza
    e-Okul'dan 5 iş günü içinde çıkarılır (kullanıcıya hatırlatılır).
    """
    from apps.disiplin import selectors

    if decision.penalty_type == PenaltyType.NO_PENALTY:
        raise ValueError("'Ceza verilmesine yer olmadığı' kararında kaldırılacak ceza yok.")
    if decision.penalty_removed_on is not None:
        raise ValueError("Bu ceza zaten kaldırılmış.")
    final, reason = selectors.decision_is_final(decision)
    if not final:
        raise ValueError(f"Yalnız kesinleşmiş ceza kaldırılabilir: {reason}.")
    if removed_on < decision.decision_date:
        raise ValueError("Kaldırma tarihi karar tarihinden önce olamaz.")
    if removed_on > timezone.localdate():
        raise ValueError("Kaldırma tarihi gelecekte olamaz.")
    decision.penalty_removed_on = removed_on
    decision.penalty_removal_note = (note or "").strip()
    decision.save(update_fields=["penalty_removed_on", "penalty_removal_note", "updated_at"])
    return decision


@transaction.atomic
def undo_penalty_removal(decision: DisciplineDecision) -> DisciplineDecision:
    """Yanlışlıkla girilen md. 171/2 kaldırma kaydını geri alır (tek yönlü kapan olmasın)."""
    if decision.penalty_removed_on is None:
        raise ValueError("Bu cezada kaldırma kaydı yok.")
    decision.penalty_removed_on = None
    decision.penalty_removal_note = ""
    decision.save(update_fields=["penalty_removed_on", "penalty_removal_note", "updated_at"])
    return decision
