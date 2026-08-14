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


def test_bilinear_curvefit_reports_tg_uncertainty():
    """The physics-validity swap routinely makes bilinear the primary fit; without an
    interval run_summary grades a bare point against a band and a near-miss reads FAIL."""
    from extract_thermal import curvefit_bilinear

    T, rho = _synthetic_bilinear(1e-3)
    res = curvefit_bilinear(T, rho, tg_hint=395.0)
    assert res is not None
    assert res.get("tg_alt_uncertainty_K") is not None
    assert res["tg_alt_uncertainty_K"] > 0


def test_bilinear_uncertainty_is_not_attached_to_the_seed_tg():
    """Tg_K from this fit is the unrefined seed (curve_fit cannot move a np.where breakpoint),
    so the sigma -- which describes Tg_alt_K -- must not be published under the name the
    headline's error bar would be read from."""
    from extract_thermal import curvefit_bilinear

    T, rho = _synthetic_bilinear(1e-3)
    res = curvefit_bilinear(T, rho, tg_hint=395.0)
    assert "tg_uncertainty_K" not in res
    # The seed really is returned verbatim -- pins the defect this naming guards against.
    assert res["Tg_K"] == pytest.approx(395.0, abs=0.01)
    assert abs(res["Tg_alt_K"] - res["Tg_K"]) > 1.0


def test_tg_uncertainty_scales_with_scatter_not_pinned_to_zero():
    """Guards the actual defect: pcov[4,4] is structurally zero because bilinear_indep
    switches on np.where(T < Tg), so reporting it claimed +/-0 K at any noise level. The
    uncertainty must be propagated from the genuinely fitted line parameters instead."""
    from extract_thermal import curvefit_bilinear

    sigmas = []
    for noise in (2e-4, 1e-3, 3e-3):
        T, rho = _synthetic_bilinear(noise)
        res = curvefit_bilinear(T, rho, tg_hint=395.0)
        assert res["tg_alt_uncertainty_K"] > 0, f"sigma collapsed to zero at noise={noise}"
        sigmas.append(res["tg_alt_uncertainty_K"])

    assert sigmas[0] < sigmas[1] < sigmas[2], "sigma must grow with scatter"
    assert sigmas[2] > 5 * sigmas[0], "sigma must scale with scatter, not be a constant"


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
