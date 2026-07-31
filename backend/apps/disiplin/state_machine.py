"""Disiplin süreci durum makinesi (requirements §4.2 kabul kriteri).

Bir aşama geçmeden sonraki açılmaz; geçersiz geçiş `InvalidTransitionError`
yükseltir. Admin, gerekçe vererek geçişi delip geçebilir (override) — bu durum
çağıran serviste loglanır (services.add_event → STATE_MACHINE_OVERRIDE).

Bu modül saf mantıktır: ORM/Django'ya bağlı değildir, kolay test edilir.
"""

from __future__ import annotations

from apps.disiplin.models import CaseStage

# Geçerli geçişler: kaynak aşama → izin verilen hedef aşamalar.
# None kaynağı: dosyanın ilk oluşturulması (PETITION).
TRANSITION_MAP: dict[str | None, set[str]] = {
    None: {CaseStage.PETITION},
    CaseStage.PETITION: {CaseStage.GUIDANCE_REFERRED, CaseStage.DECIDED},
    CaseStage.GUIDANCE_REFERRED: {CaseStage.GUIDANCE_RETURNED},
    CaseStage.GUIDANCE_RETURNED: {CaseStage.DECIDED},
    CaseStage.DECIDED: {CaseStage.COMMITTEE_DONE, CaseStage.CLOSED},
    CaseStage.COMMITTEE_DONE: {CaseStage.CLOSED},
    CaseStage.CLOSED: set(),
}

# PETITION → DECIDED (rehberlik atlama) yalnızca override ile yapılabilir.
# Aşağıdaki küme "normalde geçerli" geçişlerdir; override bunu genişletir.
_OVERRIDE_ONLY: set[tuple[str | None, str]] = {
    (CaseStage.PETITION, CaseStage.DECIDED),
}


class InvalidTransitionError(Exception):
    """Geçersiz durum geçişi (override olmadan)."""


def is_valid_transition(current: str | None, target: str) -> bool:
    """`current` aşamasından `target` aşamasına normal (override'sız) geçiş geçerli mi?

    Rehberlik atlama (PETITION → DECIDED) normal akışta geçersizdir; override
    gerektirir (requirements §4.2 — "uyarı verir, override izinli").
    """
    if (current, target) in _OVERRIDE_ONLY:
        return False
    return target in TRANSITION_MAP.get(current, set())


def validate_transition(current: str | None, target: str) -> None:
    """Geçiş geçersizse `InvalidTransitionError` yükseltir.

    Herhangi bir aşamadan CLOSED'a geçiş yalnızca override ile mümkündür (admin),
    DECIDED/COMMITTEE_DONE → CLOSED normal akışı hariç.
    """
    if not is_valid_transition(current, target):
        raise InvalidTransitionError(
            f"'{current}' aşamasından '{target}' aşamasına geçiş geçersiz."
        )
