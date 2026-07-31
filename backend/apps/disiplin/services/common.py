"""Disiplin servisleri ortak yardımcıları (alt-modüller arası paylaşılan; yaprak modül).

OYS `discipline_common.py` uyarlaması: `_audit_write`/`user_or_none` SİLİNDİ
(denetim modülü ve kullanıcı kavramı yok).
"""

from __future__ import annotations

from apps.disiplin.models import DisciplineCase


def case_has_student(case: DisciplineCase, student_id: int) -> bool:
    """Öğrenci bu dosyaya dahil mi (DisciplineCaseStudent)?"""
    return case.case_students.filter(student_id=student_id).exists()
