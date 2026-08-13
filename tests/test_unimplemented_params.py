"""decided_params that no executor consumes.

`eq_annealing_cycles` was raised as a remedy twice (PACR 5->10, PKTN 8->12) on the
strength of assess_cooling_contraction's UNDER_ANNEALED_COOLING verdicts, with notes
citing NkepsuMbitou's 10-cycle precedent. `generate_equilibration_workflow` has no
annealing-cycles parameter, so neither raise changed anything that ran. The failure is
silent in both directions: the plan records a protocol that did not happen, and the
remedy produces no behaviour change to explain its own ineffectiveness.
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))

from validate_run_plan import (  # noqa: E402
    UNIMPLEMENTED_PARAMS,
    _unimplemented_param_findings,
)


def test_set_unimplemented_param_is_structural():
    f = _unimplemented_param_findings({"decided_params": {"eq_annealing_cycles": 10}})
    assert len(f) == 1
    assert f[0]["severity"] == "structural"
    assert f[0]["check"] == "decided_param_not_executed"
    assert "10" in f[0]["detail"]


def test_unset_and_null_are_silent():
    """A plan that never claims the parameter has nothing to answer for."""
    assert _unimplemented_param_findings({"decided_params": {}}) == []
    assert _unimplemented_param_findings(
        {"decided_params": {"eq_annealing_cycles": None}}) == []
    assert _unimplemented_param_findings(
        {"decided_params": {"eq_annealing_cycles": "null"}}) == []


def test_zero_still_reports():
    """0 is a claim about protocol, not an absence of one -- and it is also wrong,
    since the workflow always runs exactly one heat/compress/cool pass."""
    assert len(_unimplemented_param_findings(
        {"decided_params": {"eq_annealing_cycles": 0}})) == 1


def test_missing_decided_params_does_not_crash():
    assert _unimplemented_param_findings({}) == []


def test_every_entry_carries_a_traced_reason():
    """Entries must be verified against a call path, not guessed from a name grep --
    a false entry here would block plans over a parameter that does work."""
    for key, why in UNIMPLEMENTED_PARAMS.items():
        assert isinstance(why, str) and len(why) > 30, key


def test_implemented_params_are_not_listed():
    """cutoff_A does reach the deck (as a hardcoded style constant, which is a
    separate reporting bug) -- it must not be flagged as unimplemented."""
    for k in ("cutoff_A", "dp_typical", "nchain", "tg_rates_K_per_ns"):
        assert k not in UNIMPLEMENTED_PARAMS
