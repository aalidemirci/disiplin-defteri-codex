from __future__ import annotations

from datetime import date

import pytest
from rest_framework.test import APIClient

from apps.disiplin import services
from apps.disiplin.models import CaseStage, PrincipalDecision
from apps.disiplin.tests.factories import PersonnelFactory, SchoolYearFactory, StudentFactory

pytestmark = pytest.mark.django_db


def _case():
    year = SchoolYearFactory()
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
        override_reason="r",
        principal_decisions=[PrincipalDecision.DISCIPLINE_COMMITTEE],
    )
    return year, case, s


@pytest.fixture
def client() -> APIClient:
    return APIClient(raise_request_exception=False)


def test_warning_student_null_500(client: APIClient) -> None:
    _y, case, _s = _case()
    r = client.post(
        f"/api/v1/discipline/cases/{case.pk}/warnings/",
        {"student": None, "warning_date": "2026-05-20"},
        format="json",
    )
    assert r.status_code == 400, r.status_code


def test_extension_requested_days_null_500(client: APIClient) -> None:
    _y, case, _s = _case()
    r = client.post(
        f"/api/v1/discipline/cases/{case.pk}/extensions/",
        {"requested_days": None, "reason": "x", "decided_on": "2026-05-25"},
        format="json",
    )
    assert r.status_code == 400, r.status_code


def test_meeting_attendee_ids_null_500(client: APIClient) -> None:
    _y, case, _s = _case()
    r = client.post(
        f"/api/v1/discipline/cases/{case.pk}/meeting/",
        {"meeting_date": "2026-05-20", "attendee_member_ids": [None]},
        format="json",
    )
    assert r.status_code == 400, r.status_code


def test_council_meeting_attendees_int_500(client: APIClient) -> None:
    year, _case_, _s = _case()
    r = client.post(
        "/api/v1/council/meetings/",
        {
            "school_year": year.pk,
            "council_type": "DISCIPLINE",
            "meeting_date": "2026-05-20",
            "attendees": 5,
        },
        format="json",
    )
    assert r.status_code == 400, r.status_code


def test_committee_school_year_null_500(client: APIClient) -> None:
    SchoolYearFactory()
    chair = PersonnelFactory()
    r = client.post(
        "/api/v1/discipline/committee/",
        {"school_year": None, "chair": chair.pk},
        format="json",
    )
    assert r.status_code == 400, r.status_code


def test_purge_record_case_ids_null_500(client: APIClient) -> None:
    r = client.post(
        "/api/v1/disiplin/imha/tutanak/",
        {"case_ids": [None], "onay": True},
        format="json",
    )
    assert r.status_code == 400, r.status_code


def test_precaution_extend_multipart_false_bypasses_mem(client: APIClient) -> None:
    _y, case, s = _case()
    p = services.create_precaution(
        case, student_id=s.pk, start_date=date(2026, 5, 20), requested_days=5
    )
    r = client.post(
        f"/api/v1/discipline/cases/{case.pk}/precautions/{p.pk}/extend/",
        {"additional_days": "3", "mne_notified": "false"},
    )  # multipart (varsayılan) — "false" metni
    # md. 175/2: MEM onayı yoksa 400 beklenir.
    assert r.status_code == 400, (r.status_code, r.content)
