"""'Yaklaşan Süreler' paneli testleri (tasarım §4.5) — collect_deadline_items."""

from __future__ import annotations

from datetime import date

import pytest

from apps.disiplin import services
from apps.disiplin.deadlines import Severity, collect_deadline_items
from apps.disiplin.models import CaseStage, DisciplineCase, PrincipalDecision
from apps.disiplin.tests.factories import SchoolYearFactory, StudentFactory

pytestmark = pytest.mark.django_db


def _committee_case() -> tuple[DisciplineCase, int]:
    SchoolYearFactory()
    s = StudentFactory()
    case = services.create_case(
        petition_date=date(2026, 5, 18),
        petitioner_name="A",
        petitioner_role="IDARE",
        summary="x",
        student_ids=[s.pk],
    )
    services.add_event(
        case,
        CaseStage.DECIDED,
        date(2026, 5, 19),
        override=True,
        override_reason="atla",
        principal_decisions=[PrincipalDecision.DISCIPLINE_COMMITTEE],
    )
    return case, s.pk


def test_bos_sistemde_panel_bos() -> None:
    SchoolYearFactory()
    assert collect_deadline_items(date(2026, 5, 20)) == []


def test_kurul_karar_suresi_yaklasirken_ve_gecince() -> None:
    case, _sid = _committee_case()
    # Son gün 02.06.2026 (19.05 + 10 iş günü). 28.05'te ufuk (5 iş günü) içinde.
    items = collect_deadline_items(date(2026, 5, 28))
    kurul = [i for i in items if i.statute_ref == "md. 192/3"]
    assert len(kurul) == 1
    assert kurul[0].severity == Severity.UPCOMING
    assert kurul[0].due_date == date(2026, 6, 2)
    assert kurul[0].case_no == case.case_no
    # Süre geçince GEÇTİ.
    gec = [i for i in collect_deadline_items(date(2026, 6, 3)) if i.statute_ref == "md. 192/3"]
    assert gec[0].severity == Severity.OVERDUE
    # Çok erken tarihte ufuk dışında — görünmez.
    erken = [i for i in collect_deadline_items(date(2026, 5, 20)) if i.statute_ref == "md. 192/3"]
    assert erken == []


def test_teblig_bekleyen_karar_bilgi_olarak_listelenir() -> None:
    case, sid = _committee_case()
    services.record_decision(
        case, student_id=sid, penalty_type="REPRIMAND", decision_date=date(2026, 5, 22)
    )
    items = collect_deadline_items(date(2026, 5, 23))
    teblig = [i for i in items if "tebliğ bekliyor" in i.title]
    assert len(teblig) == 1
    assert teblig[0].severity == Severity.INFO
    assert teblig[0].due_date is None


def test_itiraz_sevk_suresi_listelenir() -> None:
    case, sid = _committee_case()
    d = services.record_decision(
        case, student_id=sid, penalty_type="REPRIMAND", decision_date=date(2026, 5, 22)
    )
    services.notify_decision(d, notified_on=date(2026, 5, 22))
    services.file_appeal(d, filed_on=date(2026, 5, 25), filed_by_role="PARENT")
    # Sevk son günü 01.06.2026 (25.05 + 5 iş günü).
    items = collect_deadline_items(date(2026, 5, 27))
    sevk = [i for i in items if i.statute_ref == "md. 169/3"]
    assert len(sevk) == 1
    assert sevk[0].due_date == date(2026, 6, 1)
    # Sevk edilince listeden düşer.
    appeal = d.appeals.get()
    services.forward_appeal(appeal, forwarded_on=date(2026, 5, 28))
    assert [
        i for i in collect_deadline_items(date(2026, 5, 29)) if i.statute_ref == "md. 169/3"
    ] == []


def test_tedbir_suresi_listelenir() -> None:
    """İKİ eşik (işleme başlama 175/2 + bitiş 175/1) ufka girince ayrı satırlarla listelenir."""
    case, sid = _committee_case()
    services.create_precaution(case, student_id=sid, start_date=date(2026, 5, 20), requested_days=5)
    items = collect_deadline_items(date(2026, 5, 21))
    tedbir = sorted(
        (i for i in items if i.statute_ref == "md. 175"), key=lambda i: i.due_date or date.max
    )
    assert len(tedbir) == 2
    assert tedbir[0].due_date == date(2026, 5, 25)  # işleme başlama eşiği
    assert "işlemine başlanmalı" in tedbir[0].title
    assert tedbir[1].due_date == date(2026, 5, 26)  # bitiş eşiği
    assert "süresi doluyor" in tedbir[1].title


def test_kapanisa_hazir_dosya_bilgi_olarak_listelenir() -> None:
    case, sid = _committee_case()
    d = services.record_decision(
        case, student_id=sid, penalty_type="REPRIMAND", decision_date=date(2026, 5, 22)
    )
    services.notify_decision(d, notified_on=date(2026, 5, 22))
    # İtiraz süresi dolunca önce e-Okul hatırlatması gelir.
    bekleyen = [
        i for i in collect_deadline_items(date(2026, 6, 1)) if "e-Okul'a işlenmeli" in i.title
    ]
    assert len(bekleyen) == 1
    services.confirm_e_school_entry(d, processed_on=date(2026, 6, 1))
    # İtiraz süresi (29.05) + tampon (05.06) ve e-Okul onayı tamamlanınca kapatılabilir.
    hazir = [i for i in collect_deadline_items(date(2026, 6, 8)) if "kapatılabilir" in i.title]
    assert len(hazir) == 1
    assert hazir[0].severity == Severity.INFO


def test_siralama_gecti_yaklasiyor_bilgi() -> None:
    case, sid = _committee_case()
    d = services.record_decision(
        case, student_id=sid, penalty_type="REPRIMAND", decision_date=date(2026, 5, 22)
    )
    # Tebliğsiz karar (BİLGİ) + kurul süresi 02.06 GEÇTİ durumunda.
    items = collect_deadline_items(date(2026, 6, 4))
    assert d is not None
    severities = [i.severity for i in items]
    assert severities == sorted(
        severities, key=lambda s: {Severity.OVERDUE: 0, Severity.UPCOMING: 1, Severity.INFO: 2}[s]
    )
    assert severities[0] == Severity.OVERDUE
