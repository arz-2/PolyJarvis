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
    path = tmp_path / "equilibration.json"
    path.write_text(json.dumps(comp))
    return path


def _live_args(comp_path, regime, dp, ct_gate_reliable):
    return SimpleNamespace(
        comprehensive_json=str(comp_path), regime=regime, dp=dp,
        ct_gate_reliable=ct_gate_reliable, tg_k=None,
        t_equil_k=None, glass_data=None, melt_data=None, out_dir=None,
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


# ─── density_value_binding: unconditional self-consistency trigger, no exp data ────

def test_cooling_trigger_never_fires_without_both_data_paths(tmp_path):
    """No glass_data/melt_data (e.g. the phase=melt checkpoint) must never misfire
    needs_probe -- there is no post-cool glass state to assess yet."""
    comp_path = _write_comp(tmp_path, kinetic_trap_flag=False)
    args = _live_args(comp_path, "glassy", 35, True)
    result = enforce_gate.enforce_live(args)
    assert "needs_probe" not in result
    assert result["density_value_binding"] == "n/a"


def test_cooling_trigger_fires_needs_probe_with_no_exp_density_arg(tmp_path):
    """With both data paths present, the probe request must never reference an
    experimental density -- assess_cooling_contraction_args carries no such key."""
    comp_path = _write_comp(tmp_path, kinetic_trap_flag=False)
    args = _live_args(comp_path, "glassy", 35, True)
    args.glass_data = str(tmp_path / "npt_prod300_out.data")
    args.melt_data = str(tmp_path / "npt_production_out.data")
    args.out_dir = str(tmp_path)
    args.tg_k = 373.0
    args.t_equil_k = 550.0
    result = enforce_gate.enforce_live(args)
    assert result["needs_probe"] is True
    cc_args = result["assess_cooling_contraction_args"]
    assert "exp_density_gcm3" not in cc_args
    assert "alpha_glass" not in cc_args
    assert "alpha_melt" not in cc_args
    assert cc_args["tg_K"] == 373.0


def test_cooling_verdict_ok_satisfies_without_blocking(tmp_path):
    comp_path = _write_comp(tmp_path, kinetic_trap_flag=False)
    cooling_path = tmp_path / "cooling_contraction.json"
    cooling_path.write_text(json.dumps({"verdict": "OK"}))
    args = _live_args(comp_path, "glassy", 35, True)
    args.glass_data = str(tmp_path / "npt_prod300_out.data")
    args.melt_data = str(tmp_path / "npt_production_out.data")
    args.out_dir = str(tmp_path)
    result = enforce_gate.enforce_live(args)
    assert result["verdict"] == "PASS"
    assert result["density_value_binding"] == "satisfied (OK)"


def test_cooling_verdict_insufficient_data_satisfies_without_blocking(tmp_path):
    """Must not keep re-triggering needs_probe past the wrapper's one retry."""
    comp_path = _write_comp(tmp_path, kinetic_trap_flag=False)
    cooling_path = tmp_path / "cooling_contraction.json"
    cooling_path.write_text(json.dumps({"verdict": "INSUFFICIENT_DATA"}))
    args = _live_args(comp_path, "glassy", 35, True)
    args.glass_data = str(tmp_path / "npt_prod300_out.data")
    args.melt_data = str(tmp_path / "npt_production_out.data")
    args.out_dir = str(tmp_path)
    result = enforce_gate.enforce_live(args)
    assert "needs_probe" not in result
    assert result["verdict"] == "PASS"


def test_cooling_verdict_under_annealed_is_reported_but_advisory(tmp_path):
    """density_value_binding was Class A and routed STRUCTURAL_FAIL until 2026-09-01.

    decision_rationale's own class_A_is_always_worth_paying criterion is that the class's
    structural remedy removes the defect COMPLETELY at a bounded cost. Measurement retired that:
    across 21 archived multi-rate sweeps glass density moves ~1.1% per DECADE of cooling rate, so
    slower_cooling (x2 then x4, capped) recovers 0.33-0.67% against archived shortfalls of 3-9%.
    The maximum remedy clears none of the flagged archived runs -- the gate failed its own class's
    defining criterion.

    The shortfall is still real and still reported. It is a Class C statement about an inherent MD
    limitation (expected_contraction is built from experimental-rate expansivities, and MD cools
    ~12 decades faster than DSC), not a per-run admissibility failure."""
    comp_path = _write_comp(tmp_path, kinetic_trap_flag=False)
    cooling_path = tmp_path / "cooling_contraction.json"
    cooling_path.write_text(json.dumps({"verdict": "UNDER_ANNEALED_COOLING",
                                         "extrapolation_reliable": True}))
    args = _live_args(comp_path, "glassy", 35, True)
    args.glass_data = str(tmp_path / "npt_prod300_out.data")
    args.melt_data = str(tmp_path / "npt_production_out.data")
    args.out_dir = str(tmp_path)
    result = enforce_gate.enforce_live(args)

    assert result["verdict"] != "STRUCTURAL_FAIL"
    assert "density_value_binding" not in result["failing_binding_gates"]
    # Reported, not silently dropped: the verdict must survive into the gate payload so the
    # run summary and the recovery agent still see it.
    assert result["cooling_verdict"] == "UNDER_ANNEALED_COOLING"


def test_density_value_binding_is_not_a_structural_gate():
    """Pins the membership itself, so re-adding it cannot pass unnoticed."""
    assert "density_value_binding" not in enforce_gate.STRUCTURAL_GATES
    assert "density_value_binding" not in enforce_gate.EXTENDABLE_GATES


# ─── resolve_regime(): assessment temperature vs Tg, not a hardcoded 300 K ─────
#
# The gate set is chosen by the state of the cell AT THE TEMPERATURE IT IS ASSESSED.
# check_equilibration_comprehensive always gates npt_final, which cool_block ramps down to
# final_T_K -- 300 K is that knob's default, not its definition, and it is user-facing.
# The previous form compared T_workflow against a literal 300, which encoded `exp_Tg < 300`
# indirectly and is correct only while final_T_K is 300.

def test_regime_matches_the_legacy_proxy_at_300K():
    """Behaviour-preserving at the default: for every curated class/member combination the
    new (final_T_K vs Tg) rule must agree with the old (T_workflow <= 300) proxy. Verified
    across all 48 combinations when this landed; this pins the equivalence."""
    import stage_params as sp
    rules = json.loads((REPO_ROOT / "guides" / "polymer_rules.json").read_text())
    checked = 0
    for cid, entry in rules["classes"].items():
        members = list((entry.get("member_smiles") or {}).items()) or [("(class)", [None])]
        for _name, smis in members:
            smiles = smis[0] if smis else None
            tg = sp._regime_exp_tg(entry, smiles)
            t_workflow = (300.0 if isinstance(tg, (int, float)) and tg < 300
                          else entry["T_equil_K"])
            legacy = enforce_gate.resolve_regime_legacy(t_workflow)   # pre-fix proxy
            new = enforce_gate.resolve_regime(300.0, tg)              # assess at the default
            assert legacy == new, (
                f"{cid}/{_name}: Tg={tg} T_workflow={t_workflow} -> legacy {legacy}, new {new}"
            )
            checked += 1
    assert checked >= 40, f"only {checked} combinations checked"


@pytest.mark.parametrize("final_t,tg,expected", [
    (300.0, 200.0, "rubbery"),   # above Tg at the assessment temperature
    (300.0, 400.0, "glassy"),    # below Tg
    (350.0, 200.0, "rubbery"),   # the case the 300 K proxy got wrong: still above Tg
    (250.0, 270.0, "glassy"),    # user cooled below Tg -> glass, though 250 < 300
    (400.0, 400.0, "glassy"),    # exactly at Tg is not "above" it
])
def test_regime_follows_the_assessment_temperature(final_t, tg, expected):
    assert enforce_gate.resolve_regime(final_t, tg) == expected


def test_regime_falls_to_glassy_when_tg_is_unresolvable():
    """Glassy is the stricter gate set (density_drift binds), so an unknown Tg must not
    silently buy the more permissive rubbery clause."""
    assert enforce_gate.resolve_regime(300.0, None) == "glassy"
    assert enforce_gate.resolve_regime(None, 200.0) == "glassy"
    # the retired proxy is still available for plans with no Tg at all, and still says <=300
    assert enforce_gate.resolve_regime_legacy(300.0) == "rubbery"


def test_live_and_retrospective_regimes_agree():
    """enforce_live() receives args.regime from stage_params._regime; enforce() computes its
    own via resolve_regime. A divergence adjudicates the same run two different ways."""
    import stage_params as sp
    rules = json.loads((REPO_ROOT / "guides" / "polymer_rules.json").read_text())
    for cid, entry in rules["classes"].items():
        members = list((entry.get("member_smiles") or {}).items()) or [("(class)", [None])]
        for _name, smis in members:
            args = SimpleNamespace(smiles=(smis[0] if smis else None), exp_tg_K=None,
                                   final_T_K=None)
            live = sp._regime(args, entry)
            tg = sp._regime_exp_tg(entry, args.smiles)
            retro = enforce_gate.resolve_regime(entry.get("final_T_K", 300.0), tg)
            assert live == retro, f"{cid}/{_name}: live {live} vs retrospective {retro}"
