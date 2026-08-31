"""Integration test for generate_run_summary.py.

Locks in the fix where run_summary.json came out under-populated (PEG1):
  * convergence + structural_checks were null because the generator read non-existent
    equilibration_check.json / rg_summary.json etc. instead of equilibration.json (the merged
    file check_equilibration_comprehensive/extract_equilibrated_density/enforce_equilibration_
    gate all read-merge-write into, under top-level thermo/chain/spatial + density + gate keys).
  * results.tg.value_K was null when thermal.json only exists in a per-rate subdir
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
    (d / "equilibration.json").write_text(json.dumps({
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
        "density": {"plateau_density_mean": 1.057698},
    }))
    # Tg sweep output lands in a per-rate subdir; top-level thermal.json is absent.
    (d / "tg_r40").mkdir()
    (d / "tg_r40" / "thermal.json").write_text(json.dumps(
        {"Tg_K": 207.39, "fit_quality": "EXCELLENT", "r_squared": 0.9998}))


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

    # convergence + structural read from equilibration.json (the merged schema)
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


def test_cross_attempt_directory_artifacts_missing_without_explicit_paths(tmp_path):
    """PEG1 (2026-08-27): equilibration.json/mechanical.json/bulk_modulus_deform.json live under
    THEIR OWN stage's attempt raw dir (data/<run>/attempts/<stage>/attempt-N/raw/), never under
    the summary attempt's own --output_dir. Without an explicit --*_path, the plain same-dir
    lookup (and its bounded rglob, which only searches inside --output_dir) can never find a
    sibling attempt directory's file -- this locks in that gap being correctly REPORTED, not
    silently guessed at, so a caller that forgets to pass the explicit paths gets a visible
    artifacts_missing entry rather than a run_summary.json that quietly claims null density/K."""
    summary_raw = tmp_path / "summary_attempt" / "raw"
    summary_raw.mkdir(parents=True)
    equil_raw = tmp_path / "equilibration_attempt" / "raw"
    equil_raw.mkdir(parents=True)
    (equil_raw / "equilibration.json").write_text(json.dumps({"density": {"plateau_density_mean": 1.0554}}))

    res = subprocess.run(
        [sys.executable, str(SCRIPT),
         "--output_dir", str(summary_raw), "--run_name", "TEST",
         "--d01", "pcff", "--d05", "PASS", "--d06", "EXCELLENT"],
        capture_output=True, text=True,
    )
    assert res.returncode == 0, res.stderr
    summary = json.loads((summary_raw / "run_summary.json").read_text())

    assert summary["results"]["density"]["value_g_cm3"] is None
    missing_files = {m["file"] for m in summary["artifacts_missing"]}
    assert "equilibration.json" in missing_files
    assert "mechanical.json" in missing_files


def test_cross_attempt_directory_artifacts_load_with_explicit_paths(tmp_path):
    """The fix: do_summary now threads each stage's own attempt raw dir path through explicitly
    (equilibration_json_path/mechanical_json_path, surfaced by do_equil_and_check/do_mechanical),
    mirroring --tg_path's existing precedent -- same directory layout as the test above, but with
    --equilibration_path/--mechanical_path pointing at the real cross-attempt locations."""
    summary_raw = tmp_path / "summary_attempt" / "raw"
    summary_raw.mkdir(parents=True)
    equil_raw = tmp_path / "equilibration_attempt" / "raw"
    equil_raw.mkdir(parents=True)
    mech_raw = tmp_path / "mechanical_attempt" / "raw"
    mech_raw.mkdir(parents=True)
    (equil_raw / "equilibration.json").write_text(json.dumps({"density": {"plateau_density_mean": 1.0554}}))
    (mech_raw / "mechanical.json").write_text(json.dumps({"B0_GPa": 3.3565, "B0_sem_GPa": 0.0983}))

    res = subprocess.run(
        [sys.executable, str(SCRIPT),
         "--output_dir", str(summary_raw), "--run_name", "TEST",
         "--d01", "pcff", "--d05", "PASS", "--d06", "EXCELLENT",
         "--equilibration_path", str(equil_raw / "equilibration.json"),
         "--mechanical_path", str(mech_raw / "mechanical.json")],
        capture_output=True, text=True,
    )
    assert res.returncode == 0, res.stderr
    summary = json.loads((summary_raw / "run_summary.json").read_text())

    assert summary["results"]["density"]["value_g_cm3"] == 1.0554
    assert summary["results"]["bulk_modulus"]["value_GPa"] == 3.3565
    missing_files = {m["file"] for m in summary["artifacts_missing"]}
    assert "equilibration.json" not in missing_files
    assert "mechanical.json" not in missing_files


def test_cross_attempt_explicit_path_given_but_stale_is_reported(tmp_path):
    """An explicit path that no longer resolves (e.g. a stale/renamed attempt directory) must
    still surface in artifacts_missing with a clear note, not silently fall back to the (wrong)
    same-dir lookup and mask the real problem."""
    summary_raw = tmp_path / "summary_attempt" / "raw"
    summary_raw.mkdir(parents=True)
    stale_path = tmp_path / "equilibration_attempt" / "raw" / "equilibration.json"

    res = subprocess.run(
        [sys.executable, str(SCRIPT),
         "--output_dir", str(summary_raw), "--run_name", "TEST",
         "--d01", "pcff", "--d05", "PASS", "--d06", "EXCELLENT",
         "--equilibration_path", str(stale_path)],
        capture_output=True, text=True,
    )
    assert res.returncode == 0, res.stderr
    summary = json.loads((summary_raw / "run_summary.json").read_text())

    missing = {m["file"]: m for m in summary["artifacts_missing"]}
    assert "equilibration.json" in missing
    assert "equilibration_path given but not found" in missing["equilibration.json"]["note"]


def _write_equilibration_with_regime(d: Path, regime, kinetic_trap_flag=None, ct_decay=None,
                                      tau_relax_ps=None, trajectory_ps=None,
                                      msid_large_s_slope=None, msid_slope=None):
    chain = {}
    if kinetic_trap_flag is not None:
        chain["msd"] = {"kinetic_trap_flag": kinetic_trap_flag, "diffusion_regime": "sub-diffusive"}
    if ct_decay is not None:
        chain["ct"] = {"decay_fraction_at_end": ct_decay, "tau_relax_ps": tau_relax_ps,
                        "trajectory_ps": trajectory_ps}
    if msid_large_s_slope is not None:
        chain["msid"] = {
            "slope": msid_slope,
            "large_s": {"slope": msid_large_s_slope, "s_range": [26, 75],
                        "gaussian_pass": abs(msid_large_s_slope - 1.0) <= 0.20},
        }
    (d / "equilibration.json").write_text(json.dumps({
        "overall_pass": True,
        "gate": {"regime": regime},
        "chain": chain,
    }))


def test_kinetic_trap_and_ct_caveats_surface_for_rubbery_run(tmp_path):
    """PEG1 (2026-08-27): convergence.verdict=PASS hid a kinetically trapped, barely-relaxed
    chain-conformation structure -- density/Tg/K were measured on it without any visible flag
    unless a reader separately dug into structural_checks. Locks in that a rubbery run's own
    kinetic_trap_flag/C(t) decay now surface as convergence.caveats, right next to verdict."""
    _write_equilibration_with_regime(tmp_path, regime="rubbery", kinetic_trap_flag=True,
                                      ct_decay=0.021, tau_relax_ps=6179405.0, trajectory_ps=3951.0)
    res = subprocess.run(
        [sys.executable, str(SCRIPT),
         "--output_dir", str(tmp_path), "--run_name", "TEST",
         "--d01", "pcff", "--d05", "PASS", "--d06", "EXCELLENT"],
        capture_output=True, text=True,
    )
    assert res.returncode == 0, res.stderr
    summary = json.loads((tmp_path / "run_summary.json").read_text())

    caveats = summary["convergence"]["caveats"]
    assert any("kinetic_trap_flag=True" in c for c in caveats)
    assert any("C(t) only 2% decayed" in c for c in caveats)


def test_kinetic_trap_caveat_suppressed_for_glassy_run(tmp_path):
    """Below Tg, limited chain diffusion is EXPECTED (chains are arrested by design), not a red
    flag -- PEG1's own equilibration.json warning text says exactly this: "expected below Tg,
    problematic in melt state." A glassy run's kinetic_trap_flag=True must NOT surface as a
    caveat, or every legitimate glassy run would carry a spurious warning."""
    _write_equilibration_with_regime(tmp_path, regime="glassy", kinetic_trap_flag=True,
                                      ct_decay=0.01, tau_relax_ps=1e9, trajectory_ps=4000.0)
    res = subprocess.run(
        [sys.executable, str(SCRIPT),
         "--output_dir", str(tmp_path), "--run_name", "TEST",
         "--d01", "pcff", "--d05", "PASS", "--d06", "EXCELLENT"],
        capture_output=True, text=True,
    )
    assert res.returncode == 0, res.stderr
    summary = json.loads((tmp_path / "run_summary.json").read_text())

    assert summary["convergence"]["caveats"] == []


def test_no_caveats_for_well_relaxed_rubbery_run(tmp_path):
    """A genuinely well-relaxed rubbery run (kinetic_trap_flag False, C(t) mostly decayed) must
    not carry any spurious caveat -- the field should stay empty, not just non-crashing."""
    _write_equilibration_with_regime(tmp_path, regime="rubbery", kinetic_trap_flag=False,
                                      ct_decay=0.85, tau_relax_ps=500.0, trajectory_ps=4000.0)
    res = subprocess.run(
        [sys.executable, str(SCRIPT),
         "--output_dir", str(tmp_path), "--run_name", "TEST",
         "--d01", "pcff", "--d05", "PASS", "--d06", "EXCELLENT"],
        capture_output=True, text=True,
    )
    assert res.returncode == 0, res.stderr
    summary = json.loads((tmp_path / "run_summary.json").read_text())

    assert summary["convergence"]["caveats"] == []


def test_global_chain_configuration_not_relaxed_fires_for_rubbery_run(tmp_path):
    """PEG1 (2026-08-27): equilibration.json's chain.msid.large_s already computes exactly this
    signal (slope=0.753, gaussian_pass=False) but it was never surfaced anywhere -- the finding
    code GLOBAL_CHAIN_CONFIGURATION_NOT_RELAXED existed only in comments/test docstrings, citing
    Auhl et al. cond-mat/0306026, with no actual wiring. Locks in that it now reaches
    convergence.caveats."""
    _write_equilibration_with_regime(tmp_path, regime="rubbery", msid_slope=1.213,
                                      msid_large_s_slope=0.753)
    res = subprocess.run(
        [sys.executable, str(SCRIPT),
         "--output_dir", str(tmp_path), "--run_name", "TEST",
         "--d01", "pcff", "--d05", "PASS", "--d06", "EXCELLENT"],
        capture_output=True, text=True,
    )
    assert res.returncode == 0, res.stderr
    summary = json.loads((tmp_path / "run_summary.json").read_text())

    caveats = summary["convergence"]["caveats"]
    assert any("GLOBAL_CHAIN_CONFIGURATION_NOT_RELAXED" in c and "slope=0.753" in c for c in caveats)
    assert summary["structural_checks"]["msid_slope"] == 1.213
    assert summary["structural_checks"]["msid_large_s_slope"] == 0.753
    assert summary["structural_checks"]["msid_large_s_gaussian_pass"] is False


def test_global_chain_configuration_not_relaxed_fires_for_glassy_run_too(tmp_path):
    """Unlike kinetic_trap_flag, this is NOT regime-gated: a glassy structure's conformation is
    whatever the melt phase produced before cooling froze it in -- cooling can never fix a
    long-wavelength defect either, so it matters just as much (arguably more) below Tg."""
    _write_equilibration_with_regime(tmp_path, regime="glassy", msid_slope=1.2,
                                      msid_large_s_slope=0.7)
    res = subprocess.run(
        [sys.executable, str(SCRIPT),
         "--output_dir", str(tmp_path), "--run_name", "TEST",
         "--d01", "pcff", "--d05", "PASS", "--d06", "EXCELLENT"],
        capture_output=True, text=True,
    )
    assert res.returncode == 0, res.stderr
    summary = json.loads((tmp_path / "run_summary.json").read_text())

    assert any("GLOBAL_CHAIN_CONFIGURATION_NOT_RELAXED" in c for c in summary["convergence"]["caveats"])


def test_global_chain_configuration_caveat_absent_when_large_s_is_gaussian(tmp_path):
    """A large-s slope within the +/-20% band must not spuriously fire."""
    _write_equilibration_with_regime(tmp_path, regime="rubbery", msid_slope=1.02,
                                      msid_large_s_slope=1.05)
    res = subprocess.run(
        [sys.executable, str(SCRIPT),
         "--output_dir", str(tmp_path), "--run_name", "TEST",
         "--d01", "pcff", "--d05", "PASS", "--d06", "EXCELLENT"],
        capture_output=True, text=True,
    )
    assert res.returncode == 0, res.stderr
    summary = json.loads((tmp_path / "run_summary.json").read_text())

    assert summary["convergence"]["caveats"] == []
