"""Yıl devri (ders yılı geçişi) sihirbazı — tasarım §4.6.

Sihirbazın beş adımı ve bu modülün payı:

1. **Yeni ders yılı** — `create_next_school_year()`: yılı açar, `is_active`
   bayrağını YENİ yıla taşır (tek-aktif kuralı `school_year.activate_school_year`
   içinde), yeni yılın tatillerini seed eder. Aktif yıl değişince disiplin dosya
   numarası ön eki de değişir (`apps.disiplin.services.cases.generate_case_no`
   aktif yılın adını okur) — eski numaralar regex ile izole olduğundan BOZULMAZ.
2. **Tatiller** — mevcut `calendar.seed_holidays()` çağrılır; dini bayramların
   `is_estimated` uyarısı olduğu gibi korunur.
3. **Yeni kurul tanımı** — bu modülün İŞİ DEĞİLDİR: kurul üyeleri her yıl
   yeniden belirlenir (md. 188), kopyalanmaz. Sihirbaz UI'ı yeni yılda kurulun
   TANIMSIZ olduğunu görünür kılar ve kurul ekranına yönlendirir.
4. **Öğrenci güncelleme** — ÖNERİLEN yol yeni e-Okul listesini yeniden import
   etmektir (mevcut upsert boru hattı, tasarım §4.7). Bu modül ALTERNATİF yolu
   sağlar: `promote_students()` toplu sınıf yükseltmesi (önizleme + uygula).
5. **Kapanmamış eski-yıl dosyaları** — UYARIDIR, engel DEĞİL (disiplin süreci yıl
   aşabilir). Uyarı verisi disiplin tarafındadır; UI onu disiplin ucundan okur.

MODÜL SINIRI (ADR-0002 muadili): `apps.okul` üretim kodu `apps.disiplin`
modellerini/servislerini import ETMEZ. Bağımlılık yönü tek yönlüdür
(`disiplin → okul`); tersi çevrimsel bir bağ kurardı. Devrin disiplin tarafındaki
gerçekleri (kapanmamış dosya listesi, yeni yılda kurul tanımlı mı) sihirbaz
EKRANI ayrı disiplin uçlarından okur — `GET /discipline/cases/` ve
`GET /discipline/committee/` zaten vardır, yeni backend yüzeyi gerekmez.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.okul import selectors
from apps.okul.models import SchoolYear, Student, StudentStatus
from apps.okul.services import calendar as calendar_service
from apps.okul.services import school_year as school_year_service

# Lise değişmezi (9-12). `normalize.normalize_class_section` içe aktarmada,
# `StudentSerializer.validate_class_level` elle girişte bu aralığı zorlar; toplu
# yükseltme de aynı aralıkta çalışır (dışındaki veri sessizce kaydırılmaz).
FIRST_CLASS_LEVEL = 9
FINAL_CLASS_LEVEL = 12

# Önceki yıl yokken önerilecek varsayılan ders yılı sınırları (kullanıcı düzenler).
DEFAULT_START_MONTH_DAY = (9, 15)
DEFAULT_END_MONTH_DAY = (6, 15)


# ---------------------------------------------------------------------------
# Veri taşıyıcılar
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class NextYearSuggestion:
    """Sihirbazın ilk adımına önerilecek yeni ders yılı (kullanıcı değiştirebilir)."""

    name: str
    start_date: date
    end_date: date

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
        }


@dataclass(frozen=True)
class RolloverResult:
    """Yeni ders yılı adımının sonucu (UI adım özeti)."""

    school_year: SchoolYear
    previous_school_year_name: str
    holidays_created: int
    holidays_skipped: int


@dataclass(frozen=True)
class LevelMove:
    """Bir sınıf seviyesinin yükseltme dökümü (9→10 gibi)."""

    from_level: int
    to_level: int
    count: int

    def to_dict(self) -> dict[str, int]:
        return {"from_level": self.from_level, "to_level": self.to_level, "count": self.count}


@dataclass(frozen=True)
class LevelCount:
    """Sicil dökümü satırı — yükseltme DEĞİL, mevcut dağılım (12. sınıfın 'hedefi' yoktur)."""

    level: int
    count: int

    def to_dict(self) -> dict[str, int]:
        return {"level": self.level, "count": self.count}


@dataclass(frozen=True)
class PromotionReport:
    """Toplu sınıf yükseltme raporu — önizleme (`applied=False`) ve uygulama aynı şekli döner."""

    applied: bool
    graduate_final_level: bool
    promoted: int
    graduated: int
    final_level_kept: int
    skipped_inactive: int
    skipped_no_level: int
    skipped_out_of_range: int
    moves: tuple[LevelMove, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "applied": self.applied,
            "graduate_final_level": self.graduate_final_level,
            "promoted": self.promoted,
            "graduated": self.graduated,
            "final_level_kept": self.final_level_kept,
            "skipped_inactive": self.skipped_inactive,
            "skipped_no_level": self.skipped_no_level,
            "skipped_out_of_range": self.skipped_out_of_range,
            "moves": [m.to_dict() for m in self.moves],
        }


@dataclass(frozen=True)
class RolloverStatus:
    """Sihirbaz açılış özeti — mevcut durum + yeni yıl önerisi."""

    active_school_year: SchoolYear | None
    suggestion: NextYearSuggestion
    active_student_count: int
    students_without_level: int
    level_counts: tuple[LevelCount, ...]


# ---------------------------------------------------------------------------
# 1. Sonraki yıl önerisi
# ---------------------------------------------------------------------------
def _shift_year(day: date, years: int) -> date:
    """Tarihi `years` yıl ileri taşır; 29 Şubat artık olmayan yılda 28'ine kayar."""
    try:
        return day.replace(year=day.year + years)
    except ValueError:
        return day.replace(year=day.year + years, day=28)


