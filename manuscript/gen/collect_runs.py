#!/usr/bin/env python3
"""Collect every round-2 number the manuscript intends to report into gen/out/runs.json.

Reads only raw run artifacts under data/ and the two frozen gate regrades. Every path is
resolved as data/<run>/attempts/<stage>/<accepted_attempt>/..., never the absolute paths stored
inside the JSON (half were written on the other host). Nothing is graded here beyond copying
verdicts; tables.py does the arithmetic.

Usage: python3 manuscript/gen/collect_runs.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from replicates import k_basis, reported_runs  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "data"
OUT = Path(__file__).resolve().parent / "out"
V1_DATA = Path.home() / "PolyJarvis" / "data"

SYSTEMS = ["PE", "PEG", "PLLA", "aPS", "sPVC", "PEEK", "PSU"]
REPLICATES = (1, 2, 3)
GPU_STAGES = ("equilibration", "cooling", "thermal", "mechanical")
REGRADES = [
    REPO / "benchmarks/stereo_r2/regrade/regrade_20260913.json",
    REPO / "benchmarks/rev2_replicates/regrade/regrade_20260914.json",
]
TG_LEGS = {
    "TGS_PE_1_L1_r20": ("PE_1", "rate"),
    "TGS_PE_1_L2_r10": ("PE_1", "rate"),
    "TGS_PE_1_L4_dT10": ("PE_1", "t_grid"),
    "TGS_PE_1_L5_dT40": ("PE_1", "t_grid"),
    "TGS_PLLA_1_L3_r50": ("PLLA_1", "rate"),
    "TGS_PLLA_1_L6_dT40": ("PLLA_1", "t_grid"),
}
# Reference values transcribed into main.tex Table 2 (polymer_rules.json + stereo_r2 MANIFEST
# overrides). The alternates are the values some runs carried in their own parameters.
REFERENCES = {
    "PE": {"tg_K": 195, "density": 0.855, "K_band": [1.5, 2.0]},
    "PEG": {"tg_K": 206, "density": 1.12, "K_band": [2.0, 4.0]},
    "PLLA": {"tg_K": 331, "density": 1.248, "K_band": [3.0, 4.5], "K_graded": False},
    # aPS density: Mark 2007 Table 7.2 glass equation at 300 K (was 1.05).
    "aPS": {"tg_K": 373, "density": 1.043, "K_band": [3.3, 4.0]},
    "sPVC": {"tg_K": 371, "tg_K_alt": 354, "density": 1.391, "K_band": [3.5, 4.5]},
    # PEEK K: the 4.0-5.8 band had no experimental source (Chen 2025 DAC: K0 = 2.5 +/- 0.5 GPa); ungraded.
    "PEEK": {"tg_K": 418, "density": 1.263, "K_band": [4.0, 5.8], "K_graded": False},
    # PSU Tg: measured Udel 459-460 K (PH4, PDH, Zoller 1978); 463 had no source row.
    "PSU": {"tg_K": 459, "density": 1.235, "density_alt": 1.24, "K_band": [4.0, 5.5]},
}


def load(path: Path):
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def hours(a: dict) -> float | None:
    try:
        t0 = datetime.fromisoformat(a["started_at"])
        t1 = datetime.fromisoformat(a["finished_at"])
    except (KeyError, TypeError, ValueError):
        return None
    return (t1 - t0).total_seconds() / 3600


def deck_velocity_seed(att: Path | None) -> int | None:
    """Seed of the first `velocity all create T SEED` line in the accepted equilibration decks."""
    if att is None:
        return None
    for deck in sorted((att / "work").rglob("*.in")):
        for line in deck.read_text(errors="replace").splitlines():
            parts = line.split()
            if parts[:3] == ["velocity", "all", "create"] and len(parts) > 4:
                try:
                    return int(parts[4])
                except ValueError:
                    continue
    return None


def attempt_dir(run_dir: Path, ws: dict, stage: str) -> Path | None:
    acc = ws["stages"].get(stage, {}).get("accepted_attempt")
    return run_dir / "attempts" / stage / acc if acc else None


def regrade_index() -> dict:
    idx = {}
    for f in REGRADES:
        for run, rec in (load(f) or {}).get("runs", {}).items():
            idx[run] = {"file": str(f.relative_to(REPO)), **rec}
    return idx


def gate(rec: dict | None, stage: str) -> dict:
    s = ((rec or {}).get("stages") or {}).get(stage) or {}
    old, new = s.get("old_version") or {}, s.get("new_version") or {}
    return {
        "live": s.get("stored_live_verdict"),
        "old": old.get("verdict"),
        "old_failing": old.get("failing_binding_gates"),
        "new": new.get("verdict"),
        "new_failing": new.get("failing_binding_gates"),
    }


def host_of(run_dir: Path) -> str:
    text = (run_dir / "workflow_state.json").read_text()
    return "A800" if "/home/alexzhao/" in text else "RTX6000"


REEXTRACT = OUT / "tg_reextract"


def thermal_record(run: str, att: Path | None) -> tuple[dict, str]:
    """Tg fit from gen/tg_reextract.py (current extract_thermal.py) when present, else stored."""
    current = load(REEXTRACT / run / "thermal.json")
    if current:
        return current, "reextract_current_code"
    return (load(att / "raw" / "thermal.json") if att else None) or {}, "stored"


def all_points_sem(d: Path, ws: dict, mech: dict) -> float | None:
    """Murnaghan B0 standard error on every simulated point (the fit script records it only for
    its selected window). Same extractor and fit as production."""
    try:
        import numpy as np
        sys.path.insert(0, str(REPO / "mcp-servers" / "mcp-lammps-engine" / "analysis_scripts"))
        from extract_bulk_modulus_murnaghan import extract_mean_volume, fit_murnaghan
    except ImportError:
        return None
    import re
    eqf = mech.get("eq_fraction", 0.5)
    pts = []
    for lf in mech.get("log_files") or []:
        p = float(re.search(r"bm_P(-?\d+(?:\.\d+)?)\.log$", lf).group(1))
        pts.append((p, extract_mean_volume(str(DATA / lf.split("/data/", 1)[1]), eqf)[0]))
    pts.sort()
    popt, pcov, _, ok = fit_murnaghan([v for _, v in pts], [p * 1.01325e-4 for p, _ in pts])
    return round(float(np.sqrt(pcov[0][0])), 4) if ok and pcov is not None else None


def collect_run(run: str, regrades: dict, replicate: int | None = None) -> dict:
    d = DATA / run
    ws = load(d / "workflow_state.json")
    rec: dict = {"run": run, "system": run.split("_")[0], "replicate": replicate, "host": host_of(d)}
    es = {st: load(attempt_dir(d, ws, st) / "executor_state.json") for st in ws["stages"]}
    params = (es.get("summary") or {}).get("parameters", {})
    build = (es.get("build") or {}).get("outputs", {})
    rs = load(attempt_dir(d, ws, "summary") / "raw" / "run_summary.json") or {}
    th, tg_source = thermal_record(run, attempt_dir(d, ws, "thermal"))
    mech = load(attempt_dir(d, ws, "mechanical") / "raw" / "mechanical.json") or {}
    cool = load(attempt_dir(d, ws, "cooling") / "raw" / "cooling.json") or {}
    contraction = load(attempt_dir(d, ws, "cooling") / "raw" / "cooling_contraction.json")
    plan = load(d / "raw" / "run_plan.json") or {}
    ctrl = load(d / "raw" / "control_state.json") or {}

    rec["protocol"] = {
        "ff": params.get("preferred_ff"),
        "dp": rs.get("run", {}).get("dp"),
        "n_chains": rs.get("run", {}).get("n_chains"),
        "n_atoms": build.get("n_atoms"),
        "dt_fs": params.get("dt_fs"),
        "cutoff_A": params.get("cutoff_A"),
        "T_equil_K": params.get("T_equil_K"),
        "tg_rate_K_per_ns": params.get("tg_rate_K_per_ns"),
        "tg_t_step_K": params.get("tg_t_step_K"),
        "annealing_T_high_K": params.get("annealing_T_high_K"),
        "emc_seed": params.get("emc_seed") or build.get("emc_seed"),
        "velocity_seed": params.get("velocity_seed") or deck_velocity_seed(attempt_dir(d, ws, "equilibration")),
        "ladder_executed_atm": mech.get("pressures_atm"),
        "ladder_simulated_atm": (mech.get("all_points_fit") or {}).get("pressures_atm") or mech.get("pressures_atm"),
        "ladder_planned_atm": params.get("bm_pressures_atm"),
        "refs_in_params": {k: params.get(k) for k in (
            "experimental_tg_K", "experimental_density_gcm3", "exp_K_min_GPa", "exp_K_max_GPa")},
    }
    rec["planning"] = {
        "plan_mode": plan.get("plan_mode"),
        "confidence": plan.get("confidence"),
        "critic_ran": (d / "raw" / "literature_grounding.json").exists(),
        "classification_ran": (d / "raw" / "classification.json").exists(),
        "recovery_agent_calls": ctrl.get("recovery_agent_calls"),
    }
    rec["tg"] = {
        "Tg_K": th.get("Tg_K"),
        "uncertainty_K": th.get("tg_uncertainty_K"),
        "r_squared": th.get("r_squared"),
        "fit_quality": th.get("fit_quality"),
        "width_K": th.get("transition_width_c_K"),
        "method_gap_K": th.get("tg_method_gap_K"),
        "verdict": th.get("tg_gate_verdict"),
        "cause": th.get("tg_gate_cause"),
        "reportable": th.get("tg_reportable"),
        "is_glassy_at_300K": (es.get("thermal") or {}).get("outputs", {}).get("is_glassy"),
        "source": tg_source,
    }
    res = rs.get("results", {})
    rec["density"] = {
        "rho_300K": (res.get("density") or {}).get("value_g_cm3"),
        "rho_melt": (res.get("melt_density") or {}).get("value_g_cm3"),
        "T_melt_K": (res.get("melt_density") or {}).get("temperature_K"),
        "contraction": None if contraction is None else {
            k: contraction.get(k) for k in (
                "expected_contraction", "actual_contraction", "contraction_shortfall", "verdict")},
    }
    basis = k_basis(rec["system"])
    apf = mech.get("all_points_fit") or {}
    if basis == "all_points" and apf.get("B0_GPa") is not None:
        same_window = not mech.get("excluded_points")
        k_val, k_sem = apf.get("B0_GPa"), (mech.get("bulk_modulus_sem_GPa") if same_window
                                           else all_points_sem(d, ws, mech))
        k_bp, k_r2, k_n = apf.get("B0_prime"), apf.get("r_squared"), apf.get("n_points")
    else:
        basis = "production"
        k_val, k_sem = mech.get("bulk_modulus_GPa"), mech.get("bulk_modulus_sem_GPa")
        k_bp, k_r2, k_n = mech.get("B0_prime"), mech.get("r_squared"), mech.get("n_points")
    rec["K"] = {
        "basis": basis,
        "K_GPa": k_val,
        "sem_GPa": k_sem,
        "B0_prime": k_bp,
        "r_squared": k_r2,
        "n_points": k_n,
        "production_K_GPa": mech.get("bulk_modulus_GPa"),
        "production_n_points": mech.get("n_points"),
        "excluded_points": mech.get("excluded_points"),
        "fluctuation_K_GPa": mech.get("fluctuation_bulk_modulus_GPa"),
        "loo_max_dB0_pct": mech.get("loo_max_dB0_pct"),
        "gate_verdict": mech.get("bm_gate_verdict"),
        "convergence_verdict": mech.get("bm_convergence_verdict"),
    }
    th_, ch, sp = cool.get("thermo", {}), cool.get("chain", {}), cool.get("spatial", {})
    rec["structure_300K"] = {
        "Rg_A": (ch.get("rg") or {}).get("mean_Rg_A"),
        "Rg_cv": (ch.get("rg") or {}).get("cv"),
        "Ree_A": (ch.get("ree") or {}).get("mean_R_ee_A"),
        "msid_slope": (ch.get("msid") or {}).get("slope"),
        "msid_large_s_slope": ((ch.get("msid") or {}).get("large_s") or {}).get("slope"),
        "p2": (sp.get("p2") or {}).get("p2_mean"),
        "rho_cv": (sp.get("density_homogeneity") or {}).get("cv_mean"),
        "rho_cv_floor": (sp.get("density_homogeneity") or {}).get("poisson_cv"),
        "energy_drift_pct": (th_.get("energy_drift") or {}).get("drift_pct"),
        "density_drift_pct": (th_.get("density_drift") or {}).get("drift_pct"),
        "n_eff_density": (th_.get("n_eff_density") or {}).get("n_eff"),
    }
    rg = regrades.get(run)
    rec["gates"] = {"regrade_file": (rg or {}).get("file"),
                    "melt": gate(rg, "equilibration"), "cooling": gate(rg, "cooling")}
    rec["interventions"] = {
        "remedies": len(ws.get("remedy_history") or []),
        "agent_escalations": len(ws.get("agent_escalations") or []),
        "agent_actions": [(e.get("decision") or {}).get("action") for e in ws.get("agent_escalations") or []],
        "escalations_archived": sum(len(ws.get(k) or []) for k in ws if k.startswith("agent_escalations_") and isinstance(ws.get(k), list)),
        "operator_interventions": len(ws.get("operator_interventions") or []),
        "operator_acceptance": {st: True for st, v in ws["stages"].items() if v.get("operator_acceptance")},
    }
    cost = {"attempts": 0, "gpu_stage_h": 0.0, "all_stage_h": 0.0, "failed_or_superseded_gpu_h": 0.0}
    for st, v in ws["stages"].items():
        for a in v.get("attempts") or []:
            h = hours(a)
            if h is None:
                continue
            cost["attempts"] += 1
            cost["all_stage_h"] += h
            if st in GPU_STAGES:
                cost["gpu_stage_h"] += h
                if a.get("attempt_id") != v.get("accepted_attempt"):
                    cost["failed_or_superseded_gpu_h"] += h
    rec["cost"] = {k: round(x, 2) if isinstance(x, float) else x for k, x in cost.items()}
    return rec


def collect_leg(name: str) -> dict:
    d = DATA / "tg_sensitivity" / name
    ws = load(d / "workflow_state.json")
    anchor, axis = TG_LEGS[name]
    th_stage = ws["stages"]["thermal"]
    att = th_stage.get("accepted_attempt") or (th_stage.get("attempts") or [{}])[-1].get("attempt_id")
    th, tg_source = thermal_record(f"tg_sensitivity/{name}", d / "attempts" / "thermal" / att)
    p = (load(d / "attempts" / "thermal" / att / "executor_state.json") or {}).get("parameters", {})
    return {"leg": name, "anchor": anchor, "axis": axis, "stage_status": th_stage.get("status"),
            "tg_source": tg_source,
            "tg_rate_K_per_ns": p.get("tg_rate_K_per_ns"), "tg_t_step_K": p.get("tg_t_step_K"),
            "Tg_K": th.get("Tg_K"), "uncertainty_K": th.get("tg_uncertainty_K"),
            "r_squared": th.get("r_squared"), "fit_quality": th.get("fit_quality"),
            "verdict": th.get("tg_gate_verdict"), "cause": th.get("tg_gate_cause"),
            "method_gap_K": th.get("tg_method_gap_K"), "reportable": th.get("tg_reportable")}


def collect_peg_ff_arms() -> list[dict]:
    """Round-1 (v1 checkout) controlled force-field pair; values as recorded in each run_log.md."""
    arms = []
    for run, ff in (("PEGCMP1", "compass"), ("PEGORE1", "pcff_ore")):
        log = V1_DATA / run / "run_log.md"
        arms.append({"run": run, "ff": ff, "source": str(log), "exists": log.exists()})
    return arms


def main() -> None:
    regrades = regrade_index()
    runs = [collect_run(name, regrades, i) for _, i, name in reported_runs()]
    legs = [collect_leg(n) for n in TG_LEGS]
    out = {"generated_at": datetime.now().isoformat(timespec="seconds"),
           "references": REFERENCES, "runs": runs, "tg_legs": legs,
           "peg_ff_arms": collect_peg_ff_arms()}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "runs.json").write_text(json.dumps(out, indent=2) + "\n")
    print(f"wrote {OUT / 'runs.json'}: {len(runs)} runs, {len(legs)} legs")


if __name__ == "__main__":
    main()
