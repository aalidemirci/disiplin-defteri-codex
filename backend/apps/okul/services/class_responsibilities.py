"""Sınıf sorumluluğu eşleştirmelerinin yazma işlemleri."""

from __future__ import annotations

from typing import Any

from django.db import transaction

from apps.okul.models import ClassResponsibility


@transaction.atomic
def create_class_responsibility(**fields: Any) -> ClassResponsibility:
    responsibility: ClassResponsibility = ClassResponsibility.objects.create(**fields)
    return responsibility


@transaction.atomic
def update_class_responsibility(
    responsibility: ClassResponsibility, **fields: Any
) -> ClassResponsibility:
    changed = [name for name, value in fields.items() if getattr(responsibility, name) != value]
    if changed:
        for name in changed:
            setattr(responsibility, name, fields[name])
        responsibility.save(update_fields=[*changed, "updated_at"])
    return responsibility


@transaction.atomic
def delete_class_responsibility(responsibility: ClassResponsibility) -> None:
    responsibility.delete()
