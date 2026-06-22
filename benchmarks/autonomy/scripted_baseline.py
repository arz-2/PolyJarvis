#!/usr/bin/env python3
"""
Scripted-baseline driver — the SCRIPT arm of the autonomy ablation (R1M1 / M7).

Holds the backend fixed (EMC builder + LAMMPS engine + polymer_rules.json) and
removes the LLM: it reads the *deterministic* plan (scripts/make_deterministic_plan.py,
no LLM), executes planned_stages in order via direct backend calls, and HALTS on the
first failure with NO recovery — that absence of LLM glue is the experimental control.

The AGENT arm uses the same deterministic plan for high-confidence classes, so on the
happy path the two arms make identical decisions (the honest concession, shown
empirically). They diverge only at failures / off-table chemistries, where the AGENT
recovers and this SCRIPT stalls.

Scope this pass: the foundation track (build -> equil -> equil-check) is fully wired —
that already yields density, where the PE +25% over-densification failure surfaces.
Property stages (tg / bulk_modulus) are recorded as not-yet-wired and belong to the
full launch.

Usage:
  # wiring smoke (dry dispatch, no EMC/LAMMPS, tiny params):
  python benchmarks/autonomy/scripted_baseline.py --run SMOKE --polymer_class PHYC --smoke
  # real run (requires EMC + LAMMPS + GPU):
  python benchmarks/autonomy/scripted_baseline.py --run PE_SCRIPT --polymer_class PHYC \
      --smiles "*CC*" --properties density --execute --gpu_ids 0 --mpi 8 --seed 1001
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "mcp-servers" / "mcp-lammps-engine"))
sys.path.insert(0, str(REPO_ROOT / "mcp-servers" / "mcp-emc-server"))

from error_classifier import classify_error  # noqa: E402
from metrics import RecoveryEvent, RunMetrics  # noqa: E402

# Deterministic plan (no LLM). Importable per exploration.
from make_deterministic_plan import make_plan  # noqa: E402
from hw_common import load_rules  # noqa: E402

FOUNDATION_STAGES = {"build", "equil", "equil-check"}


def _ctx_from_plan(run_name, polymer_class, smiles, properties, work_dir, seed):
    plan = make_plan(run_name, polymer_class, smiles, properties)
    rules = load_rules()
    cls = rules["classes"][polymer_class.upper()]
    dp = plan["decided_params"]
    return {
        "plan": plan,
        "cls": cls,
        "decided": dp,
        "work_dir": Path(work_dir),
        "seed": seed,
        "smiles": smiles,
        "polymer_class": polymer_class,
        "run_name": run_name,
    }


# --- per-stage dispatch: returns (ok: bool, log_tail: str, info: str) -----------

def _dispatch_build(ctx, execute, smoke):
    dp = ctx["decided"]
    field = dp.get("preferred_ff", "pcff")
    density = dp.get("density_initial_gcm3", 0.5)
    n_dp = 5 if smoke else dp.get("dp_typical", 20)
    nchains = 2 if smoke else dp.get("nchain", 10)
    out_dir = ctx["work_dir"] / "build"
    intent = (f"build_cell(smiles={ctx['smiles']!r}, field={field}, "
              f"density={density}, dp={n_dp}, nchains={nchains}, seed={ctx['seed']})")
    if not execute:
        return True, "", f"DRY {intent}"
    try:
        from smiles_to_emc import build_cell
        out_dir.mkdir(parents=True, exist_ok=True)
        data_path = build_cell(
            smiles=ctx["smiles"], output_dir=str(out_dir), output_name=ctx["run_name"],
            field=field, density=density, dp=n_dp, nchains=nchains,
            seed=ctx["seed"] if ctx["seed"] is not None else -1,
        )
        ctx["data_path"] = str(data_path)
        return True, "", f"built {data_path}"
    except Exception as e:  # build failure -> log tail for classifier
        return False, str(e), f"build raised: {e!r}"


def _dispatch_equil(ctx, execute, smoke, gpu_ids, mpi):
    if not execute:
        return True, "", "DRY generate_equilibration_workflow + run_lammps_chain + poll"
    try:
        from server import (generate_equilibration_workflow, run_lammps_chain,
                            get_run_status)
        dp = ctx["decided"]
        data_path = ctx.get("data_path")
        if not data_path:
            return False, "no data file from build stage", "equil missing input"
        ff = dp.get("preferred_ff", "pcff")
        wf = generate_equilibration_workflow(
            data_file=data_path, work_dir_base=str(ctx["work_dir"] / "equil"),
            polymer_name=ctx["run_name"],
            temp=dp.get("T_workflow_K", 300.0), max_temp=dp.get("annealing_T_high_K", 600.0),
            n_chains=dp.get("nchain", 10),
            use_pcff=("pcff" in ff), use_trappe=("trappe" in ff), use_opls=("opls" in ff),
            npt_prod_steps=2000 if smoke else None,
            velocity_seed=ctx["seed"],
        )
        sub = run_lammps_chain(stages=wf["stages"], gpu_ids=gpu_ids, mpi=mpi,
                               data_file=data_path, engine="gpu")
        chain_id = sub["chain_id"]
        ctx["equil_chain_id"] = chain_id
        while True:
            st = get_run_status(chain_id)
            if st["status"] in ("completed", "failed"):
                break
            time.sleep(10)
        if st["status"] == "failed":
            from server import get_run_output
            tail = get_run_output(chain_id).get("lammps_log_tail", "")
            return False, tail, f"equil chain failed at {st.get('failed_stages')}"
        ctx["npt_prod_data"] = f"{ctx['work_dir']}/equil/npt_production/npt_production_out.data"
        return True, "", f"equil completed: {chain_id}"
    except Exception as e:
        return False, str(e), f"equil raised: {e!r}"


def _dispatch_equil_check(ctx, execute, smoke):
    if not execute:
        return True, "", "DRY check_equilibration_comprehensive (density gate)"
    # Real path: subprocess to the analysis CLI (importable-as-CLI per exploration).
    import subprocess
    script = (REPO_ROOT / "mcp-servers" / "mcp-lammps-engine" /
              "analysis_scripts" / "check_equilibration_comprehensive.py")
    data = ctx.get("npt_prod_data")
    if not data or not Path(data).exists():
        return False, "npt_production_out.data missing", "equil-check missing input"
    try:
        out = subprocess.run([sys.executable, str(script), "--data_file", data],
                             capture_output=True, text=True, timeout=600)
        ok = out.returncode == 0
        return ok, out.stderr if not ok else "", out.stdout[-400:]
    except Exception as e:
        return False, str(e), f"equil-check raised: {e!r}"


DISPATCH = {
    "build": _dispatch_build,
    "equil": _dispatch_equil,
    "equil-check": _dispatch_equil_check,
}


def run_scripted_baseline(run_name, polymer_class, smiles, properties, work_dir,
                          seed, gpu_ids, mpi, execute, smoke):
    ctx = _ctx_from_plan(run_name, polymer_class, smiles, properties, work_dir, seed)
    m = RunMetrics(arm="script", system=run_name, polymer_class=polymer_class,
                   seed=seed, smoke=smoke).start()

    for stage in ctx["plan"]["planned_stages"]:
        name = stage["stage"]
        if name not in FOUNDATION_STAGES:
            m.notes += f"; stage '{name}' not wired this pass (foundation-only)"
            m.terminal_state = "completed_foundation"
            break
        fn = DISPATCH[name]
        if name == "equil":
            ok, log_tail, info = fn(ctx, execute, smoke, gpu_ids, mpi)
        else:
            ok, log_tail, info = fn(ctx, execute, smoke)
        if not ok:
            cls = classify_error(log_tail)
            # SCRIPT performs NO recovery — record the would-be recovery, unresolved.
            m.add_recovery(RecoveryEvent(
                fault=cls["error_class"], prescripted=cls["prescripted"],
                resolved=False, attempts=1,
                note=f"halted at {name}: {info[:120]}"))
            m.terminal_state = "stalled"
            m.stop()
            return m
        m.stages_completed.append(name)
    else:
        m.terminal_state = "completed"

    if not m.terminal_state or m.terminal_state == "unknown":
        m.terminal_state = "completed_foundation"
    m.stop()
    return m


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--run", dest="run_name", required=True)
    p.add_argument("--polymer_class", required=True)
    p.add_argument("--smiles", default="*CC*")
    p.add_argument("--properties", default="density",
                   help="comma list; foundation-only this pass (density)")
    p.add_argument("--work_dir", default=None)
    p.add_argument("--seed", type=int, default=1001)
    p.add_argument("--gpu_ids", default="0")
    p.add_argument("--mpi", type=int, default=8)
    p.add_argument("--execute", action="store_true",
                   help="actually call EMC/LAMMPS (default: dry dispatch)")
    p.add_argument("--smoke", action="store_true",
                   help="tiny params; dry unless --execute also given")
    args = p.parse_args()

    work_dir = args.work_dir or str(REPO_ROOT / "data" / args.run_name / "lammps")
    properties = {s.strip().lower() for s in args.properties.split(",") if s.strip()}

    m = run_scripted_baseline(
        run_name=args.run_name, polymer_class=args.polymer_class, smiles=args.smiles,
        properties=properties, work_dir=work_dir, seed=args.seed,
        gpu_ids=args.gpu_ids, mpi=args.mpi,
        execute=args.execute, smoke=args.smoke)
    path = m.write()
    import json
    print(json.dumps(m.to_dict(), indent=2))
    print(f"\nmetrics -> {path}")


if __name__ == "__main__":
    main()
