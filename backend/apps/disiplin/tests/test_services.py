"""Disiplin dosya servisleri testleri (F2-T3) — OYS test davranışlarının uyarlaması.

OYS'den düşenler: rol/izin testleri (authsuz tek kullanıcı), sinyal/audit
doğrulamaları. Durum makinesi + otomatik kapanış + kapanış uygunluğu AYNEN.
"""

from __future__ import annotations

from datetime import date

import pytest

from apps.disiplin import selectors, services
from apps.disiplin.models import (
    CaseStage,
    DisciplineCase,
    DisciplineCaseStudent,
    DisciplineParticipant,
    ParticipantRole,
    PetitionerRole,
    PrincipalDecision,
)
from apps.disiplin.state_machine import InvalidTransitionError
from apps.disiplin.tests.factories import (
    DisciplineCaseFactory,
    PersonnelFactory,
    SchoolYearFactory,
    StudentFactory,
)

pytestmark = pytest.mark.django_db


def _case_with_student() -> tuple[DisciplineCase, int]:
    SchoolYearFactory()  # aktif ders yılı (case_no üretimi ister)
    s = StudentFactory()
    case = services.create_case(
        petition_date=date(2026, 5, 20),
        petitioner_name="A",
        petitioner_role="IDARE",
        summary="x",
        student_ids=[s.pk],
    )
    return case, s.pk


# ---------------------------------------------------------------------------
# create_case + case_no
# ---------------------------------------------------------------------------
def test_case_no_uretimi_sirali() -> None:
    year = SchoolYearFactory()
    s = StudentFactory()
    c1 = services.create_case(
        petition_date=date(2026, 5, 20),
        petitioner_name="A",
        petitioner_role="VELI",
        petitioner_student_id=s.pk,
        summary="x",
        student_ids=[s.pk],
    )
    c2 = services.create_case(
        petition_date=date(2026, 5, 21),
        petitioner_name="B",
        petitioner_role="IDARE",
        summary="y",
        student_ids=[s.pk],
    )
    assert c1.case_no == f"{year.name}-0001"
    assert c2.case_no == f"{year.name}-0002"


def test_case_no_aktif_ders_yili_yoksa_hata() -> None:
    s = StudentFactory()
    with pytest.raises(ValueError, match="Aktif ders yılı"):
        services.create_case(
            petition_date=date(2026, 5, 20),
            petitioner_name="A",
            petitioner_role="IDARE",
            summary="x",
            student_ids=[s.pk],
        )


def test_case_no_eski_seri_izole() -> None:
    """Eski biçim ('2026-0007') yeni ders-yılı serisini ETKİLEMEZ; eski no değişmez."""
    year = SchoolYearFactory()
    s = StudentFactory()
    DisciplineCaseFactory(case_no="2026-0007")
    c = services.create_case(
        petition_date=date(2026, 5, 20),
        petitioner_name="A",
        petitioner_role="IDARE",
        summary="x",
        student_ids=[s.pk],
    )
    assert c.case_no == f"{year.name}-0001"
    assert DisciplineCase.objects.filter(case_no="2026-0007").exists()


def test_coklu_ogrenci_ve_accused_senkron() -> None:
    SchoolYearFactory()
    s1 = StudentFactory()
    s2 = StudentFactory()
    case = services.create_case(
        petition_date=date(2026, 5, 20),
        petitioner_name="A",
        petitioner_role="IDARE",
        summary="ortak olay",
        student_ids=[s1.pk, s2.pk],
    )
    assert DisciplineCaseStudent.objects.filter(case=case).count() == 2
    # Suçlanan roster'ı katılımcı tablosuyla senkron kuruldu.
    assert (
        DisciplineParticipant.objects.filter(case=case, role=ParticipantRole.ACCUSED).count() == 2
    )


def test_create_case_ogrencisiz_hata() -> None:
    SchoolYearFactory()
    with pytest.raises(ValueError):
        services.create_case(
            petition_date=date(2026, 5, 20),
            petitioner_name="A",
            petitioner_role="IDARE",
            summary="x",
            student_ids=[],
        )


def test_create_case_ogretmen_dilekcesi_personel_fk() -> None:
    SchoolYearFactory()
    s = StudentFactory()
    teacher = PersonnelFactory()
    case = services.create_case(
        petition_date=date(2026, 5, 20),
        petitioner_name="",
        petitioner_role=PetitionerRole.OGRETMEN,
        petitioner_user_id=teacher.pk,
        summary="x",
        student_ids=[s.pk],
    )
    assert case.petitioner_user_id == teacher.pk
    assert case.petitioner_name == teacher.full_name  # snapshot otomatik dolduruldu


# ---------------------------------------------------------------------------
# add_event — durum makinesi + otomatik kapanış
# ---------------------------------------------------------------------------
def test_add_event_gecerli_gecis() -> None:
    case, _sid = _case_with_student()
    services.add_event(
        case,
        CaseStage.GUIDANCE_REFERRED,
        date(2026, 5, 21),
        assigned_guidance_name="REHBER HOCA",
    )
    case.refresh_from_db()
    assert case.current_stage == CaseStage.GUIDANCE_REFERRED


def test_add_event_gecersiz_gecis_hata() -> None:
    case, _sid = _case_with_student()
    with pytest.raises(InvalidTransitionError):
        services.add_event(case, CaseStage.COMMITTEE_DONE, date(2026, 5, 21))


