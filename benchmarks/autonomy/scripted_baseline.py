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

Arms (R1M7 item 4 — ordering target stock < curated < agent):
  --arm script  curated plan from polymer_rules.json (default; the scripted-curated arm)
  --arm stock   generic EMC defaults, polymer_rules NOT consulted (the floor; make_stock_plan)
  agent         a real PolyJarvis orchestrator run (the LLM arm) — NOT this driver

Usage:
  # wiring smoke (dry dispatch, no EMC/LAMMPS, tiny params):
  python benchmarks/autonomy/scripted_baseline.py --run SMOKE --polymer_class PHYC --smoke
  # curated arm, real run (requires EMC + LAMMPS + GPU):
  python benchmarks/autonomy/scripted_baseline.py --run PE_CURATED --arm script --polymer_class PHYC \
      --smiles "*CC*" --properties density --execute --gpu_ids 0 --mpi 8 --seed 1001
  # stock floor arm, real run:
  python benchmarks/autonomy/scripted_baseline.py --run PE_STOCK --arm stock --polymer_class PHYC \
      --smiles "*CC*" --properties density --execute --gpu_ids 0 --mpi 8 --seed 1001
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Pin system OpenMPI (/usr) BEFORE the lazy `from server import ...` in the dispatch helpers.
# The lammps-engine server resolves OpenMPI paths at import time; absent OPENMPI_PREFIX it can
# land on a stale /home/<user>/openmpi that does not exist, so the generated chain launcher
# exports a broken OPAL_PREFIX and mpirun fails with "unknown option -np" (PMMA_STOCK gate,
# 2026-06-27). setdefault honors a caller-supplied OPENMPI_PREFIX if one is already exported.
os.environ.setdefault("OPENMPI_PREFIX", "/usr")
os.environ.setdefault("OPENMPI_BIN", "/usr/bin")
os.environ.setdefault("OPENMPI_LIB", "/usr/lib/x86_64-linux-gnu")

REPO_ROOT = Path(__file__).resolve().parents[2]
# NOTE: insert order matters. Both server dirs contain a module named `server.py`; the LAST
# insert wins the bare name `server`. The --execute equil/build dispatch needs the
# *lammps-engine* server (generate_equilibration_workflow, run_lammps_chain, ...), so it must
# be inserted LAST. `build_cell` comes from the uniquely-named smiles_to_emc, so the emc dir's
# position is irrelevant. (Run --execute under mcp-servers/.venv, which has both deps.)
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "mcp-servers" / "mcp-emc-server"))
sys.path.insert(0, str(REPO_ROOT / "mcp-servers" / "mcp-lammps-engine"))

from error_classifier import classify_error  # noqa: E402
from metrics import RecoveryEvent, RunMetrics  # noqa: E402

# Deterministic plan (no LLM). Importable per exploration.
from make_deterministic_plan import make_plan  # noqa: E402

FOUNDATION_STAGES = {"build", "equil", "equil-check"}

# --- stock-defaults floor arm (R1M7 item 4) -------------------------------------
# The lower bound a non-expert user hits running EMC WITHOUT polymer_rules curation.
#
# Fairness note (important): the FF *family* is NOT polymer_rules curation — EMC owns its
# own class->field routing (mcp-emc-server/server.py:_select_field; its docstring says "the
# field is selected automatically from polymer_class — do not override it"). So a genuine
# no-curation "stock EMC" run of PE still gets trappe-ua for free. Forcing one FF on every
# class would be a strawman. What polymer_rules actually ADDS on top of stock EMC is the
# tuned NUMERICS — density_initial, DP/nchain, melt/equil temperature, charge_method,
# cooling rates. The floor therefore uses EMC's own FF routing but generic numerics; that
# numeric gap vs the curated arm is the honest measurement.
# Ordering target: stock-defaults (floor) < scripted-curated (polymer_rules) < agent (LLM).
STOCK_DEFAULTS = {
    "density_initial_gcm3": 0.9,   # EMC build_cell's own default (curated tunes per class, e.g. PHYC 0.65)
    "dp_typical": 20,              # generic chain length
    "nchain": 10,                  # generic chain count
    "T_workflow_K": 300.0,         # generic production T
    "annealing_T_high_K": 600.0,   # generic melt T (curated tunes per class, e.g. PHYC 620)
}