def suggest_next_year(
    previous: SchoolYear | None = None, *, today: date | None = None
) -> NextYearSuggestion:
    """Bir sonraki ders yılı için ad + tarih önerir (kullanıcı formda düzenleyebilir).

    Önceki yıl varsa tarihleri BİR YIL ileri taşınır (okulun kendi takvimi
    korunur). Yoksa `today` esas alınır: Haziran'dan itibaren içinde bulunulan
    takvim yılı, öncesinde bir önceki Eylül (ders yılı Eylül'de başlar).
    """
    if previous is not None:
        start = _shift_year(previous.start_date, 1)
        end = _shift_year(previous.end_date, 1)
        return NextYearSuggestion(
            name=f"{start.year}-{start.year + 1}", start_date=start, end_date=end
        )

    ref = today or timezone.localdate()
    base = ref.year if ref.month >= 6 else ref.year - 1
    return NextYearSuggestion(
        name=f"{base}-{base + 1}",
        start_date=date(base, *DEFAULT_START_MONTH_DAY),
        end_date=date(base + 1, *DEFAULT_END_MONTH_DAY),
    )


# ---------------------------------------------------------------------------
# 2. Yeni ders yılı + tatil seed'i
# ---------------------------------------------------------------------------
@transaction.atomic
def create_next_school_year(
    *,
    name: str,
    start_date: date,
    end_date: date,
    seed_holidays: bool = True,
    first_term_end: date | None = None,
    second_term_start: date | None = None,
) -> RolloverResult:
    """Yeni ders yılını açar, AKTİF yapar ve (istenirse) tatillerini yükler.

    Aktif yıl değişimi tek-aktif kuralıyla yapılır (eski yıl pasife çekilir).
    Kapanmamış eski-yıl dosyaları devri ENGELLEMEZ — süreç yıl aşabilir; uyarı
    sihirbaz ekranındadır (modül başlığı).
    """
    cleaned = name.strip()
    if not cleaned:
        raise ValueError("Ders yılı adı boş olamaz (örn. 2026-2027).")
    if end_date <= start_date:
        raise ValueError("Bitiş tarihi başlangıç tarihinden sonra olmalıdır.")
    if SchoolYear.objects.filter(name=cleaned).exists():
        raise ValueError(f"'{cleaned}' adında bir ders yılı zaten var; farklı bir ad girin.")

    previous = selectors.active_school_year()
    if previous is not None and start_date <= previous.start_date:
        raise ValueError(
            f"Yeni ders yılı, aktif ders yılından ('{previous.name}') sonra başlamalıdır. "
            "Geçmiş bir yıla dönmek için Ayarlar > Ders Yılları ekranını kullanın."
        )

    year = school_year_service.create_school_year(
        name=cleaned, start_date=start_date, end_date=end_date, activate=True
    )
    if (first_term_end is None) != (second_term_start is None):
        raise ValueError("Dönem takvimi için iki dönemin sınır tarihleri birlikte girilmelidir.")
    if first_term_end is not None and second_term_start is not None:
        from apps.okul.services.terms import configure_terms

        configure_terms(
            school_year=year,
            first_end=first_term_end,
            second_start=second_term_start,
        )

    created = skipped = 0
    if seed_holidays:
        created, skipped = calendar_service.seed_holidays(year)

    return RolloverResult(
        school_year=year,
        previous_school_year_name=previous.name if previous is not None else "",
        holidays_created=created,
        holidays_skipped=skipped,
    )