def test_add_event_override_gerekce_ister() -> None:
    case, _sid = _case_with_student()
    with pytest.raises(ValueError, match="gerekçe"):
        services.add_event(
            case,
            CaseStage.DECIDED,
            date(2026, 5, 21),
            override=True,
            principal_decisions=[PrincipalDecision.DISCIPLINE_COMMITTEE],
        )


def test_add_event_override_gerekceyle_deler() -> None:
    """PETITION → DECIDED (rehberlik atlama) yalnız override ile — izi olayda kalır."""
    case, _sid = _case_with_student()
    event = services.add_event(
        case,
        CaseStage.DECIDED,
        date(2026, 5, 21),
        override=True,
        override_reason="Rehberlik süreci gerekmiyor (acil durum).",
        principal_decisions=[PrincipalDecision.DISCIPLINE_COMMITTEE],
    )
    assert event.is_override is True
    assert event.override_reason
    case.refresh_from_db()
    assert case.current_stage == CaseStage.DECIDED


def test_yalniz_yazili_uyari_dosyayi_otomatik_kapatir() -> None:
    case, _sid = _case_with_student()
    services.add_event(
        case,
        CaseStage.DECIDED,
        date(2026, 5, 21),
        override=True,
        override_reason="Rehberlik atlandı.",
        principal_decisions=[PrincipalDecision.WRITTEN_WARNING],
    )
    case.refresh_from_db()
    assert case.current_stage == CaseStage.CLOSED
    assert case.closed_at is not None


def test_kurula_sevk_dosyayi_kapatmaz() -> None:
    case, _sid = _case_with_student()
    services.add_event(
        case,
        CaseStage.DECIDED,
        date(2026, 5, 21),
        override=True,
        override_reason="Rehberlik atlandı.",
        principal_decisions=[PrincipalDecision.DISCIPLINE_COMMITTEE],
    )
    case.refresh_from_db()
    assert case.current_stage == CaseStage.DECIDED
    assert case.closed_at is None


# ---------------------------------------------------------------------------
# revert_stage + close_case + rehber güncelleme
# ---------------------------------------------------------------------------
def test_revert_stage_gerekce_zorunlu() -> None:
    case, _sid = _case_with_student()
    services.add_event(case, CaseStage.GUIDANCE_REFERRED, date(2026, 5, 21))
    with pytest.raises(ValueError, match="gerekçe"):
        services.revert_stage(case, target_stage=CaseStage.PETITION, reason=" ")


def test_revert_stage_karar_varken_karar_oncesine_engel() -> None:
    case, sid = _case_with_student()
    services.add_event(
        case,
        CaseStage.DECIDED,
        date(2026, 5, 21),
        override=True,
        override_reason="atla",
        principal_decisions=[PrincipalDecision.DISCIPLINE_COMMITTEE],
    )
    services.record_decision(
        case, student_id=sid, penalty_type="REPRIMAND", decision_date=date(2026, 5, 22)
    )
    with pytest.raises(ValueError, match="resmî karar"):
        services.revert_stage(case, target_stage=CaseStage.PETITION, reason="geri al")


def test_close_case_karar_yoksa_hemen_uygun() -> None:
    case, _sid = _case_with_student()
    services.add_event(
        case,
        CaseStage.DECIDED,
        date(2026, 5, 21),
        override=True,
        override_reason="atla",
        principal_decisions=[PrincipalDecision.HONOR_COMMITTEE],
    )
    services.close_case(case)
    case.refresh_from_db()
    assert case.current_stage == CaseStage.CLOSED


def test_close_case_tebligsiz_karar_bloke_eder() -> None:
    case, sid = _case_with_student()
    services.add_event(
        case,
        CaseStage.DECIDED,
        date(2026, 5, 21),
        override=True,
        override_reason="atla",
        principal_decisions=[PrincipalDecision.DISCIPLINE_COMMITTEE],
    )
    services.record_decision(
        case, student_id=sid, penalty_type="REPRIMAND", decision_date=date(2026, 5, 22)
    )
    with pytest.raises(ValueError, match="kapatılamaz"):
        services.close_case(case)
    # Erken kapatma gerekçeyle mümkün.
    services.close_case(case, override=True, override_reason="Veli feragat etti.")
    case.refresh_from_db()
    assert case.current_stage == CaseStage.CLOSED


def test_update_guidance_assignee() -> None:
    case, _sid = _case_with_student()
    services.add_event(
        case, CaseStage.GUIDANCE_REFERRED, date(2026, 5, 21), assigned_guidance_name="ESKİ REHBER"
    )
    assert services.update_guidance_assignee(case, name="YENİ REHBER") is True
    latest = case.events.filter(stage=CaseStage.GUIDANCE_REFERRED).latest("recorded_at")
    assert latest.assigned_guidance_name == "YENİ REHBER"
    assert services.update_guidance_assignee(case, name="YENİ REHBER") is False  # değişiklik yok


def test_all_cases_asama_filtresi() -> None:
    case, _sid = _case_with_student()
    assert selectors.all_cases(stage=CaseStage.PETITION).count() == 1
    assert selectors.all_cases(stage=CaseStage.CLOSED).count() == 0
    assert selectors.all_cases(search=case.case_no).count() == 1
