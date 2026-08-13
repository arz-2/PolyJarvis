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
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))

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


# ─── collect_gates(): one source of truth for both paths ───────────────────────

def test_collect_gates_covers_both_enforce_paths():
    """enforce() and enforce_live() must read the SAME gate keys. They used to build the
    dict independently, so a key added to one was a silent no-op in the other."""
    comp = {
        "thermo": {
            "density_drift": {"pass": True}, "energy_drift": {"pass": True},
            "density_sem": {"pass": True}, "energy_sem": {"pass": True},
            "n_eff_density": {"pass": False, "n_eff": 11, "n_eff_min": 20},
            "residual_stress": {"available": True, "resolved": True, "von_mises_atm": 290.7},
        },
        "chain": {"rg": {"pass": True}, "ct": {"pass": False},
                  "msd": {"kinetic_trap_flag": True},
                  "msid": {"available": True, "gaussian_pass": True}},
        "spatial": {"p2": {"pass": True},
                    "density_homogeneity": {"pass": True, "verdict": "PASS"}},
    }
    gates = enforce_gate.collect_gates(comp)
    assert gates["n_eff_density"] is False
    assert gates["residual_stress"] is False   # resolved deviatoric stress -> not-clean
    assert gates["density_homogeneity"] is True
    assert gates["msd_not_trapped"] is False


def test_residual_stress_gate_none_without_pressure_tensor():
    """Logs without Pxx/Pyy/Pzz must yield None, not a spurious pass or fail."""
    assert enforce_gate.residual_stress_gate({}) is None
    assert enforce_gate.residual_stress_gate(
        {"residual_stress": {"available": False, "reason": "no cols"}}) is None


# ─── n_eff_density: Class B, routes EXTEND ─────────────────────────────────────

@pytest.mark.parametrize("regime,dp", [("glassy", 35), ("rubbery", None)])
def test_n_eff_failure_routes_extend(tmp_path, regime, dp):
    """Too few independent density samples is undersampling of a valid state -- more NPT
    at the same T fixes it, so it must never read as STRUCTURAL_FAIL."""
    comp_path = _write_comp(tmp_path, kinetic_trap_flag=False)
    comp = json.loads(comp_path.read_text())
    comp["thermo"]["n_eff_density"] = {"pass": False, "n_eff": 11, "n_eff_min": 20}
    comp_path.write_text(json.dumps(comp))

    result = enforce_gate.enforce_live(_live_args(comp_path, regime, dp, True))
    assert result["verdict"] == "EXTEND"
    assert result["failing_binding_gates"] == ["n_eff_density"]


def test_n_eff_is_binding_not_advisory(tmp_path):
    comp_path = _write_comp(tmp_path, kinetic_trap_flag=False)
    comp = json.loads(comp_path.read_text())
    comp["thermo"]["n_eff_density"] = {"pass": True, "n_eff": 900, "n_eff_min": 20}
    comp_path.write_text(json.dumps(comp))

    result = enforce_gate.enforce_live(_live_args(comp_path, "glassy", 35, True))
    assert result["binding_gates"]["n_eff_density"] is True
    assert "n_eff_density" not in result["advisory_gates"]


# ─── residual_stress: advisory in every clause, never a z-score gate ───────────

@pytest.mark.parametrize("regime,dp,ct_ok", [
    ("glassy", 35, True), ("rubbery", None, True), ("glassy", 10, True),
])
def test_resolved_residual_stress_never_blocks(tmp_path, regime, dp, ct_ok):
    """A resolved deviatoric stress is a real mechanical-equilibrium violation, but its
    magnitude bound is uncalibrated -- every archived glassy run violates it to some
    degree, so binding it now would halt the whole glassy track."""
    comp_path = _write_comp(tmp_path, kinetic_trap_flag=False)
    comp = json.loads(comp_path.read_text())
    comp["thermo"]["residual_stress"] = {
        "available": True, "resolved": True, "z_max": 12.3, "von_mises_atm": 428.6,
    }
    comp_path.write_text(json.dumps(comp))

    result = enforce_gate.enforce_live(_live_args(comp_path, regime, dp, ct_ok))
    assert result["verdict"] == "PASS"
    assert "residual_stress" not in result["binding_gates"]
    assert result["advisory_gates"]["residual_stress"] is False
    assert result["residual_stress"]["von_mises_atm"] == 428.6


# ─── density_homogeneity: HOMOG_HETEROGENEOUS routes to melt mixing ────────────

