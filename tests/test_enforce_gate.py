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


# ─── melt-density gate (item 6) ──────────────────────────────────────────────
#
# The phase=melt gate ran with exp_density_gcm3=null, so density_in_band was never
# set and a melt deficit could only be found after the cooling ramp was paid for.
# db/polymer_db.sqlite carries 53 Mark 2007 melt rho(T) equations; this reads one
# off at the run's own T_equil.


def test_melt_gate_binds_only_on_a_measured_deficit():
    from enforce_gate import melt_density_gate

    assert melt_density_gate({"verdict": "MELT_RHO_DEFICIT"}) is False
    assert melt_density_gate({"verdict": "MELT_RHO_PASS"}) is True


def test_no_reference_leaves_the_gate_unarmed_never_passing():
    """PSFO runs at 427 C against a 371 C equation ceiling, PKTN 497 vs 400, PIMD has no
    equation at all -- the rigid aromatics are exactly where the reference is worst. An
    absent reference must not read as agreement."""
    from enforce_gate import melt_density_gate

    assert melt_density_gate({"verdict": "MELT_RHO_NO_REFERENCE"}) is None
    assert melt_density_gate(None) is None
    assert melt_density_gate({}) is None


def test_melt_gate_is_binding_and_structural():
    import enforce_gate as eg

    assert "melt_density_in_band" in eg.BINDING_GLASSY
    assert "melt_density_in_band" in eg.BINDING_RUBBERY
    # No amount of extra NPT at the melt temperature moves an equilibrium density that the
    # force field puts in the wrong place; the remedy is a longer anneal or a different FF.
    assert "melt_density_in_band" in eg.STRUCTURAL_GATES
    assert "melt_density_in_band" not in eg.EXTENDABLE_GATES


def test_t_equil_k_accepts_the_null_the_melt_phase_passes():
    """phase=melt passes null for every cooling-contraction arg. --t-equil-k was type=float
    with no null lambda, so the --live CLI crashed on exactly that call -- invisible until
    this item made the path live."""
    import subprocess
    import sys
    from pathlib import Path

    script = Path(__file__).resolve().parents[1] / "orchestration" / "scripts" / "enforce_gate.py"
    res = subprocess.run([sys.executable, str(script), "--live",
                          "--comprehensive-json", "/nonexistent.json",
                          "--t-equil-k", "null", "--tg-k", "null",
                          "--exp-density-gcm3", "null"],
                         capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    assert "invalid" not in res.stderr.lower()


def _melt_ref(cls, t_equil_K, rho):
    import subprocess
    import sys
    from pathlib import Path
    script = (Path(__file__).resolve().parents[1] / "orchestration" / "scripts"
              / "melt_density_reference.py")
    res = subprocess.run([sys.executable, str(script), "--polymer_class", cls,
                          "--t_equil_K", str(t_equil_K), "--rho_melt", str(rho)],
                         capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout)


def test_reference_reproduces_the_a1_oracle():
    """a1_experimental_melt.md is the frozen oracle this policy was promoted from. These
    four rows carry its three distinct outcomes; a diff here is a promotion bug."""
    pmma = _melt_ref_named("Poly(methylmethacrylate)", 277 + 273.15, 1.0483, "PACR")
    assert pmma["status"] == "NEAR_RANGE" and pmma["evidence"] == "decisive"
    assert pmma["n_equations"] == 5                      # isotactic PMMA excluded
    assert abs(pmma["melt_gap_pct"] - 1.03) < 0.06
    assert pmma["verdict"] == "MELT_RHO_PASS"

    ps1 = _melt_ref_named("Polystyrene", 277 + 273.15, 0.8815, "PSTR")
    assert ps1["status"] == "IN_RANGE" and ps1["n_equations"] == 3
    assert abs(ps1["melt_gap_pct"] - -3.95) < 0.06
    # PS1's gap exceeds PS's own reference spread; PS2-4 do not. a1 reports the family as
    # MIXED for exactly this reason and warns against collapsing it to a mean.
    assert ps1["verdict"] == "MELT_RHO_DEFICIT"
    assert _melt_ref_named("Polystyrene", 277 + 273.15, 0.9077,
                           "PSTR")["verdict"] == "MELT_RHO_PASS"

    psu = _melt_ref_named("Polysulfone, (with Bisphenol A)", 427 + 273.15, 1.0451, "PSFO")
    assert psu["status"] == "T_EQUIL_OUTSIDE_EQUATION_RANGE"
    assert psu["evidence"] == "indicative"               # under half a fit-width past
    assert psu["verdict"] == "MELT_RHO_NO_REFERENCE"

    pla = _melt_ref_named("Poly(lactic acid)", 347 + 273.15, 1.0878, "PEST")
    assert pla["status"] == "NO_EXPERIMENTAL_EQUATION"
    assert pla["verdict"] == "MELT_RHO_NO_REFERENCE"


def test_tolerance_is_measured_not_chosen():
    """The deficit threshold is the spread among the independent equations for that
    polymer -- how precisely experiment itself pins rho here. Below it, 'deficit' is not
    separable from reference uncertainty."""
    ref = _melt_ref_named("Poly(methylmethacrylate)", 277 + 273.15, 1.0483, "PACR")
    gaps = [e["gap_pct"] for e in ref["equations"] if e.get("gap_pct") is not None]
    assert ref["tolerance_pp"] == round(max(gaps) - min(gaps), 2)


def test_single_equation_cannot_adjudicate_a_negative_gap():
    """With one equation there is no measured reference tolerance. A positive gap still
    settles it; a negative one must be None, never False."""
    pvc_low = _melt_ref_named("Poly(vinylchloride)", 120 + 273.15, 1.20, "PVNL")
    assert pvc_low["n_equations"] == 1 and pvc_low["tolerance_pp"] is None
    assert pvc_low["melt_gap_pct"] < 0
    assert pvc_low["melt_deficient"] is None
    assert pvc_low["verdict"] == "MELT_RHO_NO_REFERENCE"

    pvc_high = _melt_ref_named("Poly(vinylchloride)", 120 + 273.15, 1.45, "PVNL")
    assert pvc_high["melt_deficient"] is False
    assert pvc_high["verdict"] == "MELT_RHO_PASS"


def test_pvc_does_not_resolve_to_polystyrene():
    """CLASS_CANONICAL_PATTERN["PVNL"] is ["Poly(vinyl chloride)", "Polystyrene"], and
    "Poly(vinyl chloride)" never LIKE-matches the equation-bearing "Poly(vinylchloride)".
    Without the loose-normalized pass, PVC falls through to the second pattern and is
    graded against polystyrene's rho(T). The class path additionally refuses to bind at
    all now, so this checks both halves."""
    assert _melt_ref("PVNL", 120 + 273.15, 1.20)["verdict"] == "MELT_RHO_NO_REFERENCE"
    ref = _melt_ref_named("Poly(vinylchloride)", 120 + 273.15, 1.20, "PVNL")
    assert ref["n_equations"] == 1
    exp = ref["exp_density_gcm3"]
    assert exp is not None and exp > 1.2, f"PVC melt rho ~1.3, got {exp} (polystyrene is ~0.92)"


# ─── member-specific melt reference ──────────────────────────────────────────
#
# A class-level lookup names the class's FLAGSHIP polymer, not this run's member,
# and most classes hold several members with genuinely different melt densities.
# Grading a correct cell against the wrong polymer manufactures a verdict in
# either direction: measured PMA-vs-PMMA gives a false MELT_RHO_DEFICIT (-5.6%
# against a 2.7 pp tolerance), P2VP-vs-PS a false MELT_RHO_PASS (+15.5%).


def test_class_fallback_reports_but_never_binds():
    for cls, rho in (("PACR", 0.98), ("PSTR", 1.06), ("POXI", 0.973)):
        ref = _melt_ref(cls, 550, rho)
        assert ref["verdict"] == "MELT_RHO_NO_REFERENCE", cls
        assert ref["melt_deficient"] is None, cls
        assert ref["status"] in ("CLASS_MATCH_NOT_MEMBER_SPECIFIC",
                                 "T_EQUIL_OUTSIDE_EQUATION_RANGE",
                                 "NO_EXPERIMENTAL_EQUATION"), (cls, ref["status"])


def _melt_ref_named(name, t_equil_K, rho, cls=None):
    import subprocess
    import sys
    from pathlib import Path
    script = (Path(__file__).resolve().parents[1] / "orchestration" / "scripts"
              / "melt_density_reference.py")
    cmd = [sys.executable, str(script), "--polymer_name", name,
           "--t_equil_K", str(t_equil_K), "--rho_melt", str(rho)]
    if cls:
        cmd += ["--polymer_class", cls]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout)