# ---------------------------------------------------------------------------
# 3. Toplu sınıf yükseltme (e-Okul yeniden import'una ALTERNATİF)
# ---------------------------------------------------------------------------
def _build_report(*, graduate_final_level: bool, applied: bool) -> PromotionReport:
    """Sayımları tek yerden üretir — önizleme ve uygulama AYNI raporu döndürür."""
    counts = selectors.active_student_level_counts()
    moves = tuple(
        LevelMove(from_level=lvl, to_level=lvl + 1, count=counts.get(lvl, 0))
        for lvl in range(FIRST_CLASS_LEVEL, FINAL_CLASS_LEVEL)
    )
    final_count = counts.get(FINAL_CLASS_LEVEL, 0)
    out_of_range = sum(
        count
        for lvl, count in counts.items()
        if lvl is not None and not FIRST_CLASS_LEVEL <= lvl <= FINAL_CLASS_LEVEL
    )
    return PromotionReport(
        applied=applied,
        graduate_final_level=graduate_final_level,
        promoted=sum(m.count for m in moves),
        graduated=final_count if graduate_final_level else 0,
        final_level_kept=0 if graduate_final_level else final_count,
        skipped_inactive=selectors.inactive_student_count(),
        skipped_no_level=counts.get(None, 0),
        skipped_out_of_range=out_of_range,
        moves=moves,
    )


@transaction.atomic
def promote_students(*, graduate_final_level: bool = True, apply: bool = False) -> PromotionReport:
    """Aktif öğrencileri bir üst sınıfa taşır. `apply=False` iken HİÇBİR ŞEY yazmaz.

    Kurallar:
    - Yalnız `status=ACTIVE` ve sınıfı 9-12 aralığında olan öğrenciler işlenir;
      sınıfsız / ayrılmış / aralık dışı kayıtlara dokunulmaz (raporda görünür).
    - 12. sınıflar mezun olur: kayıt SİLİNMEZ, `status=LEFT` ("Ayrıldı") olur ve
      `class_level` 12'de kalır (mezun olduğu sınıf geçmiş kaydıdır). Böylece
      geçmiş disiplin dosyaları erişilebilir kalır, `only_active` süzgeçli
      seçiciler (yeni dosya açma) mezunu ÖNERMEZ. Ayrı bir "MEZUN" durumu şema
      değişikliği gerektirir; `LEFT` mevcut şemada en yakın doğru anlamdır.
    - Mezuniyet YÜKSELTMEDEN ÖNCE uygulanır: aksi halde 11'den 12'ye yükselen
      öğrenci aynı koşuda mezun sayılırdı.
    - GERİ ALINAMAZ: eski sınıf bilgisi saklanmaz (tarihçe tablosu yoktur —
      tasarım §4.2). UI onayı bunu açıkça söyler.
    """
    report = _build_report(graduate_final_level=graduate_final_level, applied=apply)
    if not apply:
        return report

    now = timezone.now()
    active = Student.objects.filter(status=StudentStatus.ACTIVE)
    if graduate_final_level:
        active.filter(class_level=FINAL_CLASS_LEVEL).update(
            status=StudentStatus.LEFT, updated_at=now
        )
    # Tek SQL UPDATE: satır bazında çalıştığı için kaydırma (9→10→11) OLMAZ.
    Student.objects.filter(
        status=StudentStatus.ACTIVE,
        class_level__gte=FIRST_CLASS_LEVEL,
        class_level__lt=FINAL_CLASS_LEVEL,
    ).update(class_level=F("class_level") + 1, updated_at=now)
    return report


# ---------------------------------------------------------------------------
# 4. Sihirbaz açılış özeti
# ---------------------------------------------------------------------------
def rollover_status() -> RolloverStatus:
    """Sihirbazın açılışta gösterdiği durum: aktif yıl, öneri, sicil dökümü."""
    active = selectors.active_school_year()
    counts = selectors.active_student_level_counts()
    levels = tuple(
        LevelCount(level=lvl, count=count)
        for lvl, count in sorted(counts.items(), key=lambda item: (item[0] is None, item[0] or 0))
        if lvl is not None
    )
    return RolloverStatus(
        active_school_year=active,
        suggestion=suggest_next_year(active),
        active_student_count=sum(counts.values()),
        students_without_level=counts.get(None, 0),
        level_counts=levels,
    )
