"""Disiplin test fabrikaları — okul sicili + disiplin çekirdeği.

OYS `ogrenci_isleri/tests/factories.py` uyarlaması: User/Parent fabrikaları
yerine `Personnel`; Student düzleştirilmiş modeldir (Enrollment yok).
"""

from __future__ import annotations

from datetime import date

import factory

from apps.disiplin.models import (
    CaseStage,
    DisciplineCase,
    DisciplineCommittee,
    DisciplineDecisionType,
    PetitionerRole,
)
from apps.okul.models import Personnel, SchoolYear, Student


class SchoolYearFactory(factory.django.DjangoModelFactory):  # type: ignore[misc]  # factory_boy tip stub'ı yok; taban Any
    class Meta:
        model = SchoolYear
        django_get_or_create = ("name",)

    name = "2025-2026"
    start_date = date(2025, 9, 8)
    end_date = date(2026, 6, 26)
    is_active = True


class StudentFactory(factory.django.DjangoModelFactory):  # type: ignore[misc]  # factory_boy tip stub'ı yok; taban Any
    class Meta:
        model = Student

    first_name = "EMRE CAN"
    last_name = factory.Sequence(lambda n: f"YILMAZ{n}")
    student_number = factory.Sequence(lambda n: str(1000 + n))
    class_level = 10
    class_section = "A"


class PersonnelFactory(factory.django.DjangoModelFactory):  # type: ignore[misc]  # factory_boy tip stub'ı yok; taban Any
    class Meta:
        model = Personnel

    first_name = "AYŞE"
    last_name = factory.Sequence(lambda n: f"ÖĞRETMEN{n}")
    title = "Öğretmen"
    branch = "Matematik"


class DisciplineDecisionTypeFactory(factory.django.DjangoModelFactory):  # type: ignore[misc]  # factory_boy tip stub'ı yok; taban Any
    class Meta:
        model = DisciplineDecisionType
        django_get_or_create = ("code",)

    code = factory.Sequence(lambda n: f"KARAR_{n}")
    name = "Kınama"
    is_active = True
    sort_order = 10


class DisciplineCaseFactory(factory.django.DjangoModelFactory):  # type: ignore[misc]  # factory_boy tip stub'ı yok; taban Any
    class Meta:
        model = DisciplineCase

    case_no = factory.Sequence(lambda n: f"2025-2026-{n + 1:04d}")
    petition_date = date(2026, 5, 20)
    petitioner_name = "Veli Veliyev"
    petitioner_role = PetitionerRole.IDARE
    summary = "Sınıf içinde uygunsuz davranış."
    current_stage = CaseStage.PETITION


class DisciplineCommitteeFactory(factory.django.DjangoModelFactory):  # type: ignore[misc]  # factory_boy tip stub'ı yok; taban Any
    class Meta:
        model = DisciplineCommittee

    school_year = factory.SubFactory(SchoolYearFactory)
    chair = factory.SubFactory(PersonnelFactory)
