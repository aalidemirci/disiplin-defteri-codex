"""Disiplin modelleri testleri (F2-T1) — clean() kuralları + SQLite koşullu unique'ler.

OYS `test_discipline_models.py`'den uyarlandı; servis-bağımlı testler (create_case)
T3'te ayrı dosyada. Koşullu UniqueConstraint'lerin SQLite partial index'te
GERÇEKTEN çalıştığı burada sabitlenir (tasarım §4.2 — F2'nin açık kabul kriteri).
"""

from __future__ import annotations

from datetime import date

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.disiplin.models import (
    CaseStage,
    CommitteeMemberType,
    CouncilMeeting,
    CouncilType,
    DisciplineCase,
    DisciplineCommittee,
    DisciplineCommitteeMember,
    DisciplineDeadlineExtension,
    DisciplineDecision,
    DisciplineEvent,
    DisciplineParticipant,
    DisciplinePrecaution,
    HonorBoard,
    ParticipantPersonType,
    ParticipantRole,
    PenaltyType,
    PetitionerRole,
    PrincipalDecision,
)
from apps.disiplin.tests.factories import (
    DisciplineCaseFactory,
    DisciplineCommitteeFactory,
    DisciplineDecisionTypeFactory,
    PersonnelFactory,
    SchoolYearFactory,
    StudentFactory,
)

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# DisciplineCase — dosya no + dilekçe veren tutarlılığı
# ---------------------------------------------------------------------------
def test_case_no_benzersiz() -> None:
    DisciplineCaseFactory(case_no="2025-2026-0001")
    with pytest.raises(IntegrityError), transaction.atomic():
        DisciplineCase.objects.create(
            case_no="2025-2026-0001",
            petition_date=date(2026, 5, 20),
            petitioner_name="A",
            petitioner_role="VELI",
            summary="x",
        )


def test_petitioner_clean_ogretmen_personel_ister() -> None:
    """OGRETMEN rolünde personel FK'sı dolu olmalı; öğrenci FK'sı boş olmalı."""
    staff = PersonnelFactory()
    student = StudentFactory()
    case = DisciplineCaseFactory.build(
        petitioner_role=PetitionerRole.OGRETMEN,
        petitioner_user=staff,
        petitioner_student=student,
    )
    with pytest.raises(ValidationError):
        case.clean()


def test_petitioner_clean_veli_ogrenci_fk_uzerinden() -> None:
    """VELI rolü İLGİLİ ÖĞRENCİ FK'sıyla bağlanır (Parent tablosu yok — tasarım §4.2)."""
    student = StudentFactory()
    case = DisciplineCaseFactory.build(
        petitioner_role=PetitionerRole.VELI,
        petitioner_student=student,
    )
    case.clean()  # hata atmamalı

    staff = PersonnelFactory()
    kotu = DisciplineCaseFactory.build(
        petitioner_role=PetitionerRole.VELI,
        petitioner_user=staff,
    )
    with pytest.raises(ValidationError):
        kotu.clean()


def test_petitioner_clean_idare_fk_doldurmaz() -> None:
    staff = PersonnelFactory()
    case = DisciplineCaseFactory.build(petitioner_role=PetitionerRole.IDARE, petitioner_user=staff)
    with pytest.raises(ValidationError):
        case.clean()


# ---------------------------------------------------------------------------
# DisciplineEvent.clean() — aşamaya özgü zorunlu alanlar (OYS AYNEN)
# ---------------------------------------------------------------------------
def test_event_clean_guidance_returned_rapor_zorunlu() -> None:
    case = DisciplineCaseFactory()
    event = DisciplineEvent(
        case=case, stage=CaseStage.GUIDANCE_RETURNED, event_date=date(2026, 5, 21)
    )
    with pytest.raises(ValidationError):
        event.clean()


def test_event_clean_decided_karar_zorunlu() -> None:
    case = DisciplineCaseFactory()
    event = DisciplineEvent(
        case=case,
        stage=CaseStage.DECIDED,
        event_date=date(2026, 5, 21),
        principal_decisions=[],
    )
    with pytest.raises(ValidationError):
        event.clean()


