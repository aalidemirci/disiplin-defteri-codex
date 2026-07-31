"""`okul` salt-okunur sorguları — view'lar ORM'e buradan erişir (katman disiplini).

Arama Türkçe-katlamalı yapılır: `normalize_header` (Türkçe→ASCII küçük harf) iki
tarafı da katlar; SQLite LIKE yalnız ASCII'de harf-duyarsız olduğundan 'yılmaz'
araması 'YILMAZ' kaydını DB filtresiyle bulamazdı. Yerel ölçek (≤1000 kayıt)
Python tarafı filtrelemeyi sorunsuz kılar; sayfalama listeyle de çalışır.
"""

from __future__ import annotations

from typing import Any, cast

from django.db.models import Count, QuerySet

from apps.okul import normalize
from apps.okul.excel_veli import normalize_header
from apps.okul.models import (
    ClassResponsibility,
    Holiday,
    ImportRun,
    Personnel,
    SchoolConfig,
    SchoolTerm,
    SchoolYear,
    Student,
    StudentStatus,
)
from apps.okul.services import app_password
from shared import crypto


def school_years() -> QuerySet[SchoolYear]:
    return SchoolYear.objects.all()


def active_school_year() -> SchoolYear | None:
    return SchoolYear.objects.filter(is_active=True).first()


def school_terms(*, school_year_id: int) -> QuerySet[SchoolTerm]:
    return SchoolTerm.objects.filter(school_year_id=school_year_id)


def holidays() -> QuerySet[Holiday]:
    return Holiday.objects.all()


def personnel_list(*, search: str = "") -> list[Personnel] | QuerySet[Personnel]:
    qs = Personnel.objects.all()
    if search.strip():
        needle = normalize_header(search)
        return [
            p
            for p in qs
            if needle in normalize_header(p.full_name)
            or needle in normalize_header(p.title)
            or needle in normalize_header(p.branch)
        ]
    return qs


def class_responsibilities(*, school_year_id: int | None = None) -> QuerySet[ClassResponsibility]:
    """Ders yılının sınıf sorumlulukları; yıl verilmezse aktif yıl kullanılır."""
    qs = ClassResponsibility.objects.select_related(
        "school_year",
        "class_teacher",
        "assistant_principal",
        "guidance_teacher",
    )
    if school_year_id is not None:
        return qs.filter(school_year_id=school_year_id)
    active = active_school_year()
    if active is None:
        return qs.none()
    return qs.filter(school_year=active)


def class_responsibilities_all() -> QuerySet[ClassResponsibility]:
    """Detay/güncelleme uçları için bütün canlı eşleştirmeler."""
    return ClassResponsibility.objects.select_related(
        "school_year",
        "class_teacher",
        "assistant_principal",
        "guidance_teacher",
    )


def student_list(
    *,
    class_level: int | None = None,
    class_section: str = "",
    search: str = "",
    only_active: bool = False,
) -> list[Student] | QuerySet[Student]:
    """Öğrenci listesi. `only_active` VARSAYILAN OLARAK KAPALIDIR.

    Sicil ekranı ayrılmış öğrenciyi de göstermek zorundadır (geçmiş dosyaların
    öğrencisi kaybolmasın); süzgeci yalnız YENİ kayıt bağlayan seçiciler
    (autocomplete) açar — ayrılmış öğrenciye yeni dosya açılmasın.
    """
    qs = Student.objects.all()
    if only_active:
        qs = qs.filter(status=StudentStatus.ACTIVE)
    if class_level is not None:
        qs = qs.filter(class_level=class_level)
    if class_section.strip():
        # Kayıtlar import/serializer'da _ascii_upper ile katlanır ('ş' → 'S');
        # filtre de AYNI katlamadan geçmeli, yoksa Türkçe harfli şube bulunamaz.
        qs = qs.filter(class_section=normalize._ascii_upper(class_section.strip()))
    if search.strip():
        needle = normalize_header(search)
        return [
            s
            for s in qs
            if needle in normalize_header(s.full_name)
            or needle in normalize_header(s.student_number)
        ]
    return qs


