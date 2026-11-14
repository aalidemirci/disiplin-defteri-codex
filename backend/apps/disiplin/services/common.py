"""Disiplin servisleri ortak yardımcıları (alt-modüller arası paylaşılan; yaprak modül).

OYS `discipline_common.py` uyarlaması: `_audit_write`/`user_or_none` SİLİNDİ
(denetim modülü ve kullanıcı kavramı yok).
"""

from __future__ import annotations

from datetime import date

from django.utils import timezone

from apps.disiplin.models import DisciplineCase


def assert_not_future(value: date, label: str, *, message: str | None = None) -> None:
    """Tarih bugünden ileri olamaz — "ileri tarih olamaz" denetiminin TEK yeri.

    "Bugün" YEREL tarihtir (`timezone.localdate()`, §7.1): UTC'den türetilirse Türkiye'de
    gece 00:00-02:59 arasında bir gün geri kayar ve o gün girilen kayıt "ileri tarihli"
    diye reddedilirdi. Geçmişe dönük (geç girilen) kayıt serbesttir.
    `message` verilirse o ileti kullanılır (bağlama özgü yönlendirme gerektiğinde).
    """
    if value > timezone.localdate():
        raise ValueError(
            message or f"{label} bugünden ileri olamaz ({value:%d.%m.%Y}); tarihi kontrol edin."
        )


def case_has_student(case: DisciplineCase, student_id: int) -> bool:
    """Öğrenci bu dosyaya dahil mi (DisciplineCaseStudent)?"""
    return case.case_students.filter(student_id=student_id).exists()