def test_event_clean_decided_tek_secim() -> None:
    case = DisciplineCaseFactory()
    event = DisciplineEvent(
        case=case,
        stage=CaseStage.DECIDED,
        event_date=date(2026, 5, 21),
        principal_decisions=[
            PrincipalDecision.WRITTEN_WARNING,
            PrincipalDecision.DISCIPLINE_COMMITTEE,
        ],
    )
    with pytest.raises(ValidationError):
        event.clean()


def test_event_clean_decided_gecerli() -> None:
    case = DisciplineCaseFactory()
    event = DisciplineEvent(
        case=case,
        stage=CaseStage.DECIDED,
        event_date=date(2026, 5, 21),
        principal_decisions=[PrincipalDecision.WRITTEN_WARNING],
    )
    event.clean()  # hata atmamalı


def test_event_clean_committee_done_alanlar_zorunlu() -> None:
    case = DisciplineCaseFactory()
    event = DisciplineEvent(case=case, stage=CaseStage.COMMITTEE_DONE, event_date=date(2026, 5, 21))
    with pytest.raises(ValidationError):
        event.clean()


def test_event_clean_committee_done_gecerli() -> None:
    case = DisciplineCaseFactory()
    dtype = DisciplineDecisionTypeFactory(code="KINAMA", name="Kınama")
    event = DisciplineEvent(
        case=case,
        stage=CaseStage.COMMITTEE_DONE,
        event_date=date(2026, 5, 21),
        committee_decision_type=dtype,
        committee_decision_text="Kınama verildi.",
    )
    event.clean()


def test_event_clean_override_gerekce_zorunlu() -> None:
    case = DisciplineCaseFactory()
    event = DisciplineEvent(
        case=case, stage=CaseStage.PETITION, event_date=date(2026, 5, 21), is_override=True
    )
    with pytest.raises(ValidationError):
        event.clean()


# ---------------------------------------------------------------------------
# Kurul üyesi clean() — PARENT tipinde FK yok, snapshot ad zorunlu (tasarım §4.2)
# ---------------------------------------------------------------------------
def test_uye_clean_ogretmen_personel_ister() -> None:
    committee = DisciplineCommitteeFactory()
    member = DisciplineCommitteeMember(committee=committee, member_type=CommitteeMemberType.TEACHER)
    with pytest.raises(ValidationError):
        member.clean()


def test_uye_clean_veli_yalniz_snapshot_adla() -> None:
    committee = DisciplineCommitteeFactory()
    member = DisciplineCommitteeMember(
        committee=committee,
        member_type=CommitteeMemberType.PARENT,
        member_name="HASAN VELİ",
    )
    member.clean()  # FK gerekmez — ad snapshot yeter

    adsiz = DisciplineCommitteeMember(committee=committee, member_type=CommitteeMemberType.PARENT)
    with pytest.raises(ValidationError):
        adsiz.clean()


def test_uye_clean_ogrenci_uyede_personel_bos_olmali() -> None:
    committee = DisciplineCommitteeFactory()
    member = DisciplineCommitteeMember(
        committee=committee,
        member_type=CommitteeMemberType.STUDENT,
        member_student=StudentFactory(),
        member_user=PersonnelFactory(),
    )
    with pytest.raises(ValidationError):
        member.clean()


# ---------------------------------------------------------------------------
# Katılımcı clean() + tedbir clean()
# ---------------------------------------------------------------------------
def test_katilimci_clean_dis_kiside_ad_zorunlu() -> None:
    case = DisciplineCaseFactory()
    p = DisciplineParticipant(
        case=case,
        role=ParticipantRole.WITNESS,
        person_type=ParticipantPersonType.EXTERNAL,
    )
    with pytest.raises(ValidationError):
        p.clean()


def test_tedbir_clean_sure_araligi() -> None:
    case = DisciplineCaseFactory()
    p = DisciplinePrecaution(
        case=case,
        student=StudentFactory(),
        start_date=date(2026, 5, 20),
        requested_days=11,  # md. 175/1 üstü
        end_date=date(2026, 6, 3),
        process_start_deadline=date(2026, 5, 25),
    )
    with pytest.raises(ValidationError):
        p.clean()


