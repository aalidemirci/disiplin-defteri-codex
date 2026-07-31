"""md. 157/7 imha aracı — önizleme, tutanak, iki aşamalı onay, hard delete.

Tasarım §4.6. Mevzuat (docs/mevzuat/ortaogretim-yonetmeligi-disiplin-md157-206.md):

  md. 157/7-d — "Sosyal sorumluluk programı çalışmasına ilişkin belgeler hariç
  diğer belgeler DERS YILI SONUNDA ya da öğrencinin NAKİL OLDUĞU TARİHTEN
  İTİBAREN 5 İŞ GÜNÜ içinde imha edilir."

Yazılı uyarı CEZA DEĞİLDİR (md. 157/7) ve sicile işlenmez — imha edilebilmesinin
mevzuat gerekçesi budur. KURUL KARARLI (Dal B) dosyalar aracın DIŞINDADIR;
kapsam yüklemi tek yerdedir (`selectors.purge.case_purge_blockers`).

**Silme bilinçli bir hard delete'tir** — `shared/models.py` soft-delete kuralının
md. 157/7 istisnası. Bu yüzden akış üç adımlıdır ve kısayolu yoktur:

  1. `preview()` / `preview_student()` — neyin silineceğinin tam dökümü.
  2. `issue_record(..., confirmed=True)` — BİRİNCİ onay; imha tutanağı PDF'i
     üretilir, diske yazılır ve kapsamı bağlayan imzalı bir jeton döner.
  3. `execute(token=..., confirmed=True)` — İKİNCİ onay; jeton doğrulanır,
     kapsam YENİDEN doğrulanır (arada Dal B'ye dönmüş dosya reddedilir) ve
     kayıtlar silinir. Jetonsuz/onaysız çağrı `ValueError` yükseltir.

Silme sırası (tasarım §4.6): önce evrak kütüğü → ekler (disk dosyaları dahil) →
olaylar → uyarılar → katılımcılar → dosya-öğrenci bağı → dosya. Öğrenci sicili
PROTECT'tir ve ASLA silinmez.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from django.core import signing
from django.db import transaction
from django.utils import timezone

from apps.disiplin import file_storage, purge_documents
from apps.disiplin.models import (
    DisciplineAttachment,
    DisciplineCase,
    DisciplineCaseStudent,
    DisciplineEvent,
    DisciplineParticipant,
    DisciplineWarning,
    GeneratedDocument,
)
from apps.disiplin.purge_documents import PurgeRecordRow
from apps.disiplin.selectors import purge as purge_selectors
from shared.models import SoftDeleteQuerySet
from shared.working_days import add_working_days

# md. 157/7-d: nakil tarihinden itibaren 5 İŞ GÜNÜ içinde imha. (Mevzuat süresi;
# `discipline_periods` tablosundaki disiplin süreleriyle karıştırılmamalı — o
# modül kurul/itiraz süreleridir, bu bent uyarı belgelerinin imhasını düzenler.)
PURGE_AFTER_TRANSFER_WORKING_DAYS = 5

# Tutanak jetonu: imzalı, süreli (1 saat). Jeton TUTANAK ÜRETİLDİĞİNDE doğar —
# ikinci onayın "tutanaktan sonra" geldiğinin kanıtı budur.
_SIGNING_NAMESPACE = "disiplin.purge.record"
TOKEN_MAX_AGE_SECONDS = 3600

SCOPE_ALL = "TOPLU"
SCOPE_STUDENT = "OGRENCI"

_MISSING_RECORD_MESSAGE = (
    "İmha tutanağı üretilmeden imha yapılamaz. Önce tutanağı üretip indirin, "
    "sonra ikinci onayı verin (md. 157/7-d)."
)


# ---------------------------------------------------------------------------
# Önizleme çıktıları
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class PurgePreview:
    """Ders yılı sonu (toplu) imha önizlemesi."""

    cases: list[purge_selectors.PurgeCaseItem]
    students: list[purge_selectors.PurgeStudentItem]
    totals: dict[str, int]
    active_school_year_name: str = ""
    active_school_year_end: date | None = None


@dataclass(frozen=True)
class StudentPurgePreview:
    """Tekil (nakil) imha önizlemesi + md. 157/7-d "+5 iş günü" göstergesi."""

    student_id: int
    student_name: str
    class_label: str
    warnings: list[purge_selectors.PurgeWarningItem]
    whole_case_ids: list[int]
    totals: dict[str, int]
    transfer_date: date | None = None
    purge_deadline: date | None = None
    working_days_left: int | None = None
    overdue: bool = False


@dataclass(frozen=True)
class PurgeRecord:
    """Üretilmiş imha tutanağı — PDF + kalıcı yol + ikinci onayı açan jeton."""

    pdf_bytes: bytes
    filename: str
    stored_path: str
    token: str
    scope_label: str


@dataclass(frozen=True)
class PurgeResult:
    """İmha sonucu — silinen kayıt sayıları + tutanağın kalıcı yolu."""

    purged_cases: int = 0
    purged_warnings: int = 0
    purged_documents: int = 0
    purged_events: int = 0
    purged_attachments: int = 0
    purged_participants: int = 0
    record_path: str = ""
    case_numbers: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Önizleme
# ---------------------------------------------------------------------------
def preview() -> PurgePreview:
    """Ders yılı sonu imhası: kapsamdaki tüm Dal A dosyaları + uyarılı öğrenciler."""
    from apps.okul import selectors as okul_selectors

    cases = purge_selectors.purgeable_case_items()
    students = purge_selectors.students_with_purgeable_warnings()
    year = okul_selectors.active_school_year()
    return PurgePreview(
        cases=cases,
        students=students,
        totals={
            "cases": len(cases),
            "warnings": sum(c.warning_count for c in cases),
            "documents": sum(c.document_count for c in cases),
            "attachments": sum(c.attachment_count for c in cases),
        },
        active_school_year_name=year.name if year is not None else "",
        active_school_year_end=year.end_date if year is not None else None,
    )


def transfer_purge_deadline(transfer_date: date) -> date:
    """md. 157/7-d: nakil tarihi + 5 iş günü (resmî tatiller yerel takvimden)."""
    from apps.okul.services import calendar as okul_calendar

    return add_working_days(
        transfer_date,
        PURGE_AFTER_TRANSFER_WORKING_DAYS,
        is_working_day=okul_calendar.is_working_day,
    )


def _working_days_between(start: date, end: date) -> int:
    """`start` ile `end` arasındaki iş günü sayısı (negatifse 0 — geçmiş gün)."""
    from apps.okul.services import calendar as okul_calendar

    if end <= start:
        return 0
    count = 0
    cursor = start
    while cursor < end:
        cursor = add_working_days(cursor, 1, is_working_day=okul_calendar.is_working_day)
        count += 1
    return count


def preview_student(
    student_id: int,
    *,
    transfer_date: date | None = None,
    today: date | None = None,
) -> StudentPurgePreview:
    """Nakil eden öğrencinin imha önizlemesi + "+5 iş günü" göstergesi.

    `transfer_date` verilirse md. 157/7-d son günü hesaplanır; verilmezse gösterge
    boş kalır (nakil tarihi öğrenci sicilinde tutulmuyor — kullanıcı girer).
    """
    from apps.okul import selectors as okul_selectors

    student = okul_selectors.get_student(student_id)
    if student is None:
        raise ValueError("Öğrenci bulunamadı.")

    warnings = purge_selectors.student_warning_items(student_id)
    whole_case_ids = sorted({w.case_id for w in warnings if w.whole_case_purgeable})

    deadline: date | None = None
    days_left: int | None = None
    overdue = False
    if transfer_date is not None:
        deadline = transfer_purge_deadline(transfer_date)
        reference = today or timezone.localdate()
        overdue = reference > deadline
        days_left = 0 if overdue else _working_days_between(reference, deadline)

    return StudentPurgePreview(
        student_id=student_id,
        student_name=student.full_name or f"#{student_id}",
        class_label=student.class_label,
        warnings=warnings,
        whole_case_ids=whole_case_ids,
        totals={
            "warnings": len(warnings),
            "documents": sum(w.warning_letter_count for w in warnings),
            "cases": len(whole_case_ids),
        },
        transfer_date=transfer_date,
        purge_deadline=deadline,
        working_days_left=days_left,
        overdue=overdue,
    )


# ---------------------------------------------------------------------------
# Kapsam çözümleme + doğrulama
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class _Scope:
    """Doğrulanmış imha kapsamı — jetona yazılan ve silmede uygulanan küme."""

    kind: str
    case_ids: list[int]  # bütünüyle silinecek dosyalar
    warning_ids: list[int]  # dosyası silinmeyen tekil uyarılar
    document_ids: list[int]  # tekil uyarılara bağlı WARNING_LETTER kütük satırları
    student_id: int | None = None
    transfer_date: date | None = None


def _resolve_case_scope(case_ids: list[int]) -> _Scope:
    """Toplu (ders yılı sonu) kapsamı: verilen dosyaların HEPSİ Dal A olmalıdır."""
    unique = sorted(dict.fromkeys(case_ids))
    if not unique:
        raise ValueError("İmha edilecek kayıt seçilmedi.")
    for case_id in unique:
        case = DisciplineCase.objects.filter(pk=case_id).first()
        if case is None:
            raise ValueError(f"Disiplin dosyası bulunamadı (#{case_id}).")
        blockers = purge_selectors.case_purge_blockers(case)
        if blockers:
            raise ValueError(f"{case.case_no}: {blockers[0]}")
    return _Scope(kind=SCOPE_ALL, case_ids=unique, warning_ids=[], document_ids=[])


def _resolve_student_scope(student_id: int, transfer_date: date | None) -> _Scope:
    """Tekil (nakil) kapsam: tek öğrencili Dal A dosyaları + kalan uyarı izleri."""
    preview = preview_student(student_id, transfer_date=transfer_date)
    if not preview.warnings:
        raise ValueError("Bu öğrenci için imha edilecek uyarı kaydı yok.")

    whole = set(preview.whole_case_ids)
    warning_ids = sorted(w.warning_id for w in preview.warnings if w.case_id not in whole)
    document_ids: list[int] = []
    for item in preview.warnings:
        if item.case_id in whole:
            continue
        document_ids.extend(
            doc.pk
            for doc in purge_selectors.warning_letter_documents(
                case_id=item.case_id, student_id=student_id
            )
        )
    return _Scope(
        kind=SCOPE_STUDENT,
        case_ids=sorted(whole),
        warning_ids=warning_ids,
        document_ids=sorted(dict.fromkeys(document_ids)),
        student_id=student_id,
        transfer_date=transfer_date,
    )


def _revalidate(scope: _Scope) -> None:
    """Jeton üretildikten SONRA kapsamın hâlâ geçerli olduğunu doğrular.

    Arada dosyaya kurul kararı işlenmişse (Dal B'ye dönmüşse) imha REDDEDİLİR —
    jeton "o an geçerliydi" demektir, "her zaman geçerli" değil.
    """
    for case_id in scope.case_ids:
        case = DisciplineCase.objects.filter(pk=case_id).first()
        if case is None:
            raise ValueError("İmha kapsamı değişti; önizlemeyi ve tutanağı yenileyin.")
        blockers = purge_selectors.case_purge_blockers(case)
        if blockers:
            raise ValueError(f"İmha kapsamı değişti — {case.case_no}: {blockers[0]}")
    for warning_id in scope.warning_ids:
        warning = DisciplineWarning.objects.filter(pk=warning_id).select_related("case").first()
        if warning is None:
            raise ValueError("İmha kapsamı değişti; önizlemeyi ve tutanağı yenileyin.")
        blockers = purge_selectors.case_purge_blockers(warning.case)
        if blockers:
            raise ValueError(f"İmha kapsamı değişti — {warning.case.case_no}: {blockers[0]}")


# ---------------------------------------------------------------------------
# Jeton (birinci onay → ikinci onay köprüsü)
# ---------------------------------------------------------------------------
def _dump_token(scope: _Scope, *, record_path: str) -> str:
    payload: dict[str, Any] = {
        "kind": scope.kind,
        "cases": scope.case_ids,
        "warnings": scope.warning_ids,
        "documents": scope.document_ids,
        "student": scope.student_id,
        "record": record_path,
    }
    return signing.dumps(payload, salt=_SIGNING_NAMESPACE)


def _load_token(token: str) -> tuple[_Scope, str]:
    if not (token or "").strip():
        raise ValueError(_MISSING_RECORD_MESSAGE)
    try:
        payload = signing.loads(token, salt=_SIGNING_NAMESPACE, max_age=TOKEN_MAX_AGE_SECONDS)
    except signing.SignatureExpired as exc:
        raise ValueError("İmha tutanağının geçerlilik süresi doldu; tutanağı yenileyin.") from exc
    except signing.BadSignature as exc:
        raise ValueError(_MISSING_RECORD_MESSAGE) from exc
    if not isinstance(payload, dict):
        raise ValueError(_MISSING_RECORD_MESSAGE)
    scope = _Scope(
        kind=str(payload.get("kind", SCOPE_ALL)),
        case_ids=[int(i) for i in payload.get("cases", [])],
        warning_ids=[int(i) for i in payload.get("warnings", [])],
        document_ids=[int(i) for i in payload.get("documents", [])],
        student_id=payload.get("student"),
    )
    return scope, str(payload.get("record", ""))


# ---------------------------------------------------------------------------
# Tutanak üretimi (BİRİNCİ onay)
# ---------------------------------------------------------------------------
def _case_rows(case_ids: list[int]) -> list[PurgeRecordRow]:
    """Dosya bazlı tutanak satırları — dosyadaki her öğrenci için bir satır."""
    rows: list[PurgeRecordRow] = []
    for case_id in case_ids:
        case = DisciplineCase.objects.filter(pk=case_id).first()
        if case is None:
            continue
        doc_count = GeneratedDocument.all_objects.filter(case_id=case_id).count()
        for link in case.case_students.select_related("student").all():
            student_warnings = DisciplineWarning.all_objects.filter(
                case_id=case_id, student_id=link.student_id
            ).order_by("warning_date")
            first = student_warnings.first()
            details = [f"{student_warnings.count()} uyarı kaydı"] if first is not None else []
            details.append(f"{doc_count} evrak kütük satırı")
            details.append("dosyanın tamamı")
            rows.append(
                PurgeRecordRow(
                    student_name=link.student.full_name or f"#{link.student_id}",
                    case_no=case.case_no,
                    record_date=first.warning_date if first is not None else case.petition_date,
                    detail=" · ".join(details),
                )
            )
    return rows


def _warning_rows(warning_ids: list[int]) -> list[PurgeRecordRow]:
    """Tekil uyarı satırları (dosyası ayakta kalan uyarılar)."""
    rows: list[PurgeRecordRow] = []
    warnings = (
        DisciplineWarning.all_objects.filter(pk__in=warning_ids)
        .select_related("case", "student")
        .order_by("warning_date", "pk")
    )
    for warning in warnings:
        docs = purge_selectors.warning_letter_documents(
            case_id=warning.case_id, student_id=warning.student_id
        )
        rows.append(
            PurgeRecordRow(
                student_name=warning.student.full_name or f"#{warning.student_id}",
                case_no=warning.case.case_no,
                record_date=warning.warning_date,
                detail=f"1 uyarı kaydı · {len(docs)} uyarı yazısı kütük satırı",
            )
        )
    return rows


def _scope_totals(scope: _Scope) -> dict[str, int]:
    warnings = DisciplineWarning.all_objects.filter(case_id__in=scope.case_ids).count() + len(
        scope.warning_ids
    )
    documents = GeneratedDocument.all_objects.filter(case_id__in=scope.case_ids).count() + len(
        scope.document_ids
    )
    return {"cases": len(scope.case_ids), "warnings": warnings, "documents": documents}


def issue_record(
    *,
    case_ids: list[int] | None = None,
    student_id: int | None = None,
    transfer_date: date | None = None,
    purge_date: date | None = None,
    confirmed: bool = False,
) -> PurgeRecord:
    """BİRİNCİ onay: imha tutanağı PDF'ini üretir, diske yazar ve jeton döner.

    `student_id` verilirse tekil (nakil) imhası, aksi hâlde `case_ids` ile toplu
    (ders yılı sonu) imhası. Kapsam burada doğrulanır — Dal B dosyası içeren
    istek `ValueError` ile reddedilir (silme AŞAMASINA HİÇ GELMEZ).
    """
    if not confirmed:
        raise ValueError("İmha önizlemesi onaylanmadan tutanak üretilemez (birinci onay).")

    if student_id is not None:
        scope = _resolve_student_scope(student_id, transfer_date)
        preview = preview_student(student_id, transfer_date=transfer_date)
        scope_label = f"Nakil — {preview.student_name}"
        deadline = preview.purge_deadline
    else:
        scope = _resolve_case_scope(list(case_ids or []))
        scope_label = "Ders yılı sonu toplu imhası"
        deadline = None

    rows = _case_rows(scope.case_ids) + _warning_rows(scope.warning_ids)
    on = purge_date or timezone.localdate()
    pdf_bytes = purge_documents.render_purge_record(
        rows=rows,
        totals=_scope_totals(scope),
        purge_date=on,
        scope_label=scope_label,
        transfer_date=scope.transfer_date,
        purge_deadline=deadline,
    )
    filename = purge_documents.record_filename(on)
    stored_path = purge_documents.store_purge_record(pdf_bytes, filename=filename)
    return PurgeRecord(
        pdf_bytes=pdf_bytes,
        filename=filename,
        stored_path=stored_path,
        token=_dump_token(scope, record_path=stored_path),
        scope_label=scope_label,
    )


# ---------------------------------------------------------------------------
# İmha (İKİNCİ onay) — hard delete
# ---------------------------------------------------------------------------
def _delete_attachment_files(case_id: int) -> int:
    """Dosya eklerinin DİSK kopyalarını siler; silinen dosya sayısını döner."""
    removed = 0
    for attachment in DisciplineAttachment.all_objects.filter(case_id=case_id):
        path = file_storage.absolute_path(attachment.file_path)
        try:
            path.unlink()
            removed += 1
        except FileNotFoundError:
            removed += 1  # kayıt var, dosya yok — kütük yine silinecek
        except OSError:
            # Dosya kilitli/erişilemez: kayıt silinir, dosya artığı kalır (loglanmaz —
            # tek kullanıcılı program; kullanıcıya sonuç özetinde sayı olarak döner).
            pass
    parent = file_storage.absolute_path(f"discipline/case_{case_id}")
    try:
        parent.rmdir()
    except OSError:
        pass
    return removed


def _hard_delete(queryset: Any) -> int:
    """`SoftDeleteQuerySet.hard_delete()` — silinen satır sayısını döner.

    `all_objects` yöneticisinin queryset'i django-stubs tarafından düz
    `QuerySet` olarak tiplenir; `hard_delete` sözleşmesi (shared/models.py)
    burada TEK yerde kapsüllenir — çağrı yerleri `# type: ignore` taşımaz.
    """
    typed: SoftDeleteQuerySet = queryset
    count = typed.count()
    typed.hard_delete()
    return count


def _purge_case(case: DisciplineCase, result: dict[str, int]) -> None:
    """Bir Dal A dosyasını bütünüyle imha eder (tasarım §4.6 sırasıyla).

    Sıra: evrak kütüğü → ekler (disk + kayıt) → olaylar → uyarılar → katılımcılar
    → dosya-öğrenci bağı → dosya. Öğrenci PROTECT — silinmez.
    """
    case_id = case.pk
    result["documents"] += _hard_delete(GeneratedDocument.all_objects.filter(case_id=case_id))

    result["attachments"] += _delete_attachment_files(case_id)
    _hard_delete(DisciplineAttachment.all_objects.filter(case_id=case_id))

    result["events"] += _hard_delete(DisciplineEvent.all_objects.filter(case_id=case_id))
    result["warnings"] += _hard_delete(DisciplineWarning.all_objects.filter(case_id=case_id))
    result["participants"] += _hard_delete(
        DisciplineParticipant.all_objects.filter(case_id=case_id)
    )

    DisciplineCaseStudent.objects.filter(case_id=case_id).delete()

    case.hard_delete()
    result["cases"] += 1


@transaction.atomic
def execute(*, token: str, confirmed: bool = False) -> PurgeResult:
    """İKİNCİ onay: jetonu doğrular, kapsamı yeniden doğrular ve kayıtları SİLER.

    Geri alınamaz — `hard_delete()` soft-delete kuralının md. 157/7 istisnasıdır.
    Silinen kayıtların tek izi, jetonun işaret ettiği imha tutanağıdır.
    """
    scope, record_path = _load_token(token)
    if not confirmed:
        raise ValueError("İmha ikinci onay olmadan uygulanamaz.")
    _revalidate(scope)

    counters = {
        "cases": 0,
        "warnings": 0,
        "documents": 0,
        "events": 0,
        "attachments": 0,
        "participants": 0,
    }
    case_numbers: list[str] = []

    # 1) Bütünüyle silinen Dal A dosyaları.
    for case_id in scope.case_ids:
        case = DisciplineCase.objects.filter(pk=case_id).first()
        if case is None:
            continue
        case_numbers.append(case.case_no)
        _purge_case(case, counters)

    # 2) Dosyası ayakta kalan tekil izler (çok öğrencili dosyada nakil senaryosu):
    #    önce uyarı yazısı kütük satırları, sonra uyarı kayıtları.
    if scope.document_ids:
        counters["documents"] += _hard_delete(
            GeneratedDocument.all_objects.filter(pk__in=scope.document_ids)
        )
    if scope.warning_ids:
        counters["warnings"] += _hard_delete(
            DisciplineWarning.all_objects.filter(pk__in=scope.warning_ids)
        )

    return PurgeResult(
        purged_cases=counters["cases"],
        purged_warnings=counters["warnings"],
        purged_documents=counters["documents"],
        purged_events=counters["events"],
        purged_attachments=counters["attachments"],
        purged_participants=counters["participants"],
        record_path=record_path,
        case_numbers=case_numbers,
    )
