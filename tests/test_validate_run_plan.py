"""validate_run_plan checks that are not hardware-related.

(_hardware_findings has its own file, tests/test_validate_run_plan_hardware.py.)
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))

import validate_run_plan as vrp  # noqa: E402


# ─── explicit Tg window vs the anneal ceiling ─────────────────────────────────────

def _ceiling_plan(**decided):
    base = {"tg_t_high_K": 900, "annealing_T_high_K": 650.0, "cool_block_dT_K": 25.0}
    base.update(decided)
    return {"decided_params": base}


def test_explicit_tg_window_above_the_anneal_ceiling_is_flagged():
    """A hand-set sweep top the cooldown never reaches: the thermal stage will reheat the
    finished cell instead of starting from a melt-cooled one. Flagged rather than auto-fixed,
    because tg_t_high_K hashes to the thermal stage while the ceiling shapes the equilibration
    chain -- raising the ceiling here would change that chain under an unchanged equilibration
    _input_hash."""
    findings = vrp._tg_window_ceiling_findings(_ceiling_plan())
    assert len(findings) == 1
    assert findings[0]["check"] == "tg_window_ceiling"
    assert findings[0]["severity"] == "advisory"
    assert "925" in findings[0]["detail"]        # 900 + one 25 K cool block


def test_an_explicit_window_with_enough_headroom_is_silent():
    assert vrp._tg_window_ceiling_findings(
        _ceiling_plan(annealing_T_high_K=925.0)) == []


def test_a_derived_window_is_not_checked_here():
    """No explicit tg_t_high_K in decided_params -> the window was derived from the SMILES, and
    temperature_schedule already raised the ceiling to clear it."""
    assert vrp._tg_window_ceiling_findings(
        {"decided_params": {"annealing_T_high_K": 650.0}}) == []
