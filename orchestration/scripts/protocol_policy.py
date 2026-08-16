"""Deterministic scientific protocol selection and bounded recovery policy."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from math import floor
from typing import Iterable, Optional


DEFAULT_COMPRESSION_LADDER_ATM = (0, 3000, 7000, 15000)
UNSCREENED_TENSION_ATM = -200
MAX_TENSION_ATM = -1000
MAX_RECOVERY_ATTEMPTS = 2


@dataclass(frozen=True)
class PressureLadderSelection:
    pressures_atm: tuple[int, ...]
    reason: str
    compression_limit_atm: int
    tension_limit_atm: int
    ced_mpa: Optional[float]

    def to_dict(self) -> dict:
        return asdict(self)


def select_pressure_ladder(
    configured_pressures: Optional[Iterable[int]] = None,
    ced_mpa: Optional[float] = None,
) -> PressureLadderSelection:
    """Select a reproducible Murnaghan ladder without agent-authored run files.

    A class-specific ladder remains authoritative. Otherwise CED screens the tensile
    point at approximately twice the CED value in atm, rounded toward zero to the
    nearest 100 atm and capped at -1000 atm. Without CED, use one conservative probe.
    """
    configured = tuple(int(value) for value in (configured_pressures or ()))
    if configured:
        return PressureLadderSelection(
            pressures_atm=configured,
            reason="class_protocol",
            compression_limit_atm=max(configured),
            tension_limit_atm=min(configured),
            ced_mpa=ced_mpa,
        )

    if ced_mpa is None or ced_mpa <= 0:
        tension_limit = UNSCREENED_TENSION_ATM
        reason = "conservative_unscreened"
        ced_value = None
    else:
        screened_magnitude = floor((2.0 * float(ced_mpa)) / 100.0) * 100
        tension_limit = -min(abs(MAX_TENSION_ATM), max(200, screened_magnitude))
        reason = "ced_screened"
        ced_value = float(ced_mpa)

    pressures = (tension_limit, *DEFAULT_COMPRESSION_LADDER_ATM)
    return PressureLadderSelection(
        pressures_atm=pressures,
        reason=reason,
        compression_limit_atm=max(pressures),
        tension_limit_atm=tension_limit,
        ced_mpa=ced_value,
    )


def recovery_allowed(attempts_completed: int) -> bool:
    """Return whether another predefined recovery attempt may run."""
    return 0 <= attempts_completed < MAX_RECOVERY_ATTEMPTS
