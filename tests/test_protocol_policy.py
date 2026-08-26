from pathlib import Path
import sys

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "orchestration" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from protocol_policy import recovery_allowed, select_pressure_ladder  # noqa: E402


def test_configured_pressure_ladder_is_authoritative():
    selected = select_pressure_ladder([-500, 0, 5000], ced_mpa=310)

    assert selected.pressures_atm == (-500, 0, 5000)
    assert selected.reason == "class_protocol"


def test_ced_screens_tension_limit():
    selected = select_pressure_ladder(ced_mpa=310)

    assert selected.pressures_atm == (-600, 0, 3000, 7000, 15000)
    assert selected.reason == "ced_screened"
    assert selected.tension_limit_atm == -600


def test_missing_ced_uses_conservative_probe():
    selected = select_pressure_ladder()

    assert selected.pressures_atm[0] == -200
    assert selected.reason == "conservative_unscreened"


def test_recovery_is_bounded_to_two_attempts():
    assert recovery_allowed(0)
    assert recovery_allowed(1)
    assert not recovery_allowed(2)


# ─── fluctuation-K-informed pressure-ladder selection (Feature 1) ──────────────

def test_fluctuation_k_none_preserves_existing_behavior_pinned():
    """Default arg contract: omitting fluctuation_K_GPa must reproduce today's
    behavior byte-for-byte."""
    selected = select_pressure_ladder([-500, 0, 5000], ced_mpa=310)
    assert selected.pressures_atm == (-500, 0, 5000)
    assert selected.reason == "class_protocol"
    assert selected.ladder_adjustment is None


def test_fluctuation_k_none_preserves_existing_behavior_unpinned():
    selected = select_pressure_ladder(ced_mpa=310)
    assert selected.pressures_atm == (-600, 0, 3000, 7000, 15000)
    assert selected.reason == "ced_screened"


# Archived, empirically-validated class ladders (guides/polymer_rules.json) at their own
# documented exp_K_GPa bounds must come back byte-identical -- this is the Stage-3 merge
# gate: fluctuation-K seeding must never move a ladder that already works. The live check
# actually sees the FLUCTUATION K estimate, not exp_K_GPa -- and this codebase documents
# that estimate running ~+70% high for rubbery classes (PEG2, polymer_rules.json), so the
# rubbery classes (PHYC/PDIE/POXI) also get a 1.7x-scaled-max row for the number the live
# path will actually see. PEST is glassy (no rubbery-fluctuation-bias correction applies).
@pytest.mark.parametrize("configured,k_gpa", [
    ((1, 1000, 2500, 5000, 10000, 15000), 1.5),        # PHYC, exp_K_GPa min
    ((1, 1000, 2500, 5000, 10000, 15000), 2.0),        # PHYC, exp_K_GPa max
    ((1, 1000, 2500, 5000, 10000, 15000), 1.7 * 2.0),  # PHYC, live fluctuation estimate (~+70%)
    ((1, 1000, 2500, 5000, 10000, 15000), 1.38),       # PDIE, exp_K_GPa min
    ((1, 1000, 2500, 5000, 10000, 15000), 1.95),       # PDIE, exp_K_GPa max
    ((1, 1000, 2500, 5000, 10000, 15000), 1.7 * 1.95), # PDIE, live fluctuation estimate
    ((-1000, 0, 3000, 7000, 15000), 2.0),              # POXI, exp_K_GPa min
    ((-1000, 0, 3000, 7000, 15000), 4.0),              # POXI, exp_K_GPa max
    ((-1000, 0, 3000, 7000, 15000), 1.7 * 4.0),        # POXI, live fluctuation estimate
    ((-1000, 0, 1500, 3000, 5000), 3.0),               # PEST, exp_K_GPa min
    ((-1000, 0, 1500, 3000, 5000), 4.5),               # PEST, exp_K_GPa max (tightest case)
])
def test_fluctuation_k_leaves_validated_archive_ladders_unchanged(configured, k_gpa):
    selected = select_pressure_ladder(list(configured), fluctuation_K_GPa=k_gpa)
    assert selected.pressures_atm == configured
    assert selected.ladder_adjustment is None
    assert selected.reason == "class_protocol"


def test_fluctuation_k_extends_undershot_pinned_ladder():
    """PSIL's own bm_pressures_note already flags it as possibly under-ranged --
    this is the intended first activation, not a regression."""
    selected = select_pressure_ladder([1, 100, 300, 600, 1000], fluctuation_K_GPa=1.5)
    assert selected.pressures_atm == (1, 100, 300, 600, 1000, 1200)
    assert selected.reason == "class_protocol_fluctuation_extended"
    assert selected.ladder_adjustment["kind"] == "extend_compression"
    assert selected.ladder_adjustment["added_point_atm"] == 1200


def test_unpinned_class_uses_default_ladder_when_k_modest():
    selected = select_pressure_ladder(fluctuation_K_GPa=2.0)
    assert selected.pressures_atm == (-200, 0, 3000, 7000, 15000)
    assert selected.ladder_adjustment is None


def test_unpinned_class_scales_up_for_stiff_polymer():
    selected = select_pressure_ladder(fluctuation_K_GPa=30.0)
    assert selected.pressures_atm == (-200, 0, 4700, 11100, 23700)
    assert selected.ladder_adjustment["kind"] == "scaled_unpinned_ladder"
    assert selected.compression_limit_atm == 23700


def test_ladder_trim_direction_is_disabled_in_v1():
    """A generously-wide pinned ladder against a tiny fluctuation-K estimate must
    still come back unchanged -- LADDER_TRIM_ENABLED is deliberately off."""
    selected = select_pressure_ladder([0, 15000], fluctuation_K_GPa=0.1)
    assert selected.pressures_atm == (0, 15000)
    assert selected.ladder_adjustment is None
