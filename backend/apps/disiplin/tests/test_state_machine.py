"""Disiplin durum makinesi testleri (saf mantık — requirements §4.2)."""

from __future__ import annotations

import pytest

from apps.disiplin.models import CaseStage
from apps.disiplin.state_machine import (
    InvalidTransitionError,
    is_valid_transition,
    validate_transition,
)

# (kaynak, hedef, geçerli mi) — normal (override'sız) akış matrisi.
VALID_CASES = [
    (None, CaseStage.PETITION),
    (CaseStage.PETITION, CaseStage.GUIDANCE_REFERRED),
    (CaseStage.GUIDANCE_REFERRED, CaseStage.GUIDANCE_RETURNED),
    (CaseStage.GUIDANCE_RETURNED, CaseStage.DECIDED),
    (CaseStage.DECIDED, CaseStage.COMMITTEE_DONE),
    (CaseStage.DECIDED, CaseStage.CLOSED),
    (CaseStage.COMMITTEE_DONE, CaseStage.CLOSED),
]

INVALID_CASES = [
    (CaseStage.PETITION, CaseStage.DECIDED),  # rehberlik atlama → override gerekli
    (CaseStage.PETITION, CaseStage.COMMITTEE_DONE),
    (CaseStage.PETITION, CaseStage.CLOSED),
    (CaseStage.GUIDANCE_REFERRED, CaseStage.DECIDED),
    (CaseStage.GUIDANCE_RETURNED, CaseStage.COMMITTEE_DONE),
    (CaseStage.CLOSED, CaseStage.DECIDED),
    (CaseStage.COMMITTEE_DONE, CaseStage.DECIDED),
]


@pytest.mark.parametrize("current,target", VALID_CASES)
def test_gecerli_gecisler(current, target) -> None:  # type: ignore[no-untyped-def]
    assert is_valid_transition(current, target) is True
    validate_transition(current, target)  # exception atmamalı


@pytest.mark.parametrize("current,target", INVALID_CASES)
def test_gecersiz_gecisler(current, target) -> None:  # type: ignore[no-untyped-def]
    assert is_valid_transition(current, target) is False
    with pytest.raises(InvalidTransitionError):
        validate_transition(current, target)


def test_petition_to_decided_override_gerektirir() -> None:
    # Rehberlik atlama normal akışta geçersizdir (override izinli — service'te).
    assert is_valid_transition(CaseStage.PETITION, CaseStage.DECIDED) is False
