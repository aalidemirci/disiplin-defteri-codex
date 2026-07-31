"""Katılımcı + müdür uyarısı testleri (F2) — md. 157/7, 193."""

from __future__ import annotations

from datetime import date

import pytest

from apps.disiplin import services
from apps.disiplin.models import (
    CaseStage,
    DisciplineCase,
    DisciplineCaseStudent,
    ParticipantPersonType,
    ParticipantRole,
    PrincipalDecision,
)
from apps.disiplin.tests.factories import PersonnelFactory, SchoolYearFactory, StudentFactory

pytestmark = pytest.mark.django_db


def _case() -> tuple[DisciplineCase, int]:
    SchoolYearFactory()
    s = StudentFactory()
    case = services.create_case(
        petition_date=date(2026, 5, 18),
        petitioner_name="A",
        petitioner_role="IDARE",
        summary="x",
        student_ids=[s.pk],
    )
    return case, s.pk


def test_taniklar_uc_tipte_eklenir() -> None:
    case, _sid = _case()
    ogrenci = StudentFactory()
    personel = PersonnelFactory()
    services.add_participant(
        case,
        role=ParticipantRole.WITNESS,
        person_type=ParticipantPersonType.STUDENT,
        person_id=ogrenci.pk,
    )
    p2 = services.add_participant(
        case,
        role=ParticipantRole.WITNESS,
        person_type=ParticipantPersonType.STAFF,
        person_id=personel.pk,
    )
    p3 = services.add_participant(
        case,
        role=ParticipantRole.WITNESS,
        person_type=ParticipantPersonType.EXTERNAL,
        external_name="MAHALLE ESNAFI",
        external_title="esnaf",
    )
    assert p2.name_snapshot == personel.full_name
    assert p3.external_name == "MAHALLE ESNAFI"
    assert case.participants.filter(role=ParticipantRole.WITNESS).count() == 3


def test_ayni_kisi_ayni_rolde_iki_kez_eklenemez() -> None:
    case, _sid = _case()
    ogrenci = StudentFactory()
    services.add_participant(
        case,
        role=ParticipantRole.VICTIM,
        person_type=ParticipantPersonType.STUDENT,
        person_id=ogrenci.pk,
    )
    with pytest.raises(ValueError, match="zaten eklenmiş"):
        services.add_participant(
            case,
            role=ParticipantRole.VICTIM,
            person_type=ParticipantPersonType.STUDENT,
            person_id=ogrenci.pk,
        )


def test_accused_eklenince_through_senkron() -> None:
    case, _sid = _case()
    yeni = StudentFactory()
    services.add_participant(
        case,
        role=ParticipantRole.ACCUSED,
        person_type=ParticipantPersonType.STUDENT,
        person_id=yeni.pk,
    )
    assert DisciplineCaseStudent.objects.filter(case=case, student=yeni).exists()


def test_son_suclanan_cikarilamaz_ve_kararli_cikarilamaz() -> None:
    case, sid = _case()
    tek = case.participants.get(role=ParticipantRole.ACCUSED)
    with pytest.raises(ValueError, match="en az bir"):
        services.remove_participant(tek)

    # İkinci suçlanan ekle → ilki çıkarılabilir; ama karar verilmişse çıkarılamaz.
    yeni = StudentFactory()
    services.add_participant(
        case,
        role=ParticipantRole.ACCUSED,
        person_type=ParticipantPersonType.STUDENT,
        person_id=yeni.pk,
    )
    services.add_event(
        case,
        CaseStage.DECIDED,
        date(2026, 5, 19),
        override=True,
        override_reason="atla",
        principal_decisions=[PrincipalDecision.DISCIPLINE_COMMITTEE],
    )
    services.record_decision(
        case, student_id=sid, penalty_type="REPRIMAND", decision_date=date(2026, 5, 22)
    )
    with pytest.raises(ValueError, match="karar verilmiş"):
        services.remove_participant(tek)

    # Kararsız olan (yeni) çıkarılabilir → through satırı da kalkar.
    yeni_p = case.participants.get(role=ParticipantRole.ACCUSED, student=yeni)
    services.remove_participant(yeni_p)
    assert not DisciplineCaseStudent.objects.filter(case=case, student=yeni).exists()


def test_mudur_uyarisi_kurallari() -> None:
    case, sid = _case()
    with pytest.raises(ValueError, match="gerekçesi"):
        services.issue_warning(case, student_id=sid, warning_date=date(2026, 5, 19), summary="  ")
    warning = services.issue_warning(
        case,
        student_id=sid,
        warning_date=date(2026, 5, 19),
        summary="İlk kez kınamalık davranış; dikkat çekildi (md. 157/7).",
    )
    assert warning.pk is not None
    disaridan = StudentFactory()
    with pytest.raises(ValueError, match="dahil değil"):
        services.issue_warning(
            case, student_id=disaridan.pk, warning_date=date(2026, 5, 19), summary="x"
        )
