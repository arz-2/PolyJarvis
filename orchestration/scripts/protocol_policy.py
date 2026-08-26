"""Deterministic scientific protocol selection and bounded recovery policy."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from math import floor
from typing import Iterable, Optional


DEFAULT_COMPRESSION_LADDER_ATM = (0, 3000, 7000, 15000)
UNSCREENED_TENSION_ATM = -200
MAX_TENSION_ATM = -1000
MAX_RECOVERY_ATTEMPTS = 2

# Fluctuation-K-informed ladder selection (D-07 Murnaghan pressure ladder).
#
# ATM_PER_GPA converts a bulk-modulus estimate to a pressure scale (1 GPa / 101325 Pa/atm).
# STRAIN_FLOOR is a MINIMUM identifiability requirement, not a target or a ceiling: a
# too-narrow pressure range leaves the Murnaghan EOS's two parameters (B0, B0') nearly
# degenerate near P≈0 (this is exactly why PHYC/PDIE/POXI were historically widened after
# B0' runaway). Naive linear-elasticity strain (ΔP≈K·ε) badly UNDERSTATES the true pressure
# needed, because the real EOS stiffens under compression -- so this floor is calibrated
# deliberately low, to sit below every already-validated class ladder's own naive-strain
# equivalent except the one class (PSIL) whose own bm_pressures_note already flags it as
# possibly under-ranged ("widen here too if B0' runs away"):
#   PHYC max=15000 atm, K≈1.65-2.0 GPa  -> naive strain ≈ 76-92%
#   PDIE max=15000 atm, K≈1.38-1.95 GPa -> naive strain ≈ 78-110%
#   POXI max=15000 atm, K≈2.0-4.0 GPa   -> naive strain ≈ 38-76%
#   PEST max=5000 atm,  K≈3.0-4.5 GPa   -> naive strain ≈ 11-17% (tightest known-good case)
#   PSIL max=1000 atm,  K unconfirmed   -> naive strain plausibly well under the floor
# STRAIN_FLOOR=0.08 sits below PEST's tightest case with margin, so validated ladders are
# essentially never touched (see UNDERSHOOT_MARGIN below), while PSIL's likely-under-ranged
# ladder can still trigger the extension it already anticipates.
ATM_PER_GPA = 9869.23
STRAIN_FLOOR = 0.08
# Only trigger an extension when the configured ladder falls meaningfully (not marginally)
# short of the required compression, to avoid flapping right at the boundary.
UNDERSHOOT_MARGIN = 0.85
# A trim/narrow direction for an already-generously-wide pinned ladder is deliberately
# designed below but shipped OFF: the naive linear-strain estimate this module uses
# overstates true (nonlinear) identifiability margin, so a trim rule calibrated on it
# would incorrectly narrow PHYC/PDIE/POXI -- the exact classes already widened for good
# reason. Enabling this needs the true nonlinear Murnaghan relation (i.e. B0'), which
# isn't available from a single-point fluctuation estimate.
LADDER_TRIM_ENABLED = False
OVERSHOOT_FACTOR = 3.0
PRESSURE_ROUND_ATM = 100


def _required_compression_atm(fluctuation_K_GPa: float) -> int:
    """Minimum compression (atm) this polymer's own K implies is needed to reach
    STRAIN_FLOOR -- a floor on identifiability, not a target ladder width."""
    raw = fluctuation_K_GPa * ATM_PER_GPA * STRAIN_FLOOR
    return int(round(raw / PRESSURE_ROUND_ATM) * PRESSURE_ROUND_ATM)


@dataclass(frozen=True)
class PressureLadderSelection:
    pressures_atm: tuple[int, ...]
    reason: str
    compression_limit_atm: int
    tension_limit_atm: int
    ced_mpa: Optional[float]
    fluctuation_K_GPa: Optional[float] = None
    ladder_adjustment: Optional[dict] = None

    def to_dict(self) -> dict:
        return asdict(self)


def select_pressure_ladder(
    configured_pressures: Optional[Iterable[int]] = None,
    ced_mpa: Optional[float] = None,
    fluctuation_K_GPa: Optional[float] = None,
) -> PressureLadderSelection:
    """Select a reproducible Murnaghan ladder without agent-authored run files.

    A class-specific ladder remains authoritative. Otherwise CED screens the tensile
    point at approximately twice the CED value in atm, rounded toward zero to the
    nearest 100 atm and capped at -1000 atm. Without CED, use one conservative probe.

    ``fluctuation_K_GPa`` (this specific polymer's own volume-fluctuation K estimate,
    already available for free from the equilibration NPT log before this stage runs)
    is an additional, optional sanity check -- see the module-level constants above.
    Passing ``None`` (the default) reproduces prior behavior exactly, byte-for-byte.
    """
    configured = tuple(int(value) for value in (configured_pressures or ()))

    if configured:
        if fluctuation_K_GPa is None or fluctuation_K_GPa <= 0:
            return PressureLadderSelection(
                pressures_atm=configured,
                reason="class_protocol",
                compression_limit_atm=max(configured),
                tension_limit_atm=min(configured),
                ced_mpa=ced_mpa,
                fluctuation_K_GPa=fluctuation_K_GPa,
                ladder_adjustment=None,
            )

        required_atm = _required_compression_atm(fluctuation_K_GPa)
        configured_max = max(configured)
        if configured_max < UNDERSHOOT_MARGIN * required_atm:
            new_point = required_atm
            pressures = tuple(sorted(set(configured) | {new_point}))
            adjustment = {
                "kind": "extend_compression",
                "trigger": "undershoot",
                "required_compression_atm": required_atm,
                "configured_compression_atm": configured_max,
                "added_point_atm": new_point,
                "target_strain_floor": STRAIN_FLOOR,
            }
            reason = "class_protocol_fluctuation_extended"
        elif (LADDER_TRIM_ENABLED and configured_max > OVERSHOOT_FACTOR * required_atm
              and len(configured) - 1 >= 4):
            # Disabled -- see LADDER_TRIM_ENABLED rationale above. Never reached in v1.
            pressures, adjustment, reason = configured, None, "class_protocol"
        else:
            pressures, adjustment, reason = configured, None, "class_protocol"

        return PressureLadderSelection(
            pressures_atm=pressures,
            reason=reason,
            compression_limit_atm=max(pressures),
            tension_limit_atm=min(pressures),
            ced_mpa=ced_mpa,
            fluctuation_K_GPa=fluctuation_K_GPa,
            ladder_adjustment=adjustment,
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

    compression, adjustment = DEFAULT_COMPRESSION_LADDER_ATM, None
    if fluctuation_K_GPa is not None and fluctuation_K_GPa > 0:
        required_atm = _required_compression_atm(fluctuation_K_GPa)
        default_ceiling = DEFAULT_COMPRESSION_LADDER_ATM[-1]
        ceiling = max(default_ceiling, required_atm)
        if ceiling > default_ceiling:
            compression = tuple(
                int(round(ceiling * (p / default_ceiling) / PRESSURE_ROUND_ATM)
                    * PRESSURE_ROUND_ATM)
                for p in DEFAULT_COMPRESSION_LADDER_ATM
            )
            adjustment = {
                "kind": "scaled_unpinned_ladder",
                "compression_limit_atm": ceiling,
                "target_strain_floor": STRAIN_FLOOR,
            }

    pressures = (tension_limit, *compression)
    return PressureLadderSelection(
        pressures_atm=pressures,
        reason=reason,
        compression_limit_atm=max(pressures),
        tension_limit_atm=tension_limit,
        ced_mpa=ced_value,
        fluctuation_K_GPa=fluctuation_K_GPa,
        ladder_adjustment=adjustment,
    )


def recovery_allowed(attempts_completed: int) -> bool:
    """Return whether another predefined recovery attempt may run."""
    return 0 <= attempts_completed < MAX_RECOVERY_ATTEMPTS