def test_heterogeneous_keeps_melt_mixing_remedy(tmp_path):
    comp_path = _write_comp(tmp_path, kinetic_trap_flag=False)
    comp = json.loads(comp_path.read_text())
    comp["spatial"]["density_homogeneity"] = {
        "pass": False, "verdict": "HOMOG_HETEROGENEOUS",
        "cv_mean": 0.287, "poisson_cv": 0.214, "cv_signal": 0.192,
    }
    comp_path.write_text(json.dumps(comp))

    result = enforce_gate.enforce_live(_live_args(comp_path, "glassy", 35, True))
    assert result["verdict"] == "STRUCTURAL_FAIL"
    assert result["homogeneity_verdict"] == "HOMOG_HETEROGENEOUS"
    assert "MELT-MIXING" in result["remedy"]


# ─── finite size: periodic self-imaging is structural, never extendable ────────

def _with_finite_size(tmp_path, **fs):
    comp_path = _write_comp(tmp_path, kinetic_trap_flag=False)
    comp = json.loads(comp_path.read_text())
    comp["spatial"]["finite_size"] = fs
    comp_path.write_text(json.dumps(comp))
    return comp_path


@pytest.mark.parametrize("regime,dp", [("glassy", 35), ("rubbery", None)])
def test_min_image_violation_is_structural(tmp_path, regime, dp):
    """L < 2*cutoff_A means the pair potential itself is wrong -- no amount of sampling
    or re-cooling can fix it, so it must never route EXTEND."""
    comp_path = _with_finite_size(
        tmp_path, available=True, **{"pass": False},
        verdict="SIZE_MIN_IMAGE_VIOLATION", L_min_A=20.0, L_over_2cutoff=0.83,
    )
    result = enforce_gate.enforce_live(_live_args(comp_path, regime, dp, True))
    assert result["verdict"] == "STRUCTURAL_FAIL"
    assert result["finite_size_verdict"] == "SIZE_MIN_IMAGE_VIOLATION"
    assert "REBUILD LARGER" in result["remedy"]
    assert "potential itself is wrong" in result["remedy"]


def test_chain_self_image_is_structural_with_nchain_remedy(tmp_path):
    """PEEK1's real numbers: L/2Rg = 0.74."""
    comp_path = _with_finite_size(
        tmp_path, available=True, **{"pass": False},
        verdict="SIZE_CHAIN_SELF_IMAGE", L_min_A=36.37, L_over_2cutoff=1.52,
        L_over_2Rg=0.74, L_over_Ree=0.65,
    )
    result = enforce_gate.enforce_live(_live_args(comp_path, "glassy", 35, True))
    assert result["verdict"] == "STRUCTURAL_FAIL"
    assert "nchain" in result["remedy"]
    assert result["finite_size"]["L_over_2Rg"] == 0.74


def test_finite_size_binding_in_both_regimes(tmp_path):
    comp_path = _with_finite_size(tmp_path, available=True, **{"pass": True},
                                  verdict="SIZE_PASS", L_over_2Rg=1.47)
    for regime, dp in (("glassy", 35), ("rubbery", None)):
        result = enforce_gate.enforce_live(_live_args(comp_path, regime, dp, True))
        assert result["binding_gates"]["finite_size"] is True
        assert result["verdict"] == "PASS"


def test_finite_size_unavailable_is_dropped_not_failed(tmp_path):
    """No box or no Rg measured must not fabricate a failure."""
    comp_path = _with_finite_size(tmp_path, available=False, reason="box unparseable")
    result = enforce_gate.enforce_live(_live_args(comp_path, "glassy", 35, True))
    assert result["verdict"] == "PASS"
    assert "finite_size" not in result["binding_gates"]
    assert result["finite_size_verdict"] is None


def test_l_below_ree_alone_does_not_block(tmp_path):
    """L < R_ee is advisory: common in published polymer MD and much weaker than 2*Rg."""
    comp_path = _with_finite_size(
        tmp_path, available=True, **{"pass": True}, verdict="SIZE_PASS",
        L_over_2Rg=1.05, L_over_Ree=0.85, ree_self_image_flag=True,
    )
    result = enforce_gate.enforce_live(_live_args(comp_path, "rubbery", None, True))
    assert result["verdict"] == "PASS"


# ─── n_eff remedy is sized from the deficit ────────────────────────────────────

def test_n_eff_remedy_scales_extension_with_deficit(tmp_path):
    """PMMA1's real n_eff of 11 against a floor of 20 -> 1.5 * 20/11 ~= 2.7 ns."""
    comp_path = _write_comp(tmp_path, kinetic_trap_flag=False)
    comp = json.loads(comp_path.read_text())
    comp["thermo"]["n_eff_density"] = {"pass": False, "n_eff": 11, "n_eff_min": 20}
    comp_path.write_text(json.dumps(comp))

    result = enforce_gate.enforce_live(_live_args(comp_path, "glassy", 35, True))
    assert result["verdict"] == "EXTEND"
    assert "extend_ns=2.7" in result["remedy"]