# Mirror of mcp-emc-server/server.py:_select_field — the FF family EMC auto-picks from the
# class (this is EMC's routing, not curation). Kept as a small literal to avoid importing the
# EMC FastMCP module (its name 'server' collides with the lammps-engine 'server' already on
# sys.path). Only the family matters here; PCFF is the fallback, matching _select_field.
_EMC_OPLS_CLASSES = {"PHAL", "PSIL"}
_EMC_TRAPPE_CLASSES = {"PHYC", "PDIE"}


def _emc_auto_field(polymer_class: str) -> str:
    pc = polymer_class.upper()
    if pc in _EMC_OPLS_CLASSES:
        return "opls/2024/opls-aa"
    if pc in _EMC_TRAPPE_CLASSES:
        return "trappe-ua"
    return "pcff"


def make_stock_plan(run_name, polymer_class, smiles, properties):
    """Floor-arm plan: EMC's own FF routing + generic numerics; polymer_rules.json NOT consulted.

    Same schema as make_deterministic_plan.make_plan so the dispatch/loop are arm-agnostic.
    decided_params carry EMC's auto-selected FF (fair — not curation) plus STOCK_DEFAULTS
    numerics, and no per-class tuned decisions are recorded."""
    decided = {"preferred_ff": _emc_auto_field(polymer_class), **STOCK_DEFAULTS}
    foundation = [
        {"stage": "build",       "track": "foundation",
         "success_criteria": {"data_file_written": True}},
        {"stage": "equil",       "track": "foundation",
         "success_criteria": {"check_equilibration_comprehensive.overall_pass": True}},
        {"stage": "equil-check", "track": "foundation",
         "success_criteria": {"equil_verdict": "PASS"}},
        {"stage": "run-summary", "track": "summary", "success_criteria": {}},
    ]
    return {
        "schema_version": "1.0",
        "goal": f"[STOCK floor] Predict {', '.join(sorted(properties))} for {polymer_class.upper()}",
        "run_name": run_name,
        "polymer_class": polymer_class.upper(),
        "smiles": smiles,
        "properties": sorted(properties),
        "confidence": "none",
        "plan_mode": "stock_defaults",
        "assumptions": ["EMC auto-selects the FF family; polymer_rules numeric curation NOT consulted"],
        "uncertainties": [],
        "decided_params": decided,
        "decisions": [],
        "planned_stages": foundation,
        "critique": {"status": "n/a", "rounds": 0, "findings": ["floor arm — no curation"]},
        "provenance": {"generator": "scripted_baseline.make_stock_plan",
                       "generated_at": datetime.now(timezone.utc).isoformat()},
    }


def _ctx_from_plan(run_name, polymer_class, smiles, properties, work_dir, seed, arm):
    if arm == "stock":
        plan = make_stock_plan(run_name, polymer_class, smiles, properties)
    else:  # "script" = curated polymer_rules plan
        plan = make_plan(run_name, polymer_class, smiles, properties)
    dp = plan["decided_params"]
    return {
        "plan": plan,
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
    density = dp.get("density_initial_gcm3", 0.9)  # EMC build_cell default if plan omits it
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
        # EMC (PCFF/Class II, OPLS) writes force-field coeffs to a sibling .params file, NOT
        # inline in the .data. generate_equilibration_workflow's pre-flight validation FAILS
        # ("'Pair Coeffs' section missing …") unless that params_file is threaded through —
        # which silently returned a status=error dict and tripped a KeyError('stages') in
        # _dispatch_equil (PMMA_STOCK gate, 2026-06-27). Capture it here.
        params_path = Path(str(data_path)).with_suffix(".params")
        if params_path.exists():
            ctx["params_path"] = str(params_path)
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
            params_file=ctx.get("params_path"),
            npt_prod_steps=2000 if smoke else None,
            velocity_seed=ctx["seed"],
        )
        if wf.get("status") == "error":
            detail = wf.get("validation_errors") or wf.get("error")
            return False, str(detail), f"equil workflow gen failed: {wf.get('error')}"
        # run_lammps_chain re-runs its OWN pre-flight validation on data_path and only
        # suppresses the "Coeffs section missing" errors when params_file is given — so the
        # EMC .params must be threaded here too, else it returns a status=error dict with no
        # chain_id (PMMA_STOCK gate, 2026-06-27).
        sub = run_lammps_chain(stages=wf["stages"], gpu_ids=gpu_ids, mpi=mpi,
                               data_file=data_path, params_file=ctx.get("params_path", ""),
                               engine="gpu")
        if sub.get("status") == "error":
            return False, str(sub.get("error")), f"chain submit failed: {sub.get('error')}"
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
        # Use the workflow's own production dir. For the GLASSY 9-run path (curated arm,
        # temp>300) this points to npt_prod300 — the 300 K density cell — NOT npt_production
        # (the 550/600 K melt). Hardcoding npt_production would feed equil-check the MELT
        # density for the curated arm and the 300 K density for stock, an apples-to-oranges
        # comparison that would invert the accuracy result. For the rubbery 7-run path
        # (stock arm, temp=300) it correctly points to npt_production.
        prod_dir = wf.get("npt_production_dir") or f"{ctx['work_dir']}/equil/npt_production"
        ctx["npt_prod_data"] = str(Path(prod_dir) / f"{Path(prod_dir).name}_out.data")
        # npt_production_log already points to the 300 K stage for BOTH regimes (npt_prod300
        # for glassy, npt_production for rubbery) — the right log for the density read.
        ctx["npt_prod_log"] = wf.get("npt_production_log") or str(
            Path(prod_dir) / f"{Path(prod_dir).name}.log")
        return True, "", f"equil completed: {chain_id}"
    except Exception as e:
        return False, str(e), f"equil raised: {e!r}"


