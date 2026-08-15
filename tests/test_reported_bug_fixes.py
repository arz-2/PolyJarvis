"""Regression tests for the reported-defect pass.

Each test pins the specific wrong behaviour that was observed, so a revert fails loudly.
"""
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "mcp-servers" / "mcp-lammps-engine" / "analysis_scripts"))
sys.path.insert(0, str(REPO / "orchestration" / "scripts"))
sys.path.insert(0, str(REPO / "mcp-servers" / "mcp-mol-builder-server"))


# ── Bug 1: homogeneity floor must match the units of the CV it is subtracted from ──

def test_poisson_floor_is_mass_weighted_not_count_based():
    """cv_mean bins by mass, so the shot-noise floor is the compound-Poisson mass floor
    sqrt(<m^2>)/<m>/sqrt(apv). The count floor 1/sqrt(apv) sits ~1.3x too low on an H-rich
    cell and manufactured a STRUCTURAL_FAIL on uniform melts (observed on PMMA1)."""
    # PS repeat unit C8H8: 8 carbons, 8 hydrogens.
    masses = np.array([12.011] * 8 + [1.008] * 8)
    disp = math.sqrt((masses ** 2).mean()) / masses.mean()
    assert disp == pytest.approx(1.309, abs=0.01), "mass dispersion for C8H8"

    apv = 29.7
    count_floor = 1.0 / math.sqrt(apv)
    mass_floor = disp / math.sqrt(apv)
    assert count_floor == pytest.approx(0.1834, abs=0.001)
    assert mass_floor == pytest.approx(0.2401, abs=0.002)

    # A measured mass CV that is genuinely at the noise floor must yield zero signal.
    cv_mean = mass_floor
    assert math.sqrt(max(cv_mean ** 2 - mass_floor ** 2, 0.0)) == 0.0
    # ...but would have reported a large phantom signal against the old count floor.
    phantom = math.sqrt(max(cv_mean ** 2 - count_floor ** 2, 0.0))
    assert phantom > 0.11, "old floor produced a gate-tripping phantom signal"


def test_density_homogeneity_reports_mass_dispersion():
    """The floor's mass-dispersion factor is emitted so a verdict can be re-derived."""
    import check_equilibration_comprehensive as ceq
    src = Path(ceq.__file__).read_text()
    assert '"mass_dispersion"' in src
    assert "mass_dispersion / math.sqrt(atoms_per_voxel)" in src


# ── Bug 4: bilinear fit must report a Tg uncertainty ──

def _synthetic_bilinear(noise, seed=0, Tg_true=400.0):
    T = np.arange(250.0, 550.0, 10.0)
    rho = np.where(T < Tg_true,
                   1.20 - 2.0e-4 * (T - 300.0),
                   1.20 - 2.0e-4 * (Tg_true - 300.0) - 6.0e-4 * (T - Tg_true))
    return T, rho + np.random.default_rng(seed).normal(0, noise, len(T))


def test_bilinear_tg_is_independent_of_the_seed():
    """THE defect this rewrite exists for. curve_fit cannot move a np.where(T < Tg) breakpoint
    -- the gradient is identically zero -- so the old fit returned its initial guess verbatim
    (measured on archived data: PMMA2/tg_r40 and PS3/tg_r400 reproduce exactly as seeds).
    The exhaustive search must give the same answer whatever hint it is handed."""
    from extract_thermal import curvefit_bilinear

    T, rho = _synthetic_bilinear(5e-4)
    answers = [curvefit_bilinear(T, rho, tg_hint=h)["Tg_K"]
               for h in (320.0, 360.0, 390.0, 420.0, 460.0)]
    assert max(answers) - min(answers) < 1e-6, f"Tg still tracks the seed: {answers}"
    assert curvefit_bilinear(T, rho)["Tg_K"] == pytest.approx(answers[0], abs=1e-6)
    # And it must land on the true breakpoint, not merely be self-consistent.
    assert answers[0] == pytest.approx(400.0, abs=15.0)


def test_bilinear_reports_tg_uncertainty_for_its_own_headline():
    """With the breakpoint genuinely fitted, sigma describes Tg_K itself, so it is published
    as tg_uncertainty_K again -- the interval run_summary needs to grade against a band."""
    from extract_thermal import curvefit_bilinear

    res = curvefit_bilinear(*_synthetic_bilinear(1e-3))
    assert res["tg_uncertainty_K"] is not None and res["tg_uncertainty_K"] > 0
    assert "tg_alt_uncertainty_K" not in res, "the audit-only stopgap should be gone"


