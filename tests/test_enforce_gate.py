"""Regression guard for enforce_gate.py's MSD/MSID advisory wiring.

kinetic_trap_flag (chain.msd) and gaussian_pass (chain.msid) are computed by
check_equilibration_comprehensive.py but were never read into enforce_gate.py's `gates`
dict -- so they never appeared in either binding_results or advisory_results, in any
clause. This test locks in the fix: both are always advisory (never binding, in any of
require_glassy / require_rubbery / plain-require), polarity-corrected
(msd_not_trapped == not kinetic_trap_flag), and never change a run's PASS/EXTEND/
STRUCTURAL_FAIL/FAIL verdict -- a pure completeness fix to the reported gate breakdown.
"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestration"))

import enforce_gate  # noqa: E402


# ─── msd_msid_gates(): polarity + availability ─────────────────────────────────

def test_msd_msid_gates_polarity_trapped():
    chain = {"msd": {"kinetic_trap_flag": True}, "msid": {"available": True, "gaussian_pass": True}}
    assert enforce_gate.msd_msid_gates(chain) == {"msd_not_trapped": False, "msid_gaussian": True}


def test_msd_msid_gates_polarity_not_trapped():
    chain = {"msd": {"kinetic_trap_flag": False}, "msid": {"available": False}}
    assert enforce_gate.msd_msid_gates(chain) == {"msd_not_trapped": True, "msid_gaussian": None}


def test_msd_msid_gates_missing_data():
    assert enforce_gate.msd_msid_gates({}) == {"msd_not_trapped": None, "msid_gaussian": None}


# ─── classify(): always advisory, in every clause ──────────────────────────────

BASE_GATES = {
    "density_drift": True, "energy_drift": True, "density_sem": True, "energy_sem": True,
    "rg": True, "ct": True, "p2": True, "density_homogeneity": True,
}


@pytest.mark.parametrize("regime,dp_typical,ct_gate_reliable,expected_clause", [
    ("glassy", 35, True, "require_glassy"),
    ("glassy", 10, False, "require_glassy"),   # ct_gate_reliable=False forces require_glassy even at low DP
    ("rubbery", None, True, "require_rubbery"),
    ("glassy", 10, True, "require (plain, no carve-out)"),
])
def test_classify_msd_msid_always_advisory(regime, dp_typical, ct_gate_reliable, expected_clause):
    for trap_pass in (True, False, None):
        gates = dict(BASE_GATES, msd_not_trapped=trap_pass, msid_gaussian=False)
        clause, binding_results, advisory_results = enforce_gate.classify(
            gates, regime, dp_typical, ct_gate_reliable)
        assert clause == expected_clause
        assert "msd_not_trapped" not in binding_results
        assert "msid_gaussian" not in binding_results
        if trap_pass is not None:
            assert advisory_results.get("msd_not_trapped") == trap_pass
        assert advisory_results.get("msid_gaussian") is False
        # regardless of clause, the pre-existing binding gates are untouched
        assert binding_results.get("density_homogeneity") is True


# ─── enforce_live(): verdict is unaffected by kinetic_trap_flag ────────────────

def _write_comp(tmp_path, kinetic_trap_flag, gaussian_pass=True, msid_available=True):
    comp = {
        "chain": {
            "rg": {"pass": True},
            "ct": {"pass": True},
            "msd": {"kinetic_trap_flag": kinetic_trap_flag},
            "msid": {"available": msid_available, "gaussian_pass": gaussian_pass},
        },
        "spatial": {
            "p2": {"pass": True},
            "density_homogeneity": {"pass": True},
        },
        "thermo": {
            "density_drift": {"pass": True},
            "energy_drift": {"pass": True},
            "density_sem": {"pass": True},
            "energy_sem": {"pass": True},
        },
    }
    path = tmp_path / "equilibration_comprehensive.json"
    path.write_text(json.dumps(comp))
    return path


def _live_args(comp_path, regime, dp, ct_gate_reliable):
    return SimpleNamespace(
        comprehensive_json=str(comp_path), regime=regime, dp=dp,
        ct_gate_reliable=ct_gate_reliable, exp_density_gcm3=None, tg_k=None,
        t_equil_k=None, glass_data=None, melt_data=None, out_dir=None,
        alpha_glass_per_k=None, alpha_melt_per_k=None,
    )


@pytest.mark.parametrize("regime,dp,ct_gate_reliable", [
    ("glassy", 35, True),    # require_glassy
    ("rubbery", None, True),  # require_rubbery
    ("glassy", 10, True),    # plain require -- the branch classify() defaults to all-binding
])
def test_enforce_live_verdict_unaffected_by_kinetic_trap(tmp_path, regime, dp, ct_gate_reliable):
    comp_path = _write_comp(tmp_path, kinetic_trap_flag=True, gaussian_pass=False)
    args = _live_args(comp_path, regime, dp, ct_gate_reliable)
    result = enforce_gate.enforce_live(args)

    assert result["verdict"] == "PASS"
    assert "msd_not_trapped" not in result["binding_gates"]
    assert "msid_gaussian" not in result["binding_gates"]
    assert result["advisory_gates"]["msd_not_trapped"] is False  # trapped -> not_trapped is False
    assert result["advisory_gates"]["msid_gaussian"] is False
    assert result["failing_binding_gates"] == []


def test_enforce_live_not_trapped_reports_true(tmp_path):
    comp_path = _write_comp(tmp_path, kinetic_trap_flag=False, gaussian_pass=True)
    args = _live_args(comp_path, "glassy", 35, True)
    result = enforce_gate.enforce_live(args)

    assert result["verdict"] == "PASS"
    assert result["advisory_gates"]["msd_not_trapped"] is True
    assert result["advisory_gates"]["msid_gaussian"] is True