def test_named_member_binds_against_its_own_polymer():
    """PEO/PEG must reach polyoxyethylene, not the class representative
    polyoxymethylene — an 18% denser polymer that would read as a large deficit."""
    peo = _melt_ref_named("Polyoxyethylene", 500, 0.973, "POXI")
    assert peo["match_confidence"] == "high"
    assert peo["verdict"] == "MELT_RHO_PASS"
    assert abs(peo["melt_gap_pct"]) < 1.0

    pmma = _melt_ref_named("Poly(methylmethacrylate)", 550, 1.0483, "PACR")
    assert pmma["verdict"] == "MELT_RHO_PASS"


def test_a_named_polymer_never_falls_back_to_the_class():
    """Supplying a name that has no melt equation must yield no reference, not the
    class representative's — that would answer a question about another polymer."""
    ref = _melt_ref_named("Poly(acrylic acid)", 550, 1.20, "PACR")
    assert ref["verdict"] == "MELT_RHO_NO_REFERENCE"
    assert ref.get("exp_density_gcm3") is None


def test_every_mapped_member_resolves_to_a_polymer_with_melt_equations():
    """polymer_rules.json's melt_reference_db_names must name real, equation-bearing DB
    polymers — a typo silently unarms the gate for that member."""
    import json as _json
    from pathlib import Path
    rules = _json.loads(
        (Path(__file__).resolve().parents[1] / "guides" / "polymer_rules.json").read_text()
    )["classes"]
    checked = 0
    for cid, c in rules.items():
        for member, db_name in (c.get("melt_reference_db_names") or {}).items():
            ref = _melt_ref_named(db_name, 400, 1.0, cid)
            assert ref["match_confidence"] == "high", f"{cid}/{member}: {db_name} unmatched"
            assert ref.get("n_equations", 0) >= 1, f"{cid}/{member}: {db_name} has no melt eq"
            checked += 1
    assert checked >= 25, f"only {checked} mappings checked"
