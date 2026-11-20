"""Kurul kararı aşaması kendiliğinden ilerler (kullanıcı kararı, 20.11.2026).

Saha bulgusu: kararları girilmiş, onaylanmış, tebliğ edilmiş ve e-Okul'a işlenmiş dosya
"Müdür değerlendirmesi / sevk" aşamasında kalıyordu — "Kurul kararı" aşama olayı (OYS'den
kalma, dosya düzeyinde ikinci bir karar tipi + metni) elle girilmediği için "Dosyayı kapat"
düğmesi hiç görünmüyordu. Artık hakkında işlem yapılan BÜTÜN öğrencilerin kurul kararı
girilince dosya kendiliğinden COMMITTEE_DONE'a geçer; olayın karar tipi / metni istenmez.
Takılı kalmış eski dosyalar göç 0020 ile aynı kurala göre ilerletilir.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from typing import Any

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from apps.disiplin import services
from apps.disiplin.models import (
    CaseStage,
    DisciplineCase,
    DisciplineCommittee,
    DisciplineDecision,
    DisciplineEvent,
    PenaltyType,
    PrincipalDecision,
)
from apps.disiplin.services.cases import AUTO_COMMITTEE_DONE_NOTE
from apps.disiplin.tests.factories import (
    PersonnelFactory,
    SchoolYearFactory,
    StudentFactory,
    decide,
)

pytestmark = pytest.mark.django_db

PETITION = date(2026, 5, 18)
REFERRED = date(2026, 5, 19)


def _case(n: int = 1) -> tuple[DisciplineCase, list[int]]:
    year = SchoolYearFactory()
    if not DisciplineCommittee.objects.filter(school_year=year).exists():
        services.create_committee(school_year_id=year.pk, chair_id=PersonnelFactory().pk)
    ids = [StudentFactory().pk for _ in range(n)]
    case = services.create_case(
        petition_date=PETITION,
        petitioner_name="İdare",
        petitioner_role="IDARE",
        summary="x",
        student_ids=ids,
    )
    services.add_event(
        case,
        CaseStage.DECIDED,
        REFERRED,
        override=True,
        override_reason="Rehberlik atlandı.",
        principal_decisions=[PrincipalDecision.DISCIPLINE_COMMITTEE],
    )
    case.refresh_from_db()
    return case, ids


def _committee_events(case: DisciplineCase) -> list[DisciplineEvent]:
    return list(case.events.filter(stage=CaseStage.COMMITTEE_DONE))


def test_tek_ogrencide_karar_girilince_kurul_karari_asamasina_gecer() -> None:
    case, (sid,) = _case()
    decide(
        case, student_id=sid, penalty_type=PenaltyType.REPRIMAND, decision_date=date(2026, 5, 22)
    )
    case.refresh_from_db()
    assert case.current_stage == CaseStage.COMMITTEE_DONE
    (event,) = _committee_events(case)
    assert event.event_date == date(2026, 5, 22)  # karar (toplantı) tarihi
    assert event.notes == AUTO_COMMITTEE_DONE_NOTE
    assert event.committee_decision_type is None
    assert event.committee_decision_text == ""
    assert not event.is_override


def test_cok_ogrencide_son_karar_girilene_dek_bekler() -> None:
    case, (a, b) = _case(2)
    decide(case, student_id=a, penalty_type=PenaltyType.REPRIMAND, decision_date=date(2026, 5, 22))
    case.refresh_from_db()
    assert case.current_stage == CaseStage.DECIDED
    assert _committee_events(case) == []
    decide(case, student_id=b, penalty_type=PenaltyType.REPRIMAND, decision_date=date(2026, 5, 25))
    case.refresh_from_db()
    assert case.current_stage == CaseStage.COMMITTEE_DONE
    (event,) = _committee_events(case)
    assert event.event_date == date(2026, 5, 25)  # en geç karar


def test_kurul_karari_asamasinda_dosya_kapatilabilir() -> None:
    case, (sid,) = _case()
    decide(
        case, student_id=sid, penalty_type=PenaltyType.REPRIMAND, decision_date=date(2026, 5, 22)
    )
    case.refresh_from_db()
    services.close_case(case, override=True, override_reason="Test kapanışı.")
    case.refresh_from_db()
    assert case.current_stage == CaseStage.CLOSED


def test_geri_yuklenen_karar_eksigi_tamamlarsa_asama_ilerler() -> None:
    case, (a, b) = _case(2)
    decide(case, student_id=a, penalty_type=PenaltyType.REPRIMAND, decision_date=date(2026, 5, 22))
    d_b = decide(
        case, student_id=b, penalty_type=PenaltyType.REPRIMAND, decision_date=date(2026, 5, 22)
    )
    case.refresh_from_db()
    services.revert_stage(case, target_stage=CaseStage.DECIDED, reason="Yanlış kayıt.")
    services.delete_decision(d_b)
    case.refresh_from_db()
    assert case.current_stage == CaseStage.DECIDED
    services.restore_decision(DisciplineDecision.all_objects.get(pk=d_b.pk))
    case.refresh_from_db()
    assert case.current_stage == CaseStage.COMMITTEE_DONE
    assert len(_committee_events(case)) == 2  # geri alma olayı silmez; yeni olay eklenir


def test_elle_kurul_karari_olayi_karar_tipi_ve_metni_istemez() -> None:
    """Eski elle yol (API) hâlâ geçerli geçiştir; karar tipi / metni artık zorunlu değil."""
    case, _ids = _case()
    services.add_event(case, CaseStage.COMMITTEE_DONE, date(2026, 5, 22))
    case.refresh_from_db()
    assert case.current_stage == CaseStage.COMMITTEE_DONE


# ---------------------------------------------------------------------------
# Göç 0020: takılı kalmış eski dosyalar
# ---------------------------------------------------------------------------
_BEFORE = [("disiplin", "0019_decision_first_penalty")]
_AFTER = [("disiplin", "0020_kurul_asamasi_otomatik")]


@pytest.fixture
def migrator() -> Iterator[None]:
    yield
    executor = MigrationExecutor(connection)
    executor.migrate(executor.loader.graph.leaf_nodes())


def _stuck(case: DisciplineCase) -> None:
    """Eski sürümün bıraktığı durum: kararlar girilmiş, aşama DECIDED, olay yok."""
    DisciplineEvent.all_objects.filter(case=case, stage=CaseStage.COMMITTEE_DONE).delete()
    DisciplineCase.objects.filter(pk=case.pk).update(current_stage=CaseStage.DECIDED)


def _run_migration() -> Any:
    executor = MigrationExecutor(connection)
    executor.migrate(_BEFORE)
    executor = MigrationExecutor(connection)
    executor.migrate(_AFTER)


@pytest.mark.django_db(transaction=True)
def test_goc_0020_takili_dosyayi_ilerletir(migrator: None) -> None:
    takili, (a, b) = _case(2)
    for sid, gun in ((a, date(2026, 5, 22)), (b, date(2026, 5, 26))):
        decide(takili, student_id=sid, penalty_type=PenaltyType.REPRIMAND, decision_date=gun)
    _stuck(takili)

    eksik, (c, _d) = _case(2)  # bir öğrencinin kararı yok → ilerlemez
    decide(eksik, student_id=c, penalty_type=PenaltyType.REPRIMAND, decision_date=date(2026, 5, 22))

    silinmis, (e,) = _case()  # tek kararı silinmiş → ilerlemez
    d_e = decide(
        silinmis, student_id=e, penalty_type=PenaltyType.REPRIMAND, decision_date=date(2026, 5, 22)
    )
    _stuck(silinmis)
    DisciplineDecision.objects.filter(pk=d_e.pk).delete()  # soft-delete

    _run_migration()

    takili.refresh_from_db()
    assert takili.current_stage == CaseStage.COMMITTEE_DONE
    (event,) = _committee_events(takili)
    assert event.event_date == date(2026, 5, 26)
    assert event.notes == AUTO_COMMITTEE_DONE_NOTE

    eksik.refresh_from_db()
    assert eksik.current_stage == CaseStage.DECIDED
    silinmis.refresh_from_db()
    assert silinmis.current_stage == CaseStage.DECIDED
    assert _committee_events(silinmis) == []


@pytest.mark.django_db(transaction=True)
def test_goc_0020_kapali_ve_zaten_ilerlemis_dosyaya_dokunmaz(migrator: None) -> None:
    kapali, (a,) = _case()
    decide(
        kapali, student_id=a, penalty_type=PenaltyType.REPRIMAND, decision_date=date(2026, 5, 22)
    )
    kapali.refresh_from_db()
    services.close_case(kapali, override=True, override_reason="Test.")
    ilerlemis, (b,) = _case()
    decide(
        ilerlemis, student_id=b, penalty_type=PenaltyType.REPRIMAND, decision_date=date(2026, 5, 22)
    )

    _run_migration()

    kapali.refresh_from_db()
    assert kapali.current_stage == CaseStage.CLOSED
    ilerlemis.refresh_from_db()
    assert ilerlemis.current_stage == CaseStage.COMMITTEE_DONE
    assert len(_committee_events(ilerlemis)) == 1  # ikinci olay yazılmadı
