"""Integration test for generate_run_summary.py.

Locks in the fix where run_summary.json came out under-populated (PEG1):
  * convergence + structural_checks were null because the generator read non-existent
    equilibration_check.json / rg_summary.json etc. instead of equilibration_comprehensive.json.
  * results.tg.value_K was null for multi-rate runs (no fallback to the log-linear slow-rate Tg).
"""
import json
import subprocess
import sys
from pathlib import Path

SCRIPT = (Path(__file__).resolve().parent.parent
          / "analysis_scripts" / "generate_run_summary.py")


def _write_fixtures(d: Path):
    """Write the minimal analysis JSONs a multi-rate rubbery run produces."""
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
    (d / "tg_multirate_result.json").write_text(json.dumps({
        "tg_at_slow_rate_K": 207.39, "loglinear_slope_K": 5.45,
        "loglinear_r_squared": 0.9996, "vf_fit_quality": "POOR_POORLY_CONSTRAINED",
        "n_points": 3, "rates_span_decades": 1.2, "slow_rate_ref_K_per_ns": 5.0,
    }))
    (d / "tg_r40").mkdir()
    (d / "tg_r40" / "tg_summary.json").write_text(json.dumps(
        {"fit_quality": "EXCELLENT", "r_squared": 0.9998}))
    (d / "equilibrated_density.json").write_text(json.dumps(
        {"plateau_density_mean": 1.057698}))
    (d / "bulk_modulus.json").write_text(json.dumps(
        {"bulk_modulus_GPa": 3.14, "bulk_modulus_sem_GPa": 0.11}))


def test_run_summary_populates_from_comprehensive_and_multirate(tmp_path):
    _write_fixtures(tmp_path)
    res = subprocess.run(
        [sys.executable, str(SCRIPT),
         "--output_dir", str(tmp_path), "--run_name", "TEST",
         "--smiles", "*CCO*", "--polymer_class", "POXI", "--ff", "pcff",
         "--charge_method", "AM1-BCC", "--dp", "100", "--n_chains", "10", "--n_atoms", "7020",
         "--d01", "PCFF", "--d05", "PASS", "--d06", "EXCELLENT",
         "--exp_tg_min", "186", "--exp_tg_max", "226"],
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

    # multi-rate Tg fallback: headline value_K + status/error vs exp range
    tg = summary["results"]["tg"]
    assert abs(tg["value_K"] - 207.39) < 1e-6
    assert tg["status"] == "PASS"
    assert tg["error_pct"] is not None and tg["error_pct"] < 2.0
    assert tg["fit_quality"] == "EXCELLENT"
    assert abs(tg["r_squared"] - 0.9996) < 1e-6


# ─── Tg interval grading ─────────────────────────────────────────────────────
#
# The point Tg was graded alone, so a value 2 K outside its band with a 15 K fit
# uncertainty read as a clean FAIL. The interval now gets its own status rather
# than widening the band -- _floor_band already widened it once, and widening
# both sides then testing containment would compound into a laundered PASS.


def _single_rate(d, tg_K, half_width_K):
    """A raw single-rate run: tg_summary.json only, no multirate artifact."""
    (d / "equilibration_comprehensive.json").write_text(json.dumps({
        "overall_pass": True, "thermo": {"equilibrated": True},
        "chain": {}, "spatial": {},
    }))
    (d / "tg_summary.json").write_text(json.dumps({
        "Tg_K": tg_K, "r_squared": 0.998, "fit_quality": "GOOD",
        "fit_method": "bilinear_curvefit",
        "tg_interval_half_width_K": half_width_K,
    }))
    (d / "equilibrated_density.json").write_text(json.dumps(
        {"plateau_density_mean": 1.05}))


def _run(d, exp_lo, exp_hi):
    res = subprocess.run(
        [sys.executable, str(SCRIPT), "--output_dir", str(d), "--run_name", "TEST",
         "--polymer_class", "PSTR", "--dp", "40",
         "--exp_tg_min", str(exp_lo), "--exp_tg_max", str(exp_hi)],
        capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    return json.loads((d / "run_summary.json").read_text())["results"]["tg"]


def test_point_inside_band_is_a_plain_pass(tmp_path):
    _single_rate(tmp_path, tg_K=380.0, half_width_K=12.0)
    tg = _run(tmp_path, 360, 400)
    assert tg["status"] == "PASS"
    assert tg["error_pct"] == 0.0


def test_point_outside_but_interval_overlapping_is_its_own_status(tmp_path):
    _single_rate(tmp_path, tg_K=412.0, half_width_K=15.0)     # band ends at 400
    tg = _run(tmp_path, 360, 400)
    assert tg["status"] == "PASS_WITHIN_UNCERTAINTY"
    # error_pct keeps the POINT distance -- zeroing it would drop the number that
    # makes the annotation readable.
    assert tg["error_pct"] == 3.0
    assert tg["tg_interval_half_width_K"] == 15.0


def test_interval_too_narrow_to_reach_the_band_still_fails(tmp_path):
    _single_rate(tmp_path, tg_K=412.0, half_width_K=3.0)
    tg = _run(tmp_path, 360, 400)
    assert tg["status"] == "FAIL"


def test_null_interval_is_not_treated_as_zero_or_as_infinite(tmp_path):
    """A missing half-width falls back to point grading, not to a free pass."""
    _single_rate(tmp_path, tg_K=412.0, half_width_K=None)
    tg = _run(tmp_path, 360, 400)
    assert tg["status"] == "FAIL"
    assert tg["tg_interval_half_width_K"] is None


def test_rate_extrapolated_tg_is_graded_as_a_point(tmp_path):
    """A log-linear extrapolation across rates carries no breakpoint sigma, so its
    interval must be null even when a per-rate tg_summary.json reports one."""
    _write_fixtures(tmp_path)
    (tmp_path / "tg_summary.json").write_text(json.dumps(
        {"Tg_K": 250.0, "tg_interval_half_width_K": 40.0}))
    tg = _run(tmp_path, 186, 226)
    assert tg["grading_basis"] == "rate_extrapolated"
    assert tg["tg_interval_half_width_K"] is None