def test_tg_uncertainty_scales_with_scatter_not_pinned_to_zero():
    """pcov[4,4] was structurally zero, so reporting it claimed +/-0 K at any noise level."""
    from extract_thermal import curvefit_bilinear

    sigmas = []
    for noise in (2e-4, 1e-3, 3e-3):
        res = curvefit_bilinear(*_synthetic_bilinear(noise))
        assert res["tg_uncertainty_K"] > 0, f"sigma collapsed to zero at noise={noise}"
        sigmas.append(res["tg_uncertainty_K"])

    assert sigmas[0] < sigmas[1] < sigmas[2], "sigma must grow with scatter"
    assert sigmas[2] > 5 * sigmas[0], "sigma must scale with scatter, not be a constant"


def test_physics_constraints_are_inside_the_search():
    """Bare argmin-SSR picks near-parallel branches that fit well and intersect thousands of K
    away (an unconstrained prototype returned -3644 K on real PMMA3 bins). Every returned fit
    must satisfy the constraints _hard_violations checks, or be flagged as unconstrained."""
    from extract_thermal import curvefit_bilinear

    res = curvefit_bilinear(*_synthetic_bilinear(1e-3))
    assert res["breakpoint_constrained"] is True
    assert res["a_glassy"] < 0 and res["a_rubbery"] < 0
    assert res["a_rubbery"] < res["a_glassy"], "rubbery branch must be the steeper one"
    T, _ = _synthetic_bilinear(1e-3)
    span = T.max() - T.min()
    assert T.min() + 0.05 * span <= res["Tg_K"] <= T.max() - 0.05 * span


def test_pure_noise_is_not_silently_reported_as_a_transition():
    """No real breakpoint => many splits tie, or the winner's intersection is loose. Either
    way the ambiguity measure must be large enough to route to TG_REVIEW."""
    from extract_thermal import curvefit_bilinear

    T = np.arange(250.0, 550.0, 10.0)
    rho = 1.15 - 3.0e-4 * (T - 300.0) + np.random.default_rng(3).normal(0, 3e-3, len(T))
    res = curvefit_bilinear(T, rho)
    if res is None:
        return  # no valid split at all is also an acceptable outcome
    ambiguity = max(res["breakpoint_spread_K"], 2.0 * (res["tg_uncertainty_K"] or 0.0))
    assert ambiguity > 20.0, f"a straight line was reported as a resolved transition: {res}"


def test_no_valid_split_still_returns_a_fit_for_the_swap_path():
    """Bilinear is the swap target when the hyperbola is rejected; returning None there would
    leave the run with no fit at all. It must degrade to an unconstrained fit and say so."""
    from extract_thermal import curvefit_bilinear

    # Density RISING with T, with a kink so the branches are not collinear: every split
    # violates the slope-sign constraint, but an intersection is still well defined.
    T = np.arange(250.0, 450.0, 10.0)
    rho = np.where(T < 350.0, 0.9 + 3.0e-4 * (T - 250.0), 0.93 + 9.0e-4 * (T - 350.0))
    rho = rho + np.random.default_rng(7).normal(0, 1e-4, len(T))
    res = curvefit_bilinear(T, rho)
    assert res is not None, "must not strand the swap path"
    assert res["breakpoint_constrained"] is False
    assert res["a_glassy"] > 0, "the returned fit is the constraint-violating one, as flagged"


# ── Bug 16: cache write must gate on derived output, not on the reliability flags ──

def _write_cache(tmp_path, fields):
    from write_characterization_cache import write_characterization
    return write_characterization(tmp_path / "cache.json", "C=C", fields)


def test_cache_not_written_when_k0_reliable_but_nothing_derived(tmp_path):
    """K0-reliable + tau-unreliable derives zero knobs (every knob needs tau), but satisfied
    the old any(flags) gate — writing an empty entry that permanently marked the SMILES
    non-novel, since the novelty check is bare key existence."""
    res = _write_cache(tmp_path, {
        "probe_tau_relax_reliable": False,
        "probe_K0_reliable": True,
        "bulk_modulus_GPa": 3.1,
    })
    assert res["written"] is False
    assert res["reason"] == "no_derived_field"


