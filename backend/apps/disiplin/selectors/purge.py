"""md. 157/7 imha aracı — salt-okunur kapsam sorguları (tasarım §4.6).

**Mevzuat gerçeği.** Yazılı uyarı CEZA DEĞİLDİR (md. 157/7): öğrencinin siciline
işlenmez, e-Okul'a girilmez (md. 157/7-ç) ve md. 157/7-d uyarınca "sosyal
sorumluluk programı çalışmasına ilişkin belgeler hariç diğer belgeler DERS YILI
SONUNDA ya da öğrencinin NAKİL OLDUĞU TARİHTEN İTİBAREN 5 İŞ GÜNÜ içinde imha
edilir". Bu modül imha KAPSAMINI hesaplar; silme `services/purge.py`'dedir.

**Kırmızı çizgi.** KURUL KARARLI (Dal B) dosyalar aracın DIŞINDADIR — md. 163-170
cezaları resmî sicil kaydıdır, imha edilemez. Kapsam kararı burada tek yerde
verilir (`case_purge_blockers`); UI da, servis de aynı yüklemi kullanır.

Kapsam (tasarım §4.6):
  1. `DisciplineWarning` kayıtları,
  2. bunlara bağlı `WARNING_LETTER` türündeki `GeneratedDocument` kütük satırları,
  3. YALNIZ uyarıyla kapanmış Dal A dosyalarının tamamı.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from django.utils import timezone

from apps.disiplin.models import (
    CaseStage,
    DisciplineCase,
    DisciplineDecision,
    DisciplineEvent,
    DisciplineMeeting,
    DisciplinePrecaution,
    DisciplineWarning,
    DocumentType,
    GeneratedDocument,
    PrincipalDecision,
)

# --- Engel gerekçeleri (Türkçe; UI aynen gösterir) -------------------------
BLOCKER_NOT_CLOSED = (
    "Dosya kapatılmamış — md. 157/7 imhası yalnız kapanmış uyarı dosyaları içindir."
)
BLOCKER_NO_WARNING_DECISION = (
    "Dosya yazılı uyarı ile kapanmamış — md. 157/7 kapsamı dışında (müdür değerlendirmesi yok)."
)
BLOCKER_COMMITTEE_REFERRAL = "Dosya kurula sevk edilmiş (Dal B) — kurul dosyası imha edilemez."
BLOCKER_HAS_DECISION = "Dosyada kurul kararı var (Dal B) — resmî ceza kaydı imha edilemez."
BLOCKER_HAS_MEETING = "Dosyada kurul toplantısı kaydı var (Dal B) — imha edilemez."
BLOCKER_HAS_PRECAUTION = "Dosyada tedbir (md. 175) kaydı var (Dal B) — imha edilemez."

# Müdürün kurula sevk kararları — biri varsa dosya Dal B'dir.
_COMMITTEE_DECISIONS: frozenset[str] = frozenset(
    {PrincipalDecision.HONOR_COMMITTEE, PrincipalDecision.DISCIPLINE_COMMITTEE}
)


@dataclass(frozen=True)
class PurgeCaseItem:
    """İmha önizlemesinde bir dosyanın tam dökümü (neyin silineceği)."""

    case_id: int
    case_no: str
    petition_date: date
    closed_on: date | None
    students: tuple[str, ...]
    warning_count: int
    warning_letter_count: int
    document_count: int
    event_count: int
    attachment_count: int
    participant_count: int
    in_active_school_year: bool
    # md. 157/7-d zamanlaması (kullanıcı kararı 26.09.2026 — A: engelle). Boşsa imha
    # edilebilir; doluysa gerekçe (ders yılı henüz bitmedi).
    timing_blocker: str = ""


@dataclass(frozen=True)
class PurgeWarningItem:
    """Tekil (nakil) imhada bir müdür uyarısı satırı."""

    warning_id: int
    case_id: int
    case_no: str
    student_id: int
    student_name: str
    warning_date: date
    warning_letter_count: int
    whole_case_purgeable: bool


@dataclass(frozen=True)
class PurgeStudentItem:
    """İmha kapsamında uyarı izi bulunan bir öğrenci (tekil imha seçim listesi)."""

    student_id: int
    full_name: str
    class_label: str
    status: str
    warning_count: int


def _decided_events(case: DisciplineCase) -> list[DisciplineEvent]:
    """Dosyanın müdür değerlendirmesi (DECIDED) olayları — silinmişler DAHİL.

    Soft-delete edilmiş bir sevk olayı da Dal B kanıtıdır; bu yüzden `all_objects`.
    """
    return list(DisciplineEvent.all_objects.filter(case_id=case.pk, stage=CaseStage.DECIDED))


def case_timing_blocker(case: DisciplineCase, *, today: date | None = None) -> str:
    """md. 157/7-d: toplu imha "ders yılı SONUNDA" yapılır (kullanıcı kararı A).

    Dosyanın ders yılı (dilekçe tarihinden önce başlayan en son `SchoolYear`)
    `today` itibarıyla bitmemişse gerekçe döner; bitmişse veya yıl bulunamazsa "".
    Ders yılı içinde nakil eden öğrencinin izleri tekil (nakil) imhayla silinir.
    """
    from django.utils import timezone

    from apps.okul.models import SchoolYear

    reference = today or timezone.localdate()
    year = (
        SchoolYear.objects.filter(start_date__lte=case.petition_date)
        .order_by("-start_date")
        .first()
    )
    if year is None or year.end_date < reference:
        return ""
    return (
        f"Dosyanın ders yılı ({year.name}) henüz bitmedi (bitiş "
        f"{year.end_date:%d.%m.%Y}) — md. 157/7-d imha ders yılı sonunda yapılır; nakil "
        f"eden öğrenci için tekil (nakil) imhayı kullanın."
    )


def student_timing_blocker(
    student_id: int, case_ids: list[int], *, today: date | None = None
) -> str:
    """Tekil (nakil) imha zamanlaması (md. 157/7-d, kullanıcı kararı A).

    Öğrenci sicilde "Ayrıldı" (nakil) ise serbest; değilse yalnız ilgili tüm
    dosyaların ders yılı bitmişse serbest. Aksi hâlde gerekçe döner.
    """
    from apps.okul.models import Student, StudentStatus

    student = Student.objects.filter(pk=student_id).first()
    if student is not None and student.status == StudentStatus.LEFT:
        return ""
    for case in DisciplineCase.objects.filter(pk__in=case_ids):
        if case_timing_blocker(case, today=today):
            return (
                'Öğrenci sicilde "Ayrıldı" (nakil) olarak işaretli değil ve ders yılı '
                "bitmedi — md. 157/7-d imha ders yılı sonunda ya da nakilden itibaren 5 iş "
                "günü içinde yapılır. Nakil ettiyse önce öğrenci kartında durumu güncelleyin."
            )
    return ""


def case_purge_blockers(case: DisciplineCase) -> list[str]:
    """Dosyanın md. 157/7 imha kapsamına girmesini engelleyen gerekçeler.

    Boş liste → dosya imha edilebilir (Dal A, yalnız yazılı uyarıyla kapanmış).
    Tüm sorgular `all_objects` üzerinden koşar: çöp kutusundaki bir kurul kararı
    da dosyayı Dal B yapar (silinmiş kayıt kapsamı GENİŞLETMEZ).
    """
    blockers: list[str] = []

    if case.current_stage != CaseStage.CLOSED or case.closed_at is None:
        blockers.append(BLOCKER_NOT_CLOSED)

    decided = _decided_events(case)
    warning_only = [
        e
        for e in decided
        if isinstance(e.principal_decisions, list)
        and e.principal_decisions == [PrincipalDecision.WRITTEN_WARNING]
    ]
    referred = [
        e
        for e in decided
        if isinstance(e.principal_decisions, list)
        and _COMMITTEE_DECISIONS.intersection(e.principal_decisions)
    ]
    if referred:
        blockers.append(BLOCKER_COMMITTEE_REFERRAL)
    elif not warning_only:
        blockers.append(BLOCKER_NO_WARNING_DECISION)

    if DisciplineEvent.all_objects.filter(case_id=case.pk, stage=CaseStage.COMMITTEE_DONE).exists():
        blockers.append(BLOCKER_COMMITTEE_REFERRAL)
    if DisciplineDecision.all_objects.filter(case_id=case.pk).exists():
        blockers.append(BLOCKER_HAS_DECISION)
    if DisciplineMeeting.all_objects.filter(case_id=case.pk).exists():
        blockers.append(BLOCKER_HAS_MEETING)
    if DisciplinePrecaution.all_objects.filter(case_id=case.pk).exists():
        blockers.append(BLOCKER_HAS_PRECAUTION)

    # Aynı gerekçe iki yoldan gelebilir (sevk olayı + COMMITTEE_DONE) — tekilleştir.
    return list(dict.fromkeys(blockers))


def is_purgeable_case(case: DisciplineCase) -> bool:
    """Dosya md. 157/7 imha kapsamında mı (Dal A, uyarıyla kapanmış)?"""
    return not case_purge_blockers(case)


def purgeable_cases() -> list[DisciplineCase]:
    """İmha kapsamındaki (canlı) dosyalar — dosya no sırasıyla."""
    candidates = (
        DisciplineCase.objects.filter(current_stage=CaseStage.CLOSED, closed_at__isnull=False)
        .prefetch_related("case_students__student")
        .order_by("case_no")
    )
    return [case for case in candidates if is_purgeable_case(case)]


def _active_year_range() -> tuple[date, date] | None:
    """Aktif ders yılının tarih aralığı — yoksa None (md. 157/7-d 'ders yılı sonu')."""
    from apps.okul import selectors as okul_selectors

    year = okul_selectors.active_school_year()
    if year is None:
        return None
    return year.start_date, year.end_date


def case_purge_item(
    case: DisciplineCase, *, active_range: tuple[date, date] | None = None
) -> PurgeCaseItem:
    """Bir dosyanın imha önizleme satırı (sayımlar silinmişleri DE kapsar).

    `in_active_school_year`: dosyanın dilekçe tarihi aktif ders yılına düşüyorsa
    işaretlenir. `timing_blocker`: ders yılı bitmemişse toplu imha ENGELLENİR
    (md. 157/7-d; kullanıcı kararı 26.09.2026 — önceki "yalnız rozet" davranışı
    değişti).
    """
    docs = GeneratedDocument.all_objects.filter(case_id=case.pk)
    in_active = False
    if active_range is not None:
        start, end = active_range
        in_active = start <= case.petition_date <= end
    return PurgeCaseItem(
        case_id=case.pk,
        case_no=case.case_no,
        petition_date=case.petition_date,
        # §7.1: UTC'den .date() gece 00:00-02:59 kapanışı bir gün geri kaydırır.
        closed_on=timezone.localdate(case.closed_at) if case.closed_at is not None else None,
        students=tuple(
            link.student.full_name or f"#{link.student_id}" for link in case.case_students.all()
        ),
        warning_count=DisciplineWarning.all_objects.filter(case_id=case.pk).count(),
        warning_letter_count=docs.filter(document_type=DocumentType.WARNING_LETTER).count(),
        document_count=docs.count(),
        event_count=DisciplineEvent.all_objects.filter(case_id=case.pk).count(),
        attachment_count=case.attachments.count(),
        participant_count=case.participants.count(),
        in_active_school_year=in_active,
        timing_blocker=case_timing_blocker(case),
    )


def purgeable_case_items() -> list[PurgeCaseItem]:
    """İmha kapsamındaki tüm dosyaların önizleme satırları."""
    active_range = _active_year_range()
    return [case_purge_item(case, active_range=active_range) for case in purgeable_cases()]


def warning_letter_documents(
    *, case_id: int, student_id: int | None = None
) -> list[GeneratedDocument]:
    """Değerlendirme formu (Form-01), uyarı yazısı (Form-02) ve veli görüşmesi (md.
    157/7-b) kütük satırları —
    silinmişler dahil. md. 157/7-d: "yazılı uyarı ile veli görüşmesine ilişkin"
    belgeler birlikte imha edilir.

    `student_id` verilirse yalnız o öğrenciye ait satırlar (tekil/nakil imhası).
    """
    qs = GeneratedDocument.all_objects.filter(
        case_id=case_id,
        document_type__in=[
            DocumentType.GUIDANCE_ASSESSMENT,
            DocumentType.WARNING_LETTER,
            DocumentType.PARENT_MEETING,
        ],
    )
    if student_id is not None:
        qs = qs.filter(student_id=student_id)
    return list(qs)


def student_warning_items(student_id: int) -> list[PurgeWarningItem]:
    """Bir öğrencinin imha edilebilir müdür uyarısı izleri (nakil senaryosu).

    Uyarı hangi dosyada olursa olsun listelenir; ANCAK dosyası Dal B ise (kurul
    kararlı) o dosyanın izlerine DOKUNULMAZ — bu yüzden Dal B uyarıları
    listelenmez. `whole_case_purgeable`: dosyanın tek öğrencisi bu öğrenciyse ve
    dosya kapsamdaysa dosyanın TAMAMI imha edilir.
    """
    items: list[PurgeWarningItem] = []
    warnings = (
        DisciplineWarning.objects.filter(student_id=student_id)
        .select_related("case", "student")
        .order_by("warning_date", "pk")
    )
    for warning in warnings:
        case = warning.case
        if not is_purgeable_case(case):
            continue
        only_student = list(case.case_students.values_list("student_id", flat=True)) == [student_id]
        items.append(
            PurgeWarningItem(
                warning_id=warning.pk,
                case_id=case.pk,
                case_no=case.case_no,
                student_id=student_id,
                student_name=warning.student.full_name or f"#{student_id}",
                warning_date=warning.warning_date,
                warning_letter_count=len(
                    warning_letter_documents(case_id=case.pk, student_id=student_id)
                ),
                whole_case_purgeable=only_student,
            )
        )
    return items


def students_with_purgeable_warnings() -> list[PurgeStudentItem]:
    """İmha kapsamında uyarı izi bulunan öğrenciler (tekil imha seçim listesi)."""
    case_ids = [case.pk for case in purgeable_cases()]
    warnings = (
        DisciplineWarning.objects.filter(case_id__in=case_ids)
        .select_related("student")
        .order_by("student__first_name", "student__last_name")
    )
    counts: dict[int, PurgeStudentItem] = {}
    for warning in warnings:
        student = warning.student
        current = counts.get(student.pk)
        counts[student.pk] = PurgeStudentItem(
            student_id=student.pk,
            full_name=student.full_name or f"#{student.pk}",
            class_label=student.class_label,
            status=student.status,
            warning_count=(current.warning_count if current else 0) + 1,
        )
    return list(counts.values())
