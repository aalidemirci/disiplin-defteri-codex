"""Öğrenci/Personel toplu içe aktarma — preview (dry-run) + commit (F1-T5).

OYS `core.services.imports`'tan DÜZLEŞTİRİLMİŞ hedefe uyarlama (tasarım §4.7):
transaction sınırı burasıdır; parser'lar saf (DB'siz) çalışır, eşleştirme/yazma
burada. OYS'den farklar:

- Enrollment/NameHistory/Parent/Link zinciri YOK → `Student` satır içi alanlara
  yazılır (sorumlu veli → `guardian_*`; diğer velinin telefonu → `guardian_phone2`).
- xlsx ve pano yapıştırması AYNI boru hattı: her girişten önce `rows` matrisi
  üretilir (`read_sheet` / `text_to_grid`), gerisi ortak.
- Idempotency UYARIDIR, ENGEL DEĞİL: aynı içerik (sha256) yeniden commit
  edilebilir (güncelleme meşru) — `already_imported=True` uyarısıyla MEVCUT
  COMPLETED `ImportRun` satırı güncellenir (koşullu unique bozulmaz).
- Önizleme deseni AYNEN: gerçek ingest atomic blokta koşulur ve
  `set_rollback(True)` ile geri alınır — ayrı hesaplayıcı YOK, %100 sonuç
  paritesi; ardından kalıcı PREVIEWED izi yazılır. Ingest zincirine
  `transaction.on_commit` hook'u EKLENEMEZ (rollback yan etki sızdırır).
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any
from zipfile import BadZipFile

from django.db import transaction
from django.utils import timezone
from openpyxl.utils.exceptions import InvalidFileException

from apps.okul import excel_personel, excel_veli, normalize, selectors
from apps.okul.excel_personel import ParsedPersonnelRow, PersonnelColumnMapping
from apps.okul.excel_veli import ColumnMapping, ParsedParent, ParsedRow, ParserError
from apps.okul.models import (
    ClassResponsibility,
    GuardianKinship,
    ImportRun,
    ImportSourceType,
    ImportStatus,
    Personnel,
    SchoolYear,
    Student,
    StudentStatus,
)
from apps.okul.services.templates import (
    PERSONNEL_TEMPLATE_EXAMPLE,
    PERSONNEL_TEMPLATE_HEADERS,
    STUDENT_TEMPLATE_EXAMPLE,
    STUDENT_TEMPLATE_HEADERS,
)
from shared.text import mask_tckn


@dataclass
class ImportIssue:
    """İçe aktarmada bir satır sorunu (atlama veya uyarı)."""

    row_number: int
    field: str
    issue: str
    raw_value: str = ""


@dataclass
class StudentImportReport:
    """Öğrenci içe aktarma özeti (UI raporu + ImportRun.report JSON'ı)."""

    file_hash: str
    file_name: str = ""
    total_rows: int = 0
    processed: int = 0
    created_students: int = 0
    updated_students: int = 0
    unchanged_students: int = 0
    already_imported: bool = False
    dry_run: bool = False
    warnings: list[ImportIssue] = field(default_factory=list)
    skipped: list[ImportIssue] = field(default_factory=list)

    def add_warning(self, row: int, field_name: str, issue: str, raw: str = "") -> None:
        self.warnings.append(ImportIssue(row, field_name, issue, raw))

    def add_skip(self, row: int, field_name: str, issue: str, raw: str = "") -> None:
        self.skipped.append(ImportIssue(row, field_name, issue, raw))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def summary_tr(self) -> str:
        return (
            f"İçe aktarma: {self.processed}/{self.total_rows} satır işlendi — "
            f"{self.created_students} yeni, {self.updated_students} güncellenen, "
            f"{self.unchanged_students} değişmeyen öğrenci; "
            f"{len(self.warnings)} uyarı, {len(self.skipped)} atlanan."
        )


@dataclass
class PersonnelImportReport:
    """Personel içe aktarma özeti (UI raporu + ImportRun.report JSON'ı)."""

    file_hash: str
    file_name: str = ""
    total_rows: int = 0
    processed: int = 0
    created_personnel: int = 0
    updated_personnel: int = 0
    unchanged_personnel: int = 0
    already_imported: bool = False
    dry_run: bool = False
    warnings: list[ImportIssue] = field(default_factory=list)
    skipped: list[ImportIssue] = field(default_factory=list)

    def add_warning(self, row: int, field_name: str, issue: str, raw: str = "") -> None:
        self.warnings.append(ImportIssue(row, field_name, issue, raw))

    def add_skip(self, row: int, field_name: str, issue: str, raw: str = "") -> None:
        self.skipped.append(ImportIssue(row, field_name, issue, raw))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def summary_tr(self) -> str:
        return (
            f"Personel içe aktarma: {self.processed}/{self.total_rows} satır — "
            f"{self.created_personnel} yeni, {self.updated_personnel} güncellenen, "
            f"{self.unchanged_personnel} değişmeyen; "
            f"{len(self.warnings)} uyarı, {len(self.skipped)} atlanan."
        )


# ---------------------------------------------------------------------------
# Girdi normalize — dosya ve pano aynı matris biçimine iner
# ---------------------------------------------------------------------------
def file_hash(file_bytes: bytes) -> str:
    """Yüklenen dosyanın SHA256 özeti (aynı içerik tespiti için)."""
    return hashlib.sha256(file_bytes).hexdigest()


def text_hash(text: str) -> str:
    """Yapıştırılan metnin SHA256 özeti (satır sonları normalize edilir)."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def text_to_grid(text: str) -> list[list[Any]]:
    """Pano metnini satır matrisine çevirir (tab ayraçlı — Excel kopyala/yapıştır)."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return [list(line.split("\t")) for line in normalized.split("\n")]


def _grid_from_file(file_bytes: bytes) -> list[list[Any]]:
    """xlsx baytlarını matrise çevirir; xlsx olmayan içerik ParserError olur.

    openpyxl xlsx olmayan her bayt dizisinde `BadZipFile` (BytesIO'da uzantı
    kontrolü çalışmadığından eski .xls de buraya düşer) veya
    `InvalidFileException` fırlatır — 500 yerine sözleşmeli 400 için sarılır.
    """
    try:
        return excel_veli.read_sheet(file_bytes)
    except (BadZipFile, InvalidFileException) as exc:
        raise ParserError(
            "Dosya .xlsx biçiminde okunamadı; uygulamadaki güncel Excel şablonunu kullanın "
            "(.xls veya CSV desteklenmez)."
        ) from exc


# Parser'ın iç alan adları ("class", "number veya tckn") kullanıcıya gösterilmez.
_MISSING_COLUMN_LABELS: dict[str, str] = {
    "class": "Sınıf",
    "number veya tckn": "Okul Numarası (ya da TCKN)",
    "student_name veya student_first+student_last": (
        "Öğrenci Adı ve Öğrenci Soyadı (ya da tek sütunda Adı Soyadı)"
    ),
    "full_name veya first_name+last_name": "Adı ve Soyadı (ya da tek sütunda Ad Soyad)",
}


def _missing_columns_error(
    missing: list[str], expected: tuple[str, ...], *, headerless_hint: bool = False
) -> ParserError:
    labels = ", ".join(_MISSING_COLUMN_LABELS.get(name, name) for name in missing)
    message = (
        f"Zorunlu sütun(lar) bulunamadı: {labels}. Listeyi başlık satırıyla birlikte "
        f"yapıştırın (şablon başlıkları: {', '.join(expected)}) ya da Şablon indir ile "
        "alınan dosyayı doldurun."
    )
    if headerless_hint:
        message += " Başlık satırı olmadan yapıştırıyorsanız sütunlar şablon sırasında olmalıdır."
    return ParserError(message)


# Başlıksız girişte satır şekli: e-Okul okul numarası kısadır — 11 haneli TCKN
# bu kalıba UYMAZ (Veli İletişim düzeni başlıksız yapıştırılırsa TCKN okul
# numarasına yazılmasın). Ad/soyad en az bir harf içerir, rakam içermez.
_SCHOOL_NUMBER_RE = re.compile(r"\d{1,6}(\.0)?")
_NAME_RE = re.compile(r"[^\d]*[^\W\d_][^\d]*")
_HEADERLESS_SAMPLE_ROWS = 10
# Ad/soyad yerinde cinsiyet kodu ya da ANNE/DİĞER tek hücrede bile başka düzenin
# kanıtıdır. VELİ/BABA gerçek ad/soyad da olabilir: ancak ≥2 satırda kanıt sayılır.
_NOT_NAME_WORDS = frozenset({"e", "k", "kiz", "erkek", "anne", "diger"})
_GUARDIAN_WORDS = frozenset({"veli", "baba"})
# "Ad" sütunu her satırda iki sözcükse birleşik ad-soyad sütunudur; iki isimli
# öğrenciler (Kız MTAL'de sık) yanlış reddedilmesin diye en az bu kadar dolu satır
# aranır. Daha kısa yapıştırmada önizlemedeki okunuş uyarısı güvenlik ağıdır.
_FULL_NAME_MIN_ROWS = 6


def _template_cells(row: list[Any]) -> list[str]:
    cells = [str(c).strip() if c is not None else "" for c in row]
    return cells + [""] * (len(STUDENT_TEMPLATE_HEADERS) - len(cells))


def _looks_like_name(cell: str) -> bool:
    return (
        len(cell) >= 2
        and _NAME_RE.fullmatch(cell) is not None
        and excel_veli.normalize_header(cell) not in _NOT_NAME_WORDS
    )


def _headerless_shape_problem(cells: list[str]) -> str | None:
    """Satırda BAŞKA bir sütun düzeninin kanıtı varsa nedeni; yoksa None.

    Boş hücre kanıt sayılmaz: o satır içe aktarmada satır düzeyinde atlanır
    (tek eksik hücre bütün listeyi reddettirmesin). Neden metni hücre değeri
    içermez (TCKN kişisel veridir; ileti FAILED izine yazılır).
    """
    if any(cells[len(STUDENT_TEMPLATE_HEADERS) :]):
        return "şablonda olmayan fazladan bir sütun dolu"
    if cells[0] and not any(ch.isalpha() for ch in cells[0]):
        return "Sınıf sütununda şube harfi yok"
    if cells[1] and _SCHOOL_NUMBER_RE.fullmatch(cells[1]) is None:
        return "Okul Numarası sütununda en çok 6 haneli bir sayı olmalı"
    if cells[2] and not _looks_like_name(cells[2]):
        return "Öğrenci Adı sütununda ad olmayan bir değer var"
    if cells[3] and not _looks_like_name(cells[3]):
        return "Öğrenci Soyadı sütununda soyad olmayan bir değer var"
    name_words = excel_veli.normalize_header(cells[2]).split()
    surname_words = excel_veli.normalize_header(cells[3]).split()
    if len(name_words) >= 2 and len(surname_words) >= 2 and name_words[-1] == surname_words[-1]:
        # "TUĞBANUR POLAT | AYŞE POLAT": ad-soyad ve veli adı-soyadı sütunları
        return "Öğrenci Adı ve Öğrenci Soyadı sütunları ad-soyad ile veli adı gibi görünüyor"
    if len(name_words) >= 2 and surname_words in (["veli"], ["baba"]):
        return "Öğrenci Soyadı sütununda Veli Kim değeri var"
    if (
        cells[4]
        and any(ch.isalpha() for ch in cells[4])
        and normalize.normalize_excel_date(cells[4]) is None
    ):
        return "Doğum Tarihi sütununda tarih yerine metin var"
    return None


def _is_complete_template_row(cells: list[str]) -> bool:
    return (
        _headerless_shape_problem(cells) is None
        and all(cells[:4])
        and any(ch.isdigit() for ch in cells[0])
    )


def _headerless_error(detail: str) -> ParserError:
    return ParserError(
        f"Başlıksız yapıştırmada {detail}. Sütunlar şablon sırasında olmalı "
        f"({', '.join(STUDENT_TEMPLATE_HEADERS)}) ya da listeyi başlık satırıyla "
        "birlikte yapıştırın."
    )


def _headerless_student_mapping(grid: list[list[Any]]) -> ColumnMapping | None:
    """Başlıksız giriş: ilk 10 dolu satırdan biri eksiksiz bir şablon satırıysa
    sütunlar şablon sırasıyla okunur; hiçbiri değilse None (genel "başlık gerekli").

    Kullanıcı Excel'den çoğu kez yalnız veri satırlarını kopyalar (14.10.2026 saha
    bildirimi). Örneklemde başka düzenin KANITI (TCKN biçimli no, ad yerinde
    rakam/cinsiyet, ≥2 satırda Veli Kim değeri, fazladan sütun, her satırda iki
    sözcüklü "ad" = birleşik ad-soyad) varsa satır numarasıyla ParserError:
    yanlış alanlara yazmaktansa reddedilir. Boş hücre kanıt değildir. Önizlemede
    ilk satırın okunuşu gösterilir (1-3 satırlık yapıştırmada şekil yetmez).
    `header_row=-1`: satır numaraları yapıştırılan satırlarla aynı kalır.
    """
    sample = [
        (index + 1, _template_cells(row))
        for index, row in enumerate(grid)
        if any(str(c or "").strip() for c in row)
    ][:_HEADERLESS_SAMPLE_ROWS]
    reference = next(((n, c) for n, c in sample if _is_complete_template_row(c)), None)
    if reference is None:
        return None
    for row_number, cells in sample:
        if row_number >= reference[0]:
            break
        # Başlık gibi satır: rakamsız ve Okul Numarası yerinde metin ("No", "Okul No").
        if cells[1] and not any(ch.isdigit() for ch in "".join(cells)):
            raise ParserError(
                f"{row_number}. satır başlık satırı gibi görünüyor ama tanınmadı. Şablon "
                f"başlıklarını kullanın ({', '.join(STUDENT_TEMPLATE_HEADERS)}) ya da bu "
                "satırı silip yalnız öğrenci satırlarını yapıştırın."
            )
    for row_number, cells in sample:
        problem = _headerless_shape_problem(cells)
        if problem is not None:
            raise _headerless_error(f"{row_number}. satır şablon sırasına uymuyor: {problem}")
    for column, label in ((2, "Öğrenci Adı"), (3, "Öğrenci Soyadı")):
        hits = [n for n, c in sample if excel_veli.normalize_header(c[column]) in _GUARDIAN_WORDS]
        if len(hits) >= 2:
            raise _headerless_error(
                f"{label} sütununda birden çok satırda VELİ/BABA değeri var "
                "(Veli Kim sütunu olabilir)"
            )
    both_multi = [c for _, c in sample if c[2] and c[3]]
    if len(both_multi) >= 2 and all(
        len(c[2].split()) >= 2 and len(c[3].split()) >= 2 for c in both_multi
    ):
        raise _headerless_error(
            "Öğrenci Adı ve Öğrenci Soyadı sütunları her satırda birden çok sözcük içeriyor "
            "(ad-soyad ile veli adı ya da alan adı sütunları olabilir)"
        )
    named = [c[2] for _, c in sample if c[2]]
    if len(named) >= _FULL_NAME_MIN_ROWS and all(len(name.split()) >= 2 for name in named):
        raise _headerless_error(
            "Öğrenci Adı sütunu her satırda ad ve soyad gibi görünüyor (birleşik "
            "ad-soyad sütunu olabilir)"
        )
    mapping = excel_veli.detect_columns([list(STUDENT_TEMPLATE_HEADERS)])
    mapping.header_row = -1
    ref_number, ref = reference
    mapping.warnings.append(
        "Başlık satırı bulunamadı; sütunlar şablon sırasıyla okundu: "
        f"{', '.join(STUDENT_TEMPLATE_HEADERS)}. {ref_number}. satır şöyle okundu: "
        f"Sınıf {ref[0]} · Okul No {ref[1]} · Ad {ref[2]} · Soyad {ref[3]}. "
        "Yanlışsa listeyi başlık satırıyla yapıştırın."
    )
    return mapping


def _parse_student_grid(grid: list[list[Any]]) -> tuple[ColumnMapping, list[ParsedRow]]:
    """Matristen (mapping, satırlar); kritik sütun eksikse ParserError (parse_workbook paritesi)."""
    mapping = excel_veli.detect_columns(grid)
    if not mapping.is_usable:
        headerless = _headerless_student_mapping(grid)
        if headerless is None:
            raise _missing_columns_error(
                mapping.missing_critical, STUDENT_TEMPLATE_HEADERS, headerless_hint=True
            )
        mapping = headerless
    return mapping, excel_veli.parse_rows(grid, mapping)


def _parse_personnel_grid(
    grid: list[list[Any]],
) -> tuple[PersonnelColumnMapping, list[ParsedPersonnelRow]]:
    mapping = excel_personel.detect_columns(grid)
    if not mapping.is_usable:
        raise _missing_columns_error(mapping.missing_critical, PERSONNEL_TEMPLATE_HEADERS)
    return mapping, excel_personel.parse_rows(grid, mapping)


# ---------------------------------------------------------------------------
# ImportRun yaşam döngüsü (idempotency uyarısı + koşullu unique koruması)
# ---------------------------------------------------------------------------
def _open_run(*, source_type: str, source_hash: str, file_name: str) -> tuple[ImportRun, bool]:
    """Koşu kaydını açar → (run, zaten_tamamlanmış_mı).

    Aynı hash daha önce TAMAMLANDIYSA yeni satır AÇILMAZ — mevcut satır yeniden
    RUNNING'e çekilir (uq_importrun_completed_per_hash bozulmaz; yeniden commit
    meşru güncellemedir, yalnız raporda uyarı düşer).
    """
    existing: ImportRun | None = ImportRun.objects.filter(
        source_type=source_type, file_hash=source_hash, status=ImportStatus.COMPLETED
    ).first()
    if existing is not None:
        existing.status = ImportStatus.RUNNING
        existing.started_at = timezone.now()
        existing.finished_at = None
        if file_name:
            existing.file_name = file_name
        existing.save(
            update_fields=["status", "started_at", "finished_at", "file_name", "updated_at"]
        )
        return existing, True
    run = ImportRun.objects.create(
        source_type=source_type,
        file_name=file_name,
        file_hash=source_hash,
        status=ImportStatus.RUNNING,
    )
    return run, False


def _close_run(run: ImportRun, report_dict: dict[str, Any]) -> None:
    run.status = ImportStatus.COMPLETED
    run.finished_at = timezone.now()
    run.report = report_dict
    run.save(update_fields=["status", "finished_at", "report", "updated_at"])


# ---------------------------------------------------------------------------
# Öğrenci içe aktarma
# ---------------------------------------------------------------------------
@transaction.atomic
def _ingest_students(
    *, grid: list[list[Any]], source_hash: str, file_name: str = ""
) -> StudentImportReport:
    """Matristeki öğrenci-veli satırlarını Student kayıtlarına yazar (TCKN upsert)."""
    mapping, rows = _parse_student_grid(grid)
    report = StudentImportReport(file_hash=source_hash, file_name=file_name, total_rows=len(rows))
    run, already = _open_run(
        source_type=ImportSourceType.STUDENTS, source_hash=source_hash, file_name=file_name
    )
    report.already_imported = already
    for header_warning in mapping.warnings:
        # Başlıksız girişte header_row=-1; uyarı ilk satıra bağlanır.
        report.add_warning(max(mapping.header_row + 1, 1), "header", header_warning)

    state = _StudentRunState(has_guardian_columns=bool(_GUARDIAN_FIELDS & mapping.fields.keys()))
    for row in rows:
        _process_student_row(row, report=report, state=state)

    _ensure_student_classes()
    _close_run(run, report.to_dict())
    return report


_STUDENT_NUMBER_MAX_LENGTH = 16  # Student.student_number

_GUARDIAN_FIELDS = frozenset(
    {"guardian", "mother_name", "mother_phone", "father_name", "father_phone"}
)


@dataclass
class _StudentRunState:
    """Bir içe aktarma koşusunun satırlar arası durumu (dosya içi yinelenme).

    - `seen_tckn`: TCKN → ilk satır no; aynı TCKN ikinci kez gelirse satır atlanır.
    - `seen_number`: okul no → (ilk satır no, o satırın TCKN'si). Aynı numara
      yalnız iki satırın da farklı TCKN'si varsa geçer (aynı numaralı iki ayrı
      öğrenci); satırlardan biri TCKN'sizse ikincisi atlanır.
    - `touched`: bu koşuda yazılan öğrenci → satır no. Bir öğrenci bir koşuda
      iki kez yazılmaz; ikinci kez eşleşen satır atlanır (sessiz ezme yok).
    - `replaced_numbers`: bu koşuda numarası değiştirilen öğrencinin ESKİ numarası
      → satır no; o numarayla gelen TCKN'siz satır aynı kişiyi ikinci kez açmaz.
    """

    has_guardian_columns: bool
    seen_tckn: dict[str, int] = field(default_factory=dict)
    seen_number: dict[str, tuple[int, str | None]] = field(default_factory=dict)
    touched: dict[Any, int] = field(default_factory=dict)
    replaced_numbers: dict[str, int] = field(default_factory=dict)
    # Ad-soyad anahtarı → TCKN'siz aktif öğrencilerin okul numaraları (koşu başında,
    # ilk ihtiyaçta bir kez kurulur; satır başına tüm sicili taramamak için).
    tckn_less_by_name: dict[str, list[str]] | None = None


def _skip_in_file_duplicate(
    row: ParsedRow, report: StudentImportReport, state: _StudentRunState
) -> bool:
    """Satır dosyada daha önce geçen bir öğrencinin tekrarıysa atlar (True)."""
    if row.tckn is not None and row.tckn in state.seen_tckn:
        # raw_value MASKELİ: TCKN kişisel veridir, rapor JSON'ına ham düşmez.
        report.add_skip(
            row.row_number,
            "tckn",
            f"Bu TCKN dosyada {state.seen_tckn[row.tckn]}. satırda da var; satır atlandı.",
            mask_tckn(row.tckn),
        )
        return True
    if row.tckn is None and row.student_number in state.replaced_numbers:
        report.add_skip(
            row.row_number,
            "number",
            "Bu okul numarası, dosyada "
            f"{state.replaced_numbers[row.student_number]}. satırda numarası değiştirilen "
            "öğrencinin eski numarası; satır atlandı.",
            row.student_number,
        )
        return True
    if row.student_number in state.seen_number:
        first_row, first_tckn = state.seen_number[row.student_number]
        distinct_people = row.tckn is not None and first_tckn is not None
        if not distinct_people:
            report.add_skip(
                row.row_number,
                "number",
                f"Bu okul numarası dosyada {first_row}. satırda da var; satır atlandı.",
                row.student_number,
            )
            return True
    if row.tckn is not None:
        state.seen_tckn[row.tckn] = row.row_number
    if row.student_number:
        state.seen_number.setdefault(row.student_number, (row.row_number, row.tckn))
    return False


def _find_existing_student(
    row: ParsedRow, report: StudentImportReport
) -> tuple[Student | None, bool]:
    """TCKN ile, yoksa okul numarasıyla mevcut öğrenciyi bulur → (öğrenci, atlandı_mı).

    Numarayla aramada TCKN'si DOLU ve satırınkinden FARKLI aday elenir (başka
    kişidir). Birden fazla aday kalırsa satır belirsiz sayılıp atlanır.
    """
    # DB filtresi DEĞİL: uygulama parolası konulduğunda TCKN şifrelidir ve
    # `filter(tckn=...)` daima boş döner (kopya öğrenci üretirdi) — F5-D5.
    if row.tckn is not None:
        student = selectors.find_student_by_tckn(row.tckn)
        if student is not None:
            return student, False
    if not row.student_number:
        return None, False
    candidates = [
        s
        for s in Student.objects.filter(
            student_number=row.student_number, status=StudentStatus.ACTIVE
        )
        if not (row.tckn and s.tckn and s.tckn != row.tckn)
    ]
    if len(candidates) > 1:
        report.add_skip(
            row.row_number,
            "number",
            "Aynı okul numarasına sahip birden fazla aktif öğrenci var; satır eşleştirilemedi.",
            row.student_number,
        )
        return None, True
    if candidates and _name_key(row.student_first, row.student_last) != _name_key(
        candidates[0].first_name, candidates[0].last_name
    ):
        # Yalnız numarayla eşleşen kayıtta ad/soyad farklı: numara başka bir öğrenciye
        # verilmiş olabilir. Ad, sınıf ya da TCKN üzerine yazılmaz (disiplin dosyası
        # başka birinin kimliğini göstermesin); kullanıcı Kişiler'den düzeltir.
        report.add_skip(
            row.row_number,
            "number",
            "Bu okul numarası adı/soyadı farklı bir öğrenciye kayıtlı; satır atlandı. Aynı "
            "öğrenciyse önce Kişiler'den adını düzeltin.",
            row.student_number,
        )
        return None, True
    return (candidates[0] if candidates else None), False


def _warn_possible_duplicate(
    row: ParsedRow, report: StudentImportReport, state: _StudentRunState
) -> None:
    """TCKN'li yeni kayıt açılırken aynı ad-soyadlı TCKN'siz aktif öğrenci varsa uyarır.

    Örn. şablonla yanlış numarayla girilmiş öğrenci, e-Okul listesinde doğru
    numarasıyla gelince ikinci kez açılır; veriye dokunulmaz, kullanıcı birleştirir.
    """
    if row.tckn is None:
        return
    if state.tckn_less_by_name is None:
        index: dict[str, list[str]] = {}
        for s in Student.objects.filter(status=StudentStatus.ACTIVE).only(
            "first_name", "last_name", "student_number", "tckn"
        ):
            if not s.tckn:
                index.setdefault(_name_key(s.first_name, s.last_name), []).append(s.student_number)
        state.tckn_less_by_name = index
    numbers = state.tckn_less_by_name.get(_name_key(row.student_first, row.student_last))
    if numbers:
        report.add_warning(
            row.row_number,
            "full_name",
            "Aynı ad-soyadla TCKN'siz bir öğrenci kayıtlı (okul no "
            f"{', '.join(numbers)}); aynı kişiyse Kişiler'den kontrol edin.",
            row.student_number,
        )


def _name_key(first: str, last: str) -> str:
    """Ad-soyad karşılaştırma anahtarı (yalnız eşleme için: Türkçe→ASCII, boşluksuz)."""
    return excel_veli.normalize_header(f"{first} {last}").replace(" ", "")


def _process_student_row(
    row: ParsedRow, *, report: StudentImportReport, state: _StudentRunState
) -> None:
    """Tek satır: doğrula → yinelenme → mevcut öğrenciyi bul → veli düzleştir → yaz."""
    if (row.student_first, row.student_last) == STUDENT_TEMPLATE_EXAMPLE[2:4]:
        report.add_skip(row.row_number, "row", "Şablondaki örnek satır; aktarılmadı.")
        return
    if row.raw_tckn and row.tckn is None:
        # raw_value MASKELİ: TCKN kişisel veridir, rapor JSON'ına ham düşmez.
        report.add_skip(row.row_number, "tckn", "Geçersiz TCKN", mask_tckn(row.raw_tckn))
        return
    if row.tckn is None and not row.student_number:
        report.add_skip(
            row.row_number,
            "number",
            "Okul numarası veya TCKN bulunamadı.",
        )
        return
    if row.student_number and normalize.normalize_tckn(row.student_number) is not None:
        # Okul numarası sütununa TCKN yazılmış: şifresiz student_number alanına ve
        # evraka düşmesin (KVKK). raw_value MASKELİ.
        report.add_skip(
            row.row_number,
            "number",
            "Okul numarası yerine TCKN yazılmış; satır atlandı.",
            mask_tckn(row.student_number),
        )
        return
    if not row.student_first or not row.student_last:
        report.add_skip(row.row_number, "full_name", "Öğrenci adı ya da soyadı boş; satır atlandı.")
        return
    if row.student_number and (
        not any(ch.isdigit() for ch in row.student_number)
        or len(row.student_number) > _STUDENT_NUMBER_MAX_LENGTH
    ):
        report.add_skip(
            row.row_number,
            "number",
            "Okul numarası geçersiz (sütunlar kaymış olabilir); satır atlandı.",
            row.student_number,
        )
        return
    if any(ch.isdigit() for ch in row.student_first + row.student_last):
        # Değer bilinçli rapora yazılmaz: kaymış satırda TCKN ad hücresine düşmüş olabilir.
        report.add_skip(
            row.row_number,
            "full_name",
            "Öğrenci adı ya da soyadı rakam içeriyor (sütunlar kaymış olabilir); satır atlandı.",
        )
        return
    if row.class_level is None:
        report.add_skip(
            row.row_number, "class", "Sınıf/şube çözülemedi (beklenen yazım: 10/A)", row.raw_class
        )
        return
    if _skip_in_file_duplicate(row, report, state):
        return
    student, skipped = _find_existing_student(row, report)
    if skipped:
        return
    if student is not None and student.pk in state.touched:
        report.add_skip(
            row.row_number,
            "row",
            f"Bu öğrenci dosyada {state.touched[student.pk]}. satırda zaten işlendi; "
            "satır atlandı.",
        )
        return

    kinship, primary, other = _resolve_guardian(
        row, report, has_guardian_columns=state.has_guardian_columns
    )
    if primary.has_any_data and primary.raw_phone and primary.phone is None:
        # raw bilinçli BOŞ: telefon kişisel veridir, rapora ham yazılmaz.
        report.add_warning(
            row.row_number, "phone", "Sorumlu veli telefonu geçersiz (05XXXXXXXXX bekleniyor)."
        )
    if row.raw_birth_date and row.birth_date is None:
        report.add_warning(
            row.row_number, "birth_date", "Doğum tarihi biçimi çözülemedi (GG.AA.YYYY bekleniyor)."
        )
    if row.raw_gender and not row.gender:
        report.add_warning(
            row.row_number, "gender", "Cinsiyet çözülemedi (E/K bekleniyor).", row.raw_gender
        )

    fields: dict[str, Any] = {
        "first_name": row.student_first,
        "last_name": row.student_last,
        "class_level": row.class_level,
        "class_section": row.class_section,
    }
    # Boş/çözülemeyen hücre mevcut veriyi SİLMEZ (import silmez ilkesi — OYS
    # `_sync_parents` "atla ve koru" davranışının düz-model karşılığı): okul no,
    # veli ve demografi anahtarları yalnız dosyada VERİ VARSA fields'a girer.
    if row.student_number:
        fields["student_number"] = row.student_number
    if primary.has_any_data:
        fields["guardian_name"] = primary.raw_name.strip()
        fields["guardian_kinship"] = kinship
        if primary.phone is not None:
            fields["guardian_phone"] = primary.phone
    if other.phone is not None:
        fields["guardian_phone2"] = other.phone
    if row.birth_date is not None:
        fields["birth_date"] = row.birth_date
    if row.gender:
        fields["gender"] = row.gender

    if student is None:
        _warn_possible_duplicate(row, report, state)
        student = Student.objects.create(tckn=row.tckn or "", **fields)
        report.created_students += 1
    else:
        if row.tckn is not None and not student.tckn:
            # Numarayla eşleşen TCKN'siz kayda TCKN eklenir (silmez; TCKN'nin başka
            # canlı kayıtta olmadığı yukarıdaki TCKN aramasıyla bilinir).
            fields["tckn"] = row.tckn
        changed = [name for name, value in fields.items() if getattr(student, name) != value]
        if "student_number" in changed and student.student_number:
            state.replaced_numbers.setdefault(student.student_number, row.row_number)
        if changed:
            for name in changed:
                setattr(student, name, fields[name])
            student.save(update_fields=[*changed, "updated_at"])
            report.updated_students += 1
        else:
            report.unchanged_students += 1
    state.touched[student.pk] = row.row_number
    report.processed += 1


def _ensure_student_classes() -> None:
    """Sicildeki aktif öğrenci şubelerini aktif yılın eşleştirme listesine ekler."""
    year = SchoolYear.objects.filter(is_active=True).first()
    if year is None:
        return
    class_pairs = set(
        Student.objects.filter(status=StudentStatus.ACTIVE)
        .exclude(class_level=None)
        .exclude(class_section="")
        .values_list("class_level", "class_section")
    )
    for level, section in sorted(class_pairs):
        ClassResponsibility.objects.get_or_create(
            school_year=year,
            class_level=level,
            class_section=section,
        )


def _resolve_guardian(
    row: ParsedRow, report: StudentImportReport, *, has_guardian_columns: bool = True
) -> tuple[str, ParsedParent, ParsedParent]:
    """Veli Kim → (yakınlık, sorumlu veli, diğer veli). OYS `_resolve_parent_roles` paritesi.

    Atanan sorumlu velinin verisi eksikse diğerine düşülür ve uyarı yazılır;
    DİĞER/boş → varsayılan BABA + uyarı (elle düzeltme için).
    """
    mother, father = row.mother, row.father
    g = row.guardian

    if not has_guardian_columns:
        # Dosyada veli sütunu yok (standart şablon): uyarı gürültüdür; her satıra
        # düşüp başarılı önizlemeyi hata gibi gösteriyordu (14.10.2026 saha bildirimi).
        return GuardianKinship.FATHER, father, mother

    if g == "ANNE":
        if mother.has_any_data:
            return GuardianKinship.MOTHER, mother, father
        report.add_warning(
            row.row_number,
            "guardian",
            "Sorumlu veli ANNE ama anne bilgisi eksik; BABA varsayıldı.",
            g,
        )
        return GuardianKinship.FATHER, father, mother

    if g == "BABA":
        if father.has_any_data:
            return GuardianKinship.FATHER, father, mother
        report.add_warning(
            row.row_number,
            "guardian",
            "Sorumlu veli BABA ama baba bilgisi eksik; ANNE varsayıldı.",
            g,
        )
        return GuardianKinship.MOTHER, mother, father

    if not mother.has_any_data and not father.has_any_data:
        report.add_warning(
            row.row_number,
            "guardian",
            "Anne/baba bilgisi okunamadı; veli alanları güncellenmedi.",
            row.guardian,
        )
        return GuardianKinship.FATHER, father, mother
    # Uyarı fiilî sonucu söyler: baba verisi yoksa kayda ANNE yazılır.
    if father.has_any_data:
        kinship, primary, other = GuardianKinship.FATHER, father, mother
    else:
        kinship, primary, other = GuardianKinship.MOTHER, mother, father
    report.add_warning(
        row.row_number,
        "guardian",
        f"Veli Kim '{row.guardian or 'boş'}' belirsiz; {kinship.value} varsayıldı.",
        row.guardian,
    )
    return kinship, primary, other


# ---------------------------------------------------------------------------
# Personel içe aktarma
# ---------------------------------------------------------------------------
@transaction.atomic
def _ingest_personnel(
    *, grid: list[list[Any]], source_hash: str, file_name: str = ""
) -> PersonnelImportReport:
    """Matristeki personel satırlarını Personnel kayıtlarına yazar (ada göre upsert).

    Eşleşme anahtarı normalize edilmiş ad-soyaddır (`normalize_header`: Türkçe→
    ASCII küçük harf) — yerel ölçekte (≤100 personel) yeterli; adaş çakışması
    durumunda son kayıt kazanır, elle düzeltilir.
    """
    mapping, rows = _parse_personnel_grid(grid)
    report = PersonnelImportReport(file_hash=source_hash, file_name=file_name, total_rows=len(rows))
    run, already = _open_run(
        source_type=ImportSourceType.PERSONNEL, source_hash=source_hash, file_name=file_name
    )
    report.already_imported = already
    for header_warning in mapping.warnings:
        report.add_warning(mapping.header_row + 1, "header", header_warning)

    name_index: dict[str, Personnel] = {
        excel_veli.normalize_header(p.full_name): p for p in Personnel.objects.all()
    }
    for row in rows:
        _process_personnel_row(row, report=report, name_index=name_index)

    _close_run(run, report.to_dict())
    return report


def _process_personnel_row(
    row: ParsedPersonnelRow, *, report: PersonnelImportReport, name_index: dict[str, Personnel]
) -> None:
    """Tek personel satırı: ada göre bul/oluştur; boş hücre mevcut veriyi silmez."""
    if not row.first_name and not row.last_name:
        report.add_skip(row.row_number, "full_name", "Ad-soyad boş; satır atlandı.")
        return
    if (row.first_name, row.last_name) == PERSONNEL_TEMPLATE_EXAMPLE[:2]:
        report.add_skip(row.row_number, "row", "Şablondaki örnek satır; aktarılmadı.")
        return

    key = excel_veli.normalize_header(row.raw_full_name)
    person = name_index.get(key)
    if person is None:
        person = Personnel.objects.create(
            first_name=row.first_name,
            last_name=row.last_name,
            title=row.title,
            branch=row.branch,
        )
        name_index[key] = person
        report.created_personnel += 1
    else:
        changed: list[str] = []
        if row.title and person.title != row.title:
            person.title = row.title
            changed.append("title")
        if row.branch and person.branch != row.branch:
            person.branch = row.branch
            changed.append("branch")
        if changed:
            person.save(update_fields=[*changed, "updated_at"])
            report.updated_personnel += 1
        else:
            report.unchanged_personnel += 1
    report.processed += 1


# ---------------------------------------------------------------------------
# Kamu API — dosya ve pano girişleri (preview/commit)
# ---------------------------------------------------------------------------
def commit_students_file(*, file_bytes: bytes, file_name: str = "") -> StudentImportReport:
    return _student_entry(
        lambda: _grid_from_file(file_bytes), file_hash(file_bytes), file_name, preview=False
    )


def commit_students_text(*, text: str) -> StudentImportReport:
    return _student_entry(lambda: text_to_grid(text), text_hash(text), "", preview=False)


def preview_students_file(*, file_bytes: bytes, file_name: str = "") -> StudentImportReport:
    return _student_entry(
        lambda: _grid_from_file(file_bytes), file_hash(file_bytes), file_name, preview=True
    )


def preview_students_text(*, text: str) -> StudentImportReport:
    return _student_entry(lambda: text_to_grid(text), text_hash(text), "", preview=True)


def commit_personnel_file(*, file_bytes: bytes, file_name: str = "") -> PersonnelImportReport:
    return _personnel_entry(
        lambda: _grid_from_file(file_bytes), file_hash(file_bytes), file_name, preview=False
    )


def commit_personnel_text(*, text: str) -> PersonnelImportReport:
    return _personnel_entry(lambda: text_to_grid(text), text_hash(text), "", preview=False)


def preview_personnel_file(*, file_bytes: bytes, file_name: str = "") -> PersonnelImportReport:
    return _personnel_entry(
        lambda: _grid_from_file(file_bytes), file_hash(file_bytes), file_name, preview=True
    )


def preview_personnel_text(*, text: str) -> PersonnelImportReport:
    return _personnel_entry(lambda: text_to_grid(text), text_hash(text), "", preview=True)


def _student_entry(
    grid_supplier: Callable[[], list[list[Any]]],
    source_hash: str,
    file_name: str,
    *,
    preview: bool,
) -> StudentImportReport:
    """Ortak giriş: ParserError'da kalıcı FAILED izi bırakır ve hatayı yükseltir.

    Ingest atomiktir — hata rollback'i RUNNING satırını da siler; FAILED izi bu
    yüzden transaction DIŞINDA, burada yazılır (geçmiş görünümü boş kalmasın).
    """
    try:
        grid = grid_supplier()
        if preview:
            return _preview_students(grid=grid, source_hash=source_hash, file_name=file_name)
        return _ingest_students(grid=grid, source_hash=source_hash, file_name=file_name)
    except ParserError as exc:
        _record_failed(ImportSourceType.STUDENTS, source_hash, file_name, exc)
        raise


def _personnel_entry(
    grid_supplier: Callable[[], list[list[Any]]],
    source_hash: str,
    file_name: str,
    *,
    preview: bool,
) -> PersonnelImportReport:
    try:
        grid = grid_supplier()
        if preview:
            return _preview_personnel(grid=grid, source_hash=source_hash, file_name=file_name)
        return _ingest_personnel(grid=grid, source_hash=source_hash, file_name=file_name)
    except ParserError as exc:
        _record_failed(ImportSourceType.PERSONNEL, source_hash, file_name, exc)
        raise


def _preview_students(
    *, grid: list[list[Any]], source_hash: str, file_name: str = ""
) -> StudentImportReport:
    """Öğrenci importunu YAZMADAN simüle eder (gerçek ingest + rollback)."""
    with transaction.atomic():
        report = _ingest_students(grid=grid, source_hash=source_hash, file_name=file_name)
        transaction.set_rollback(True)
    report.dry_run = True
    _record_preview(ImportSourceType.STUDENTS, report.file_hash, file_name, report.to_dict())
    return report


def _preview_personnel(
    *, grid: list[list[Any]], source_hash: str, file_name: str = ""
) -> PersonnelImportReport:
    with transaction.atomic():
        report = _ingest_personnel(grid=grid, source_hash=source_hash, file_name=file_name)
        transaction.set_rollback(True)
    report.dry_run = True
    _record_preview(ImportSourceType.PERSONNEL, report.file_hash, file_name, report.to_dict())
    return report


def _record_preview(
    source_type: str, source_hash: str, file_name: str, report_dict: dict[str, Any]
) -> None:
    """Kalıcı PREVIEWED izi (geçmiş görünümü) — rollback DIŞINDA yazılır."""
    ImportRun.objects.create(
        source_type=source_type,
        file_name=file_name,
        file_hash=source_hash,
        status=ImportStatus.PREVIEWED,
        finished_at=timezone.now(),
        report=report_dict,
    )


def _record_failed(source_type: str, source_hash: str, file_name: str, error: Exception) -> None:
    """Kalıcı FAILED izi. `error` metni yalnız yapısal bilgidir (sütun adları) — PII yok."""
    ImportRun.objects.create(
        source_type=source_type,
        file_name=file_name,
        file_hash=source_hash,
        status=ImportStatus.FAILED,
        finished_at=timezone.now(),
        report={"error": str(error)},
    )