# ---------------------------------------------------------------------------
# SQLite koşullu unique regresyonları (tasarım §4.2 — F2 kabul kriteri)
# ---------------------------------------------------------------------------
def _decision(case: DisciplineCase, student_pk: int) -> DisciplineDecision:
    decision: DisciplineDecision = DisciplineDecision.objects.create(
        case=case,
        student_id=student_pk,
        penalty_type=PenaltyType.REPRIMAND,
        decision_date=date(2026, 5, 22),
        approval_authority="PRINCIPAL",
    )
    return decision


def test_dosya_basina_ogrenciye_tek_canli_karar() -> None:
    case = DisciplineCaseFactory()
    student = StudentFactory()
    first = _decision(case, student.pk)
    with pytest.raises(IntegrityError), transaction.atomic():
        _decision(case, student.pk)
    first.delete()  # soft delete → kısıt serbest kalır
    _decision(case, student.pk)
    assert DisciplineDecision.objects.count() == 1
    assert DisciplineDecision.all_objects.count() == 2


def test_ayni_ogrenci_ayni_rolde_iki_kez_eklenemez() -> None:
    case = DisciplineCaseFactory()
    student = StudentFactory()
    DisciplineParticipant.objects.create(
        case=case,
        role=ParticipantRole.ACCUSED,
        person_type=ParticipantPersonType.STUDENT,
        student=student,
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        DisciplineParticipant.objects.create(
            case=case,
            role=ParticipantRole.ACCUSED,
            person_type=ParticipantPersonType.STUDENT,
            student=student,
        )


def test_ogrenciye_ayni_anda_tek_aktif_tedbir() -> None:
    case = DisciplineCaseFactory()
    student = StudentFactory()
    DisciplinePrecaution.objects.create(
        case=case,
        student=student,
        start_date=date(2026, 5, 20),
        requested_days=5,
        end_date=date(2026, 5, 26),
        process_start_deadline=date(2026, 5, 25),
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        DisciplinePrecaution.objects.create(
            case=case,
            student=student,
            start_date=date(2026, 5, 21),
            requested_days=3,
            end_date=date(2026, 5, 25),
            process_start_deadline=date(2026, 5, 26),
        )


def test_ders_yili_basina_tek_canli_disiplin_kurulu() -> None:
    year = SchoolYearFactory()
    DisciplineCommittee.objects.create(school_year=year, chair=PersonnelFactory())
    with pytest.raises(IntegrityError), transaction.atomic():
        DisciplineCommittee.objects.create(school_year=year, chair=PersonnelFactory())


def test_ders_yili_basina_tek_canli_onur_kurulu() -> None:
    year = SchoolYearFactory()
    HonorBoard.objects.create(school_year=year, chair=PersonnelFactory())
    with pytest.raises(IntegrityError), transaction.atomic():
        HonorBoard.objects.create(school_year=year, chair=PersonnelFactory())


def test_dosya_basina_tek_canli_sure_uzatmasi() -> None:
    case = DisciplineCaseFactory()
    DisciplineDeadlineExtension.objects.create(
        case=case,
        requested_days=5,
        reason="İfade gecikmesi",
        decided_on=date(2026, 5, 22),
        original_deadline=date(2026, 6, 3),
        new_deadline=date(2026, 6, 10),
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        DisciplineDeadlineExtension.objects.create(
            case=case,
            requested_days=3,
            reason="İkinci uzatma (md. 192/3 yasak)",
            decided_on=date(2026, 5, 23),
            original_deadline=date(2026, 6, 3),
            new_deadline=date(2026, 6, 13),
        )


def test_toplanti_no_yil_tur_basina_benzersiz() -> None:
    year = SchoolYearFactory()
    CouncilMeeting.objects.create(
        school_year=year,
        council_type=CouncilType.DISCIPLINE,
        meeting_no=1,
        meeting_date=date(2026, 5, 22),
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        CouncilMeeting.objects.create(
            school_year=year,
            council_type=CouncilType.DISCIPLINE,
            meeting_no=1,
            meeting_date=date(2026, 5, 29),
        )
    # Farklı kurul türünde aynı no serbest.
    CouncilMeeting.objects.create(
        school_year=year,
        council_type=CouncilType.HONOR,
        meeting_no=1,
        meeting_date=date(2026, 5, 29),
    )
