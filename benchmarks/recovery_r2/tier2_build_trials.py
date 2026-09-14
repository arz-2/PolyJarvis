#!/usr/bin/env python3
"""Tier 2 recovery trial for build-stage faults: real campaign executor, real EMC build,
real recovery agent, scored on COMPLETION.

Tier 1 (run_trials.py) drives the real WorkflowEngine with a scripted executor and a
`stop`-only stub agent, so it measures routing and caps but cannot measure completion and
contains no LLM. This script closes both gaps for the one fault class where the arms can
diverge at all: BUILD_CELL_INVALID is `agent_only`, so A1 (no agent) escalates by
construction and A2's outcome is whatever the real agent decides.

Injection without touching production code
-------------------------------------------
Every artifact is sha256'd into its attempt manifest AFTER the executor returns, and
_input_hash folds those hashes into every dependent. Corrupting an accepted cell in place
would therefore not be experienced as a fault -- the engine would call the stage stale and
rebuild. So the fault is injected INSIDE the build attempt: this driver wraps the LAMMPS
engine module's `inspect_data_file` (the exact validation call do_build makes) and corrupts
the attempt's own freshly built cell.data immediately before validating it. The manifest
then hashes the corrupted file and everything downstream is internally consistent -- the
fault is indistinguishable from a genuinely bad build, which is the point.

Fault persistence is part of the design, not a knob
---------------------------------------------------
BUILD_CELL_INVALID is agent_only because "rebuilding at the same decided_params reproduces
the same cell (the EMC seed is pinned), so a retry is guaranteed to fail identically"
(workflow_engine.py). That is true for a chemistry-determined defect and false for an I/O
one, so each fault carries the persistence its real-world counterpart has:

    net_charge      persistent  a charge-assignment defect recurs on every rebuild
    truncate_atoms  transient   a half-written file; a rebuild writes it whole
    collapse_box    transient   same shape: a truncated write

That gives the agent a genuine discrimination task: `retry` recovers a transient fault and
cannot recover a persistent one. A stub that always retried, or always stopped, would score
well on exactly one of the two.

Arms
----
    A1  recovery_agent=None           -- escalation is terminal
    A2  recovery_agent_cli.py (real)  -- autonomous, within MAX_AGENT_DECISIONS(_PER_STAGE)

The engine is restricted to the build stage (BuildOnlyEngine), and completion is scored on
build `accepted` PLUS an independent re-validation of the accepted cell with the un-hooked
validator -- so "recovered" can never mean "a corrupted cell got accepted".

    mcp-servers/.venv/bin/python benchmarks/recovery_r2/tier2_build_trials.py \
        --plan <plan.json> --arms A1 --faults truncate_atoms --trials 1    # smoke, no LLM
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO / "orchestration" / "scripts"))
sys.path.insert(0, str(HERE))

import injectors  # noqa: E402
import run_campaign as rc  # noqa: E402
from rules_common import get_class_entry, load_rules  # noqa: E402
from scientific_control import (JsonSubprocessAgent, SubprocessRecoveryAgent,  # noqa: E402
                                validate_overrides)
from stage_params import apply_plan, resolve_hardware  # noqa: E402
from validate_run_plan import validate_plan  # noqa: E402
from workflow_engine import WorkflowEngine  # noqa: E402

VENV_PY = REPO / "mcp-servers" / ".venv" / "bin" / "python"
WORKSPACE = REPO / "data" / "recovery_r2"

FAULTS = {
    "net_charge": ("persistent", injectors.inject_net_charge),
    "truncate_atoms": ("transient", injectors.inject_truncate_atoms),
    "collapse_box": ("transient", injectors.inject_collapse_box),
}


class BuildOnlyEngine(WorkflowEngine):
    """The real engine, restricted to the stage the fault fires on."""

    def enabled_stages(self):
        return ("build",)


def _policy_hashes() -> dict:
    out = {}
    for p in (REPO / "guides" / "polymer_rules.json", REPO / "guides" / "ff_moiety_rules.json",
              REPO / "orchestration" / "decision_policy.json"):
        if p.exists():
            out[str(p.relative_to(REPO))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def one_trial(base_plan: dict, fault: str, arm: str, n: int, lammps, emc, seed: int) -> dict:
    persistence, inject = FAULTS[fault]
    tag = base_plan["run_name"].replace("RECOV_", "")
    name = f"RECOV_{tag}_{fault}_{arm}_t{n}"
    run_dir = WORKSPACE / name
    if run_dir.exists():
        shutil.rmtree(run_dir)
    (run_dir / "raw").mkdir(parents=True)

    plan = json.loads(json.dumps(base_plan))
    plan["run_name"] = name
    plan.setdefault("decided_params", {})["emc_seed"] = seed   # identical cell in every trial
    plan_path = run_dir / "raw" / "run_plan.json"
    plan_path.write_text(json.dumps(plan, indent=2))

    rules = load_rules()
    pclass = plan["polymer_class"]
    args = rc._base_args(name, pclass, str(plan_path))
    cls = apply_plan(get_class_entry(rules, pclass, warn_on_miss=False), plan, args)
    resolve_hardware(args, cls, rules)
    args.properties = ",".join(sorted(plan.get("properties") or ()))

    original = lammps.inspect_data_file
    counter = {"validations": 0, "injected": 0}

    def hooked(*a, **kw):
        counter["validations"] += 1
        path = Path(kw["data_file"] if "data_file" in kw else a[0])
        if persistence == "persistent" or counter["validations"] == 1:
            path.write_text(inject(path.read_text()))
            counter["injected"] += 1
        return original(*a, **kw)

    agent = None
    if arm == "A2":
        agent = SubprocessRecoveryAgent(JsonSubprocessAgent(
            [str(VENV_PY), str(REPO / "orchestration" / "scripts" / "recovery_agent_cli.py")]))

    decision_policy = json.loads((REPO / "orchestration" / "decision_policy.json").read_text())
    executor = rc.CampaignStageExecutor(args, cls, emc, lammps, str(plan_path))
    t0 = time.time()
    lammps.inspect_data_file = hooked
    try:
        engine = BuildOnlyEngine(
            run_dir, plan, executor, recovery_agent=agent, policy_hashes=_policy_hashes(),
            plan_path=plan_path,
            plan_validator=lambda c: validate_plan(c, decision_policy),
            override_validator=validate_overrides)
        try:
            result = engine.run()
            status = result.get("status")
        except Exception as exc:  # noqa: BLE001 -- a harness crash is data, not a verdict
            status = f"raised:{type(exc).__name__}:{exc}"[:200]
    finally:
        lammps.inspect_data_file = original
    wall = time.time() - t0

    state = json.loads((run_dir / "workflow_state.json").read_text())
    build = state["stages"]["build"]
    escalations = list(state.get("agent_escalations") or [])

    # Completion, independently re-checked with the UN-hooked validator.
    independently_valid = None
    if build.get("status") == "accepted":
        acc = build["accepted_attempt"]
        cell = run_dir / "attempts" / "build" / acc / "work" / "cell" / "cell.data"
        params = cell.parent / "emc_build.params"
        dp = plan["decided_params"]
        info = original(data_file=str(cell), lj_cutoff=dp.get("cutoff_A") or 12.0,
                        target_density_gcm3=rc.COMPRESSION_RATIO * dp["density_initial_gcm3"],
                        nchain=dp["nchain"], params_file=str(params) if params.exists() else "")
        independently_valid = not (info.get("validation") or {}).get("errors")

    return {
        "at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "run": name, "fault": fault, "persistence": persistence, "arm": arm, "trial": n,
        "status": status,
        "build_status": build.get("status"),
        "build_attempts": len(build.get("attempts") or []),
        "validations": counter["validations"], "injected": counter["injected"],
        "agent_calls": len(escalations),
        "decisions": [{"action": (e.get("decision") or {}).get("action"),
                       "modifications": (e.get("decision") or {}).get("modifications"),
                       "rationale_head": ((e.get("decision") or {}).get("rationale") or "")[:600]}
                      for e in escalations],
        # Who closed a failed trial: the agent's end_run, the engine's spent budget, or
        # nothing (a harness crash / no-agent halt). Without it those read identically.
        "terminated_by": state.get("terminated_by"),
        "completed": build.get("status") == "accepted" and bool(independently_valid),
        "accepted_cell_independently_valid": independently_valid,
        "wall_s": round(wall, 1),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--plan", required=True, help="base run_plan.json (run_name RECOV_<SYS>)")
    ap.add_argument("--arms", default="A1,A2")
    ap.add_argument("--faults", default=",".join(FAULTS))
    ap.add_argument("--trials", type=int, default=3)
    ap.add_argument("--seed", type=int, default=424242424)
    ap.add_argument("--out", default=str(WORKSPACE / "tier2_build_trials.jsonl"))
    args = ap.parse_args()

    if os.environ.get("POLYJARVIS_GATES_ADVISORY"):
        sys.exit("refusing: POLYJARVIS_GATES_ADVISORY is set -- recovery trials need binding gates")

    base = json.loads(Path(args.plan).read_text())
    if not str(base.get("run_name", "")).startswith("RECOV_"):
        sys.exit("refusing: base plan run_name must start with RECOV_ so trials cannot "
                 "collide with a campaign directory")

    WORKSPACE.mkdir(parents=True, exist_ok=True)
    lammps = rc._load_server_module("lammps_engine_server", rc.LAMMPS_ENGINE_DIR / "server.py",
                                    rc.LAMMPS_ENGINE_DIR, rc._mcp_env("mcp-lammps-engine"))
    emc = rc._load_server_module("emc_server_module", rc.EMC_SERVER_DIR / "server.py",
                                 rc.EMC_SERVER_DIR, rc._mcp_env("mcp-emc-server"))

    rows = []
    with open(args.out, "a") as sink:
        for fault in [f for f in args.faults.split(",") if f]:
            for arm in [a for a in args.arms.split(",") if a]:
                for n in range(1, args.trials + 1):
                    row = one_trial(base, fault, arm, n, lammps, emc, args.seed)
                    rows.append(row)
                    sink.write(json.dumps(row) + "\n")
                    sink.flush()
                    acts = [d["action"] for d in row["decisions"]]
                    print(f"{fault:15s} {row['persistence']:10s} {arm} t{n}  "
                          f"status={row['status']!s:22.22s} attempts={row['build_attempts']} "
                          f"injected={row['injected']} agent={acts} "
                          f"COMPLETED={row['completed']}  ({row['wall_s']}s)", flush=True)

    print("\ncompletion by fault x arm:")
    for fault in dict.fromkeys(r["fault"] for r in rows):
        for arm in dict.fromkeys(r["arm"] for r in rows):
            sel = [r for r in rows if r["fault"] == fault and r["arm"] == arm]
            if sel:
                print(f"  {fault:15s} {arm}: {sum(r['completed'] for r in sel)}/{len(sel)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