def test_cache_written_when_a_knob_was_actually_derived(tmp_path):
    res = _write_cache(tmp_path, {
        "probe_tau_relax_reliable": True,
        "probe_K0_reliable": False,
        "derived_t_equil_ns": 12.5,
    })
    assert res["written"] is True
    assert "derived_t_equil_ns" in res["fields_written"]


def test_cache_ignores_null_derived_fields(tmp_path):
    res = _write_cache(tmp_path, {
        "probe_tau_relax_reliable": True,
        "derived_t_equil_ns": None,
    })
    assert res["written"] is False


# ── Bug 7: a relative output_dir silently resolved against LAMBDA_WORKDIR ──

def test_require_output_dir_rejects_relative_path():
    sys.path.insert(0, str(REPO / "mcp-servers" / "mcp-lammps-engine"))
    import server

    with pytest.raises(ValueError, match="absolute path"):
        server._require_output_dir("bulk_analysis", "extract_bulk_modulus", "<legacy>")
    with pytest.raises(ValueError, match="required"):
        server._require_output_dir("", "extract_bulk_modulus", "<legacy>")
    server._require_output_dir("/abs/raw", "extract_bulk_modulus", "<legacy>")  # no raise


def test_every_output_dir_tool_validates_it():
    """The guard only helps on paths that call it; the Murnaghan extractor did not."""
    src = (REPO / "mcp-servers/mcp-lammps-engine/server.py").read_text()
    for tool in ("extract_bulk_modulus", "extract_bulk_modulus_deform",
                 "extract_bulk_modulus_murnaghan", "extract_thermal",
                 "extract_equilibrated_density", "check_equilibration_comprehensive"):
        assert f'_require_output_dir(output_dir, "{tool}"' in src, f"{tool} does not validate"


# ── Bug 8: the gate verdict must leave an audit record, including on failure ──

def test_gate_verdict_is_persisted_including_failures(tmp_path):
    sys.path.insert(0, str(REPO / "mcp-servers" / "mcp-lammps-engine"))
    import server

    ok = server._save_gate_verdict(tmp_path, {"verdict": "PASS"})
    saved = json.loads((tmp_path / "equilibration_gate.json").read_text())
    assert saved["verdict"] == "PASS"
    assert ok["saved_to"].endswith("equilibration_gate.json")

    # A blown-up probe is the case most worth having a record of.
    server._save_gate_verdict(tmp_path, {"status": "failed", "error": "probe exploded"})
    assert json.loads((tmp_path / "equilibration_gate.json").read_text())["status"] == "failed"

    # A missing out_dir must not raise -- the verdict still returns.
    assert server._save_gate_verdict(None, {"verdict": "PASS"})["verdict"] == "PASS"


# ── Bug 18: ff_confidence read a field retired in 49877fe, grading every class "low" ──

def test_ff_confidence_derived_from_citation_not_retired_field():
    import ff_routing

    rules = ff_routing.load_polymer_rules()["classes"]
    assert all("confidence" not in e for e in rules.values()), \
        "classes.<CLASS>.confidence was retired; nothing should reintroduce it"

    got = ff_routing.get_preferred_ff("PSTR")
    assert got["ff_confidence"] == "cited"
    # And it must agree with what gen_prompt writes into the build prompt.
    expected = "cited" if rules["PSTR"].get("ff_justification_doi") else "uncited"
    assert got["ff_confidence"] == expected

    assert not any(ff_routing.get_preferred_ff(c)["ff_confidence"] == "low" for c in rules)


# ── Bug 2: cooling-contraction densities must be plateau means, not one final frame ──

