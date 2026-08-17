"""Integration test for generate_run_summary.py.

Locks in the fix where run_summary.json came out under-populated (PEG1):
  * convergence + structural_checks were null because the generator read non-existent
    equilibration_check.json / rg_summary.json etc. instead of equilibration_comprehensive.json.
  * results.tg.value_K was null when tg_summary.json only exists in a per-rate subdir
    (tg_r<rate>/) and not at the top level (no rglob fallback).
"""
import json
import subprocess
import sys
from pathlib import Path

SCRIPT = (Path(__file__).resolve().parent.parent
          / "analysis_scripts" / "generate_run_summary.py")


def _write_fixtures(d: Path):
    """Write the minimal analysis JSONs a single-rate-primary rubbery run produces."""
    (d / "equilibration_comprehensive.json").write_text(json.dumps({
        "overall_pass": True,
        "thermo": {
            "equilibrated": True,
            "density_drift": {"pass": True, "drift_pct": 0.3844},
            "energy_drift": {"pass": True, "drift_pct": 0.69},
        },
        "chain": {
            "rg": {"pass": True, "cv": 0.2161, "mean_Rg_A": 19.82},
            "msd": {"kinetic_trap_flag": True, "diffusion_regime": "sub-diffusive"},
        },
        "spatial": {
            "p2": {"pass": True, "p2_mean": 0.0},
            "density_homogeneity": {"pass": True, "cv_mean": 0.2198},
        },
    }))
    # Tg sweep output lands in a per-rate subdir; top-level tg_summary.json is absent.
    (d / "tg_r40").mkdir()
    (d / "tg_r40" / "tg_summary.json").write_text(json.dumps(
        {"Tg_K": 207.39, "fit_quality": "EXCELLENT", "r_squared": 0.9998}))
    (d / "equilibrated_density.json").write_text(json.dumps(
        {"plateau_density_mean": 1.057698}))
    (d / "bulk_modulus.json").write_text(json.dumps(
        {"bulk_modulus_GPa": 3.14, "bulk_modulus_sem_GPa": 0.11}))


def test_run_summary_populates_from_comprehensive_and_subdir_tg(tmp_path):
    _write_fixtures(tmp_path)
    res = subprocess.run(
        [sys.executable, str(SCRIPT),
         "--output_dir", str(tmp_path), "--run_name", "TEST",
         "--smiles", "*CCO*", "--polymer_class", "POXI", "--ff", "pcff",
         "--charge_method", "AM1-BCC", "--dp", "100", "--n_chains", "10", "--n_atoms", "7020",
         "--d01", "PCFF", "--d05", "PASS", "--d06", "EXCELLENT"],
        capture_output=True, text=True,
    )
    assert res.returncode == 0, res.stderr
    summary = json.loads((tmp_path / "run_summary.json").read_text())

    # run metadata threaded through
    assert summary["run"]["dp"] == 100
    assert summary["run"]["n_atoms"] == 7020
    assert summary["run"]["charge_method"] == "AM1-BCC"

    # convergence + structural read from equilibration_comprehensive.json (the real schema)
    conv = summary["convergence"]
    assert conv["density_equilibrated"] is True
    assert conv["density_drift_pct"] == 0.3844
    sc = summary["structural_checks"]
    assert sc["rg_cv"] == 0.2161
    assert sc["kinetic_trap_flag"] is True
    assert sc["p2_mean"] == 0.0
    assert sc["density_cv_mean"] == 0.2198
    assert sc["heterogeneous_flag"] is False

    # per-rate subdir fallback: headline value_K, no experimental comparison
    tg = summary["results"]["tg"]
    assert abs(tg["value_K"] - 207.39) < 1e-6
    assert "status" not in tg and "exp_range_K" not in tg
    assert tg["fit_quality"] == "EXCELLENT"
    assert abs(tg["r_squared"] - 0.9998) < 1e-6
