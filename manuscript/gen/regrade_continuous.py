#!/usr/bin/env python3
"""Regrade every accepted gated cell with appended continuations read as one continuous run.

A continuation restarts the previous segment (`read_restart`) and appends to its trajectory, but
the live gate and the frozen regrades graded only the last segment's log. Here the thermo
section is recomputed on the concatenated logs of the whole restart chain, with the same
checker arguments, gate classification and trajectory evidence as
benchmarks/stereo_r2/regrade_gates.py. A cell whose chain cannot be rebuilt (a segment's log is
no longer on disk) keeps its last-segment verdict and is marked chain_incomplete.

Usage: mcp-servers/.venv/bin/python manuscript/gen/regrade_continuous.py
"""
from __future__ import annotations

import copy
import importlib.util
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "out"
SYSTEMS = ["PE", "PEG", "PLLA", "aPS", "sPVC", "PEEK", "PSU"]
STAGES = {"equilibration": "npt_melt_hold", "cooling": "npt_final"}

_spec = importlib.util.spec_from_file_location("regrade_gates", REPO / "benchmarks/stereo_r2/regrade_gates.py")
rg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rg)
RESTART = re.compile(r"^\s*read_restart\s+(\S+)")
ATTEMPT_IN_PATH = re.compile(r"/attempts/([^/]+)/(attempt-\d+)/")


def segment_chain(run: str, stage: str, attempt: str) -> list[dict]:
    """Oldest-first list of segments feeding the accepted cell's gated sub-stage."""
    sub = STAGES[stage]
    chain, cur = [], attempt
    while cur:
        wd = REPO / "data" / run / "attempts" / stage / cur / "work" / sub
        log = wd / f"{sub}.log"
        chain.append({"attempt": cur, "log": str(log.relative_to(REPO)), "log_exists": log.exists()})
        parent = None
        for deck in sorted(wd.glob("*.in")) if wd.exists() else []:
            for line in deck.read_text(errors="replace").splitlines():
                m = RESTART.match(line)
                if m and f"/{sub}/" in m.group(1):
                    a = ATTEMPT_IN_PATH.search(m.group(1))
                    if a and a.group(1) == stage and a.group(2) != cur:
                        parent = a.group(2)
        if parent is None and not wd.exists():
            es = json.loads((REPO / "data" / run / "attempts" / stage / cur / "executor_state.json").read_text())
            if (es.get("parameters") or {}).get("npt_continuation_attempt" if stage == "equilibration"
                                                  else "cooling_continuation_attempt"):
                chain.append({"attempt": "<unknown parent: deck not on disk>", "log": None, "log_exists": False})
        cur = parent
    return list(reversed(chain))


def regrade(run: str, stage: str, state: dict, plan: dict) -> dict:
    attempt = state["stages"][stage]["accepted_attempt"]
    gate_json = REPO / "data" / run / "attempts" / stage / attempt / "raw" / rg.GATE_FILES[stage]
    stored = json.loads(gate_json.read_text())
    regime = rg.CLAUSE_REGIME[(stored.get("gate") or {})["applicable_clause"]]
    dp = (plan.get("decided_params") or {}).get("dp_typical")
    ct_reliable = rg.class_rules(plan).get("ct_gate_reliable")
    evidence = stored
    if not (stored.get("chain") and stored.get("spatial")):
        offline = gate_json.with_name(gate_json.stem + "_offline_regate.json")
        if offline.exists():
            evidence = json.loads(offline.read_text())

    chain = segment_chain(run, stage, attempt)
    rec = {"accepted_attempt": attempt, "segments": chain, "n_segments": len(chain)}
    complete = all(s["log_exists"] for s in chain)
    logs = [REPO / s["log"] for s in chain if s["log_exists"]]
    if len(chain) > 1 and complete:
        tmp = OUT / "chains" / f"{run}_{stage}.log"
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text("".join(p.read_text(errors="replace") for p in logs))
        log_file, basis = tmp, "continuous_chain"
    else:
        log_file = logs[-1] if logs else None
        basis = "single_segment" if len(chain) == 1 else "chain_incomplete_last_segment_only"
    rec["basis"] = basis
    if log_file is None:
        rec["error"] = "no log on disk"
        return rec
    thermo = rg.checker.check_thermo(log_file=str(log_file), **rg.THERMO_ARGS)
    if "error" in thermo:
        rec["error"] = thermo["error"]
        return rec
    comp = copy.deepcopy(evidence)
    comp["thermo"] = rg.checker.to_native(rg.checker.thermo_section(thermo, rg.N_EFF_MIN))
    rec["verdict"] = rg.grade(comp, regime, dp, ct_reliable)
    t = comp["thermo"]
    rec["thermo"] = {k: {x: (t.get(k) or {}).get(x) for x in ("drift_pct", "sem_pct", "n_eff", "p_value", "pass")}
                     for k in ("energy_drift", "energy_sem", "density_drift", "density_sem", "n_eff_density")}
    rec["n_production_rows"] = (thermo.get("meta") or {}).get("n_production_rows")
    return rec


def main() -> None:
    report = {"generated_at": datetime.now(timezone.utc).isoformat(),
              "gate": {"thermo_args": rg.THERMO_ARGS, "n_eff_min": rg.N_EFF_MIN,
                       "checker_sha256": rg.sha256(rg.CHECKER_DIR / "check_equilibration_comprehensive.py"),
                       "enforce_gate_sha256": rg.sha256(rg.GATE_DIR / "enforce_gate.py")},
              "runs": {}}
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from replicates import reported_runs
    for _, _, run in reported_runs():
        state = json.loads((REPO / "data" / run / "workflow_state.json").read_text())
        plan = json.loads((REPO / "data" / run / "raw" / "run_plan.json").read_text())
        report["runs"][run] = {st: regrade(run, st, state, plan) for st in STAGES}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "regrade_continuous.json").write_text(json.dumps(report, indent=2) + "\n")
    for run, r in report["runs"].items():
        print(run, " | ".join(
            f"{st}: {v.get('verdict', {}).get('verdict', v.get('error'))}"
            f"{' ' + str(v['verdict']['failing_binding_gates']) if v.get('verdict', {}).get('failing_binding_gates') else ''}"
            f" [{v.get('basis')}, {v.get('n_segments')} seg]" for st, v in r.items()))


if __name__ == "__main__":
    main()