def test_assess_cooling_contraction_prefers_log_plateau_over_final_frame():
    base = REPO / "data" / "PMMA1" / "lammps" / "equil"
    glass_data = base / "npt_prod300" / "npt_prod300_out.data"
    melt_log = base / "npt_production" / "npt_production.log"
    if not (glass_data.exists() and melt_log.exists()):
        pytest.skip("PMMA1 artifacts not present")

    script = REPO / "mcp-servers/mcp-lammps-engine/analysis_scripts/assess_cooling_contraction.py"
    common = [sys.executable, str(script), "--glass_data", str(glass_data),
              "--melt_data", str(base / "npt_production" / "npt_production_out.data"),
              "--exp_density_gcm3", "1.19", "--tg_K", "378", "--t_equil_K", "550"]

    frame = json.loads(subprocess.run(common, capture_output=True, text=True).stdout)
    plateau = json.loads(subprocess.run(
        common + ["--melt_log", str(melt_log),
                  "--glass_log", str(base / "npt_prod300" / "npt_prod300.log")],
        capture_output=True, text=True).stdout)

    assert frame["density_provenance"]["rho_melt"].startswith("final_frame")
    assert plateau["density_provenance"]["rho_melt"].startswith("plateau_mean")
    assert plateau["rho_melt_sd"] is not None
    # The single frame is a draw from the NPT distribution, not the stage density.
    assert frame["rho_melt"] != plateau["rho_melt"]


# ── Bug 15: a recorded knob the deck silently overrides is a false protocol record ──

def test_overridden_tg_steps_per_t_is_flagged():
    from validate_run_plan import _overridden_param_findings

    plan = {"decided_params": {"tg_steps_per_t": 500000, "tg_rate_index": 0}}
    findings = _overridden_param_findings(plan)
    assert len(findings) == 1
    assert findings[0]["check"] == "decided_param_overridden"

    # Only fires when the overriding knob is actually set.
    assert _overridden_param_findings({"decided_params": {"tg_steps_per_t": 500000}}) == []


# ── Two semantic plan checks the validator scored 0 on ────────────────────────
# validate_run_plan does stage schema and coverage, not semantics. Both of these were
# real critic findings the script missed: PLA1 argued in two places that PEST's
# PET-derived exp_K_GPa must not grade PLA and armed nothing, and PSU1 asserted
# overall_pass=true on a class whose own policy calls it unsatisfiable by construction.

def test_prose_against_a_class_band_must_be_armed_in_decided_params():
    from validate_run_plan import _prose_prohibition_findings

    plan = {"decided_params": {},
            "assumptions": ["PEST exp_K_GPa is PET-derived and must not grade PLA"]}
    f = _prose_prohibition_findings(plan)
    assert len(f) == 1 and f[0]["severity"] == "structural"
    assert "exp_K_GPa" in f[0]["detail"]

    # An explicit null shadows the class value in {**cls, **decided_params} — armed.
    assert _prose_prohibition_findings(
        {"decided_params": {"exp_K_GPa": None},
         "assumptions": ["PEST exp_K_GPa must not grade PLA"]}) == []
    # Prose that makes no claim about a band is not a finding.
    assert _prose_prohibition_findings(
        {"decided_params": {}, "assumptions": ["dp=40 chosen for Rg"]}) == []


def test_overall_pass_as_a_success_criterion_is_a_finding():
    from validate_run_plan import _gate_boolean_findings

    f = _gate_boolean_findings({"planned_stages": [
        {"stage": "equil",
         "success_criteria": {"check_equilibration_comprehensive.overall_pass": True}}]})
    assert len(f) == 1 and f[0]["severity"] == "structural"
    # The binding form — a routed verdict — is fine.
    assert _gate_boolean_findings({"planned_stages": [
        {"stage": "equil", "success_criteria": {"equil_verdict": "PASS"}}]}) == []


def test_member_match_finds_the_key_inside_a_prefixed_run_name():
    """startswith missed every descriptive prefix and fell through to a class MEDIAN:
    cis-PBD1 failed to match PBD and was graded against cis-polyisoprene's 200 K."""
    import json
    sys.path.insert(0, str(REPO / "orchestration" / "scripts"))
    import gen_prompt as g

    classes = json.loads((REPO / "guides" / "polymer_rules.json").read_text())["classes"]
    assert g._exp_tg_point(classes["PDIE"], "cis-PBD1") == 181     # was 200
    assert g._exp_tg_range(classes["PDIE"], "cis-PBD3") == [161, 201]
    # Longest key first, or PMMA1 takes PMA.
    assert g._exp_tg_point(classes["PACR"], "PMMA1") == 378
    assert g._exp_tg_point(classes["PACR"], "PMA2") == 281
    # No member in the name still falls back to the class median, not a crash.
    assert g._exp_tg_point(classes["PDIE"], "RUN9") in (181, 200)