def get_student(student_id: int) -> Student | None:
    """Tek öğrenci (canlı) — yoksa None. Disiplin modülünün okuma kanalı."""
    return Student.objects.filter(pk=student_id).first()


def find_student_by_tckn(tckn: str) -> Student | None:
    """TCKN ile canlı öğrenci arar (içe aktarma upsert'inin eşleştirme kanalı).

    Şifreleme AÇIKKEN `Student.objects.filter(tckn=...)` DAİMA BOŞ döner: Fernet
    aynı metni her seferinde farklı token'a çevirir (blind index alınmadı —
    tasarım §10.2). Bu yüzden kilit açıkken eşleştirme Python tarafında yapılır;
    yerel ölçek (≤1000 öğrenci) bunu ucuzlatır.

    Veri şifreliyken kilit AÇILMAMIŞSA eşleştirme yapılamaz; sessizce "bulunamadı"
    dönmek içe aktarmada KOPYA öğrenci yaratırdı → hata yükseltilir (API kapısı
    zaten 423 verir, bu ikinci hattır: yönetim komutları/betikler için).
    """
    aranan = (tckn or "").strip()
    if not aranan:
        return None
    if app_password.is_locked():
        raise ValueError(
            "Kayıtlar uygulama parolasıyla kilitli; içe aktarma için önce kilidi açın."
        )
    if crypto.writes_encrypted():
        adaylar = cast("QuerySet[Student]", Student.objects.exclude(tckn=""))
        for ogrenci in adaylar:
            if ogrenci.tckn == aranan:
                return ogrenci
        return None
    return Student.objects.filter(tckn=aranan).first()


def get_personnel(personnel_id: int) -> Personnel | None:
    """Tek personel (canlı) — yoksa None. Disiplin modülünün okuma kanalı."""
    return Personnel.objects.filter(pk=personnel_id).first()


def get_school_year(school_year_id: int) -> SchoolYear | None:
    """Tek ders yılı (canlı) — yoksa None. Disiplin modülünün okuma kanalı."""
    return SchoolYear.objects.filter(pk=school_year_id).first()


def students_all() -> QuerySet[Student]:
    return Student.objects.all()


def import_runs(*, source_type: str = "") -> QuerySet[ImportRun]:
    qs = ImportRun.objects.all()
    if source_type:
        qs = qs.filter(source_type=source_type)
    return qs


def setup_status() -> dict[str, Any]:
    """Kurulum sihirbazı durum özeti (FE açılış yönlendirmesi bundan okur)."""
    config = SchoolConfig.load()
    return {
        "setup_completed": config.setup_completed,
        "school_name": config.school_name,
        "has_active_school_year": active_school_year() is not None,
        "student_count": Student.objects.count(),
        "personnel_count": Personnel.objects.count(),
        "holiday_count": Holiday.objects.count(),
    }


def distinct_class_levels() -> list[int]:
    """Sicilde fiilen kayıtlı sınıf seviyeleri (artan, tekilleştirilmiş).

    Sınıfı girilmemiş (`class_level=None`) öğrenciler listeyi kirletmez.
    """
    values = Student.objects.exclude(class_level=None).values_list("class_level", flat=True)
    return sorted({int(v) for v in values})


def active_student_level_counts() -> dict[int | None, int]:
    """Aktif öğrencilerin sınıf seviyesine göre sayımı — sınıfsızlar `None` anahtarında.

    Yıl devri sihirbazının toplu sınıf yükseltme önizlemesi
    (`services.year_rollover`) bu dökümden beslenir: seviyesi girilmemiş kayıtlar
    sessizce kaybolmasın, raporda ayrı satır olarak görünsün.
    """
    rows = (
        Student.objects.filter(status=StudentStatus.ACTIVE)
        .values_list("class_level")
        .annotate(total=Count("id"))
    )
    return {(None if level is None else int(level)): int(total) for level, total in rows}


def inactive_student_count() -> int:
    """Ayrılmış (pasif) öğrenci sayısı — toplu sınıf yükseltme bunlara DOKUNMAZ."""
    return Student.objects.exclude(status=StudentStatus.ACTIVE).count()
