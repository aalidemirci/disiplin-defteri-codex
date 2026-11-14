"""Öğrenci/Personel elle kayıt işlemleri (F1-T6; tasarım §4.7/6).

İnce servis katmanı — doğrulama/normalize serializer'da (TCKN checksum, telefon
biçimi), yazma burada. View ORM çağırmaz (katman disiplini).
"""

from __future__ import annotations

from typing import Any

from django.db import transaction

from apps.okul.models import Personnel, Student


def _assert_tckn_unique(tckn: object, *, exclude_pk: int | None = None) -> None:
    """TCKN tekilliği — şifreli kipte DB kısıtı etkisizdir (borç K1), servis korur.

    Aynı TCKN'li ikinci kayıt öğrencinin disiplin geçmişini böler (md. 157/7,
    166 tekrar triajı, davranış puanı, onur uygunluğu yanlış hesaplanır).
    """
    from apps.okul import selectors

    value = str(tckn or "").strip()
    if not value:
        return
    existing = selectors.find_student_by_tckn(value)
    if existing is not None and existing.pk != exclude_pk:
        raise ValueError("Bu T.C. kimlik numarasıyla kayıtlı bir öğrenci zaten var.")


@transaction.atomic
def create_student(**fields: Any) -> Student:
    _assert_tckn_unique(fields.get("tckn"))
    student: Student = Student.objects.create(**fields)
    return student


@transaction.atomic
def update_student(student: Student, **fields: Any) -> Student:
    if "tckn" in fields and fields["tckn"] != student.tckn:
        _assert_tckn_unique(fields["tckn"], exclude_pk=student.pk)
    changed = [name for name, value in fields.items() if getattr(student, name) != value]
    if changed:
        for name in changed:
            setattr(student, name, fields[name])
        student.save(update_fields=[*changed, "updated_at"])
    return student


def _assert_student_deletable(student: Student) -> None:
    """Disiplin kaydı olan öğrenci sicilden silinmez.

    Silinen öğrenci listelerden düşer ama dosyası, kararı ve uyarı kaydı durur:
    evrak üretimi, davranış puanı ve md. 157/7-e / 166 tekrar triajı sahipsiz kalır.
    Okuldan ayrılan öğrenci SİLİNMEZ, durumu "Ayrıldı" ya da "Mezun" yapılır.
    """
    # Yerel içe aktarım: okul → disiplin bağımlılığı yalnız bu korumada (döngüsel import).
    from apps.disiplin.models import DisciplineCase, DisciplineDecision, DisciplineWarning

    if DisciplineCase.objects.filter(
        case_students__student_id=student.pk, closed_at__isnull=True
    ).exists():
        reason = "açık disiplin dosyası"
    elif DisciplineDecision.objects.filter(student_id=student.pk).exists():
        reason = "disiplin kararı"
    elif DisciplineWarning.objects.filter(student_id=student.pk).exists():
        reason = "müdür uyarı kaydı"
    else:
        return
    raise ValueError(
        f"Bu öğrencinin {reason} var; sicilden silinemez. Öğrenci okuldan ayrıldıysa "
        'silmek yerine öğrenci kartında durumunu "Ayrıldı" ya da "Mezun" yapın.'
    )


@transaction.atomic
def delete_student(student: Student) -> None:
    _assert_student_deletable(student)
    student.delete()  # soft delete (BaseModel)


@transaction.atomic
def create_personnel(**fields: Any) -> Personnel:
    person: Personnel = Personnel.objects.create(**fields)
    return person


@transaction.atomic
def update_personnel(person: Personnel, **fields: Any) -> Personnel:
    changed = [name for name, value in fields.items() if getattr(person, name) != value]
    if changed:
        for name in changed:
            setattr(person, name, fields[name])
        person.save(update_fields=[*changed, "updated_at"])
    return person


@transaction.atomic
def delete_personnel(person: Personnel) -> None:
    person.delete()  # soft delete (BaseModel)