def _dispatch_equil_check(ctx, execute, smoke):
    """Density gate. The foundation ablation's signal is the 300 K density, so this stage
    extracts the equilibrated-plateau density from the production log (the 300 K stage for
    BOTH arms — stock npt_production@300, curated npt_prod300@300) and writes density.json.
    We parse the log directly — columns located by header NAME, robust to column order — rather
    than calling check_equilibration_comprehensive.py, which requires --log_file/--dump_file/
    --backbone_types and emits non-binding verdicts irrelevant to a density read (the missing
    args silently failed the original gate; PMMA_STOCK, 2026-06-27)."""
    if not execute:
        return True, "", "DRY density extraction from production log"
    import json
    import statistics as stx
    log = ctx.get("npt_prod_log")
    if not log or not Path(log).exists():
        return False, f"production log missing: {log}", "equil-check missing input"
    target_T = ctx.get("density_target_T", 300.0)
    cols, rows = None, []
    for line in Path(log).read_text().splitlines():
        p = line.split()
        if not p:
            continue
        if p[0] == "Step":
            cols = {name: i for i, name in enumerate(p)}
            continue
        if cols and p[0].isdigit() and len(p) >= len(cols):
            try:
                rows.append((float(p[cols["Temp"]]), float(p[cols["Density"]])))
            except (KeyError, ValueError):
                pass
    if not rows:
        return False, "no thermo rows parsed", "equil-check parse failed"
    # Keep rows near the target T (drops any ramp tail), then average the last half (plateau).
    near = [d for T, d in rows if abs(T - target_T) <= 50.0] or [d for _, d in rows]
    window = near[len(near) // 2:]
    density = stx.mean(window)
    std = stx.pstdev(window) if len(window) > 1 else 0.0
    out = {"density_gcm3": round(density, 4), "density_std": round(std, 4),
           "n_points": len(window), "target_temp_K": target_T, "source_log": str(log)}
    (ctx["work_dir"] / "density.json").write_text(json.dumps(out, indent=2))
    ctx["density_gcm3"] = density
    return True, "", f"density={density:.4f} g/cm^3 (n={len(window)}, std={std:.4f})"


DISPATCH = {
    "build": _dispatch_build,
    "equil": _dispatch_equil,
    "equil-check": _dispatch_equil_check,
}


def run_scripted_baseline(run_name, polymer_class, smiles, properties, work_dir,
                          seed, gpu_ids, mpi, execute, smoke, arm="script"):
    ctx = _ctx_from_plan(run_name, polymer_class, smiles, properties, work_dir, seed, arm)
    m = RunMetrics(arm=arm, system=run_name, polymer_class=polymer_class,
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
    p.add_argument("--arm", choices=["script", "stock"], default="script",
                   help="script = curated polymer_rules plan (default); "
                        "stock = generic EMC-defaults floor (no curation). "
                        "The agent arm is a real orchestrator run, not this driver.")
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
        execute=args.execute, smoke=args.smoke, arm=args.arm)
    path = m.write()
    import json
    print(json.dumps(m.to_dict(), indent=2))
    print(f"\nmetrics -> {path}")


if __name__ == "__main__":
    main()
