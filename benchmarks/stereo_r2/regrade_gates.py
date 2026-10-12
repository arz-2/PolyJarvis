#!/usr/bin/env python3
"""Regrade the melt and assessment gates of completed stereo_r2 runs under the current gate code.

Why: the energy-drift criterion changed during the campaign (2026-09-09 per-term drift added,
2026-09-10 autocorrelation-corrected p-values, 2026-09-13 every term judged on drift/sigma), so
replicates of one system were adjudicated by different gate versions. This re-applies ONE frozen
version to every run and reports the old verdict next to the new one.

What is recomputed: the thermo section (density/energy drift and SEM, per-term energy drift,
n_eff), from the same log the live gate read (`log_file` in the stored gate JSON), through
check_equilibration_comprehensive.check_thermo + thermo_section -- the live code path.

What is reused: the chain and spatial sections (Rg, chain displacement, torsion, P2,
homogeneity, finite size). They are computed from trajectories by code this change did not touch.

What is NOT touched: every sha256-pinned artifact under data/<run>/attempts/. Results are written
only under benchmarks/stereo_r2/regrade/. Thermal and mechanical verdicts are reported as recorded.

Usage:
    mcp-servers/.venv/bin/python benchmarks/stereo_r2/regrade_gates.py [RUN ...]
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CHECKER_DIR = REPO / "mcp-servers" / "mcp-lammps-engine" / "analysis_scripts"
GATE_DIR = REPO / "orchestration" / "scripts"
sys.path.insert(0, str(CHECKER_DIR))
sys.path.insert(0, str(GATE_DIR))

import check_equilibration_comprehensive as checker  # noqa: E402
import enforce_gate  # noqa: E402

DEFAULT_RUNS = ["aPS_1", "aPS_2", "aPS_3", "sPVC_1", "sPVC_2", "sPVC_3",
                "PLLA_1", "PLLA_2", "PLLA_3"]
GATE_FILES = {"equilibration": "equilibration.json", "cooling": "cooling.json"}
CLAUSE_REGIME = {"require_melt": "melt", "require_glassy": "glassy", "require_rubbery": "rubbery"}
# check_equilibration_comprehensive.main() defaults; run_campaign passes none of these, so the
# live gate ran on exactly these values.
THERMO_ARGS = dict(eq_fraction=0.5, drift_threshold_pct=1.0, drift_pvalue=0.01, block_count=10,
                   temp_col="Temp", density_col="Density", energy_col="TotEng",
                   pressure_cols=["Pxx", "Pyy", "Pzz"])
N_EFF_MIN = 20


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verdict_of(binding: dict) -> tuple[str, list[str]]:
    failing = sorted(k for k, v in binding.items() if v is False)
    if not binding:
        return "FAIL", ["<no binding gate measured>"]
    return ("FAIL" if failing else "PASS"), failing


def class_rules(plan: dict) -> dict:
    rules = json.loads((REPO / "guides" / "polymer_rules.json").read_text())
    classes = rules.get("classes", rules)
    cls = plan.get("polymer_class") or (plan.get("decided_params") or {}).get("polymer_class")
    return classes.get(cls, {}) if isinstance(classes, dict) else {}


STAGE_LOG = {"equilibration": ("melt_log_path", "npt_melt_hold"),
             "cooling": ("npt_prod_log_path", "npt_final")}


def resolve_log(run: str, stage: str, attempt: str, stored: dict):
    """The log the live gate read: the gate JSON's own record first, then the executor's, then
    the stage's fixed path inside the attempt. Returns (path, which source), or (None, None)."""
    attempt_dir = REPO / "data" / run / "attempts" / stage / attempt
    key, stage_dir = STAGE_LOG[stage]
    outputs = json.loads((attempt_dir / "executor_state.json").read_text()).get("outputs") or {}
    for source, path in (("gate_json.log_file", stored.get("log_file")),
                         (f"executor_state.outputs.{key}", outputs.get(key)),
                         ("attempt_work_dir", str(attempt_dir / "work" / stage_dir / f"{stage_dir}.log"))):
        if path and Path(path).exists():
            return path, source
    return None, None


def grade(comp: dict, regime: str, dp, ct_reliable) -> dict:
    gates = enforce_gate.collect_gates(comp)
    clause, binding, advisory, unmeasured = enforce_gate.classify(gates, regime, dp, ct_reliable)
    verdict, failing = verdict_of(binding)
    return {"clause": clause, "verdict": verdict, "failing_binding_gates": failing,
            "unmeasured_binding_gates": unmeasured,
            "failing_advisory_gates": sorted(k for k, v in advisory.items() if v is False)}


def regrade_stage(run: str, stage: str, state: dict, plan: dict) -> dict:
    attempt = state["stages"][stage]["accepted_attempt"]
    gate_json = REPO / "data" / run / "attempts" / stage / attempt / "raw" / GATE_FILES[stage]
    stored = json.loads(gate_json.read_text())
    stored_gate = stored.get("gate") or {}
    regime = CLAUSE_REGIME[stored_gate["applicable_clause"]]
    dp = (plan.get("decided_params") or {}).get("dp_typical")
    ct_reliable = class_rules(plan).get("ct_gate_reliable")

    old = grade(stored, regime, dp, ct_reliable)

    # A pinned gate file with no chain/spatial sections is a vacuous gate (sPVC_1's melt, see
    # FINDING_gate_fails_open.md). Its operator re-measurement on the correct trajectories sits
    # beside it with an _offline_regate suffix; take trajectory evidence from there, and say so.
    evidence, evidence_source = stored, "pinned_gate_file"
    if not (stored.get("chain") and stored.get("spatial")):
        offline = gate_json.with_name(gate_json.stem + "_offline_regate.json")
        if offline.exists():
            evidence, evidence_source = json.loads(offline.read_text()), str(offline.relative_to(REPO))

    log_file, log_source = resolve_log(run, stage, attempt, evidence)
    if log_file is None:
        return {"attempt": attempt, "error": "no gate log found"}
    thermo = checker.check_thermo(log_file=log_file, **THERMO_ARGS)
    if "error" in thermo:
        return {"attempt": attempt, "error": thermo["error"]}
    new_comp = copy.deepcopy(evidence)
    new_comp["thermo"] = checker.to_native(checker.thermo_section(thermo, N_EFF_MIN))
    new = grade(new_comp, regime, dp, ct_reliable)

    components = (new_comp["thermo"].get("energy_component_drift") or {}).get("components", {})
    changed_thermo = sorted(
        k for k in ("density_drift", "energy_drift", "density_sem", "energy_sem", "n_eff_density")
        if (stored.get("thermo", {}).get(k) or {}).get("pass") != (new_comp["thermo"].get(k) or {}).get("pass"))
    return {
        "attempt": attempt, "gate_file": str(gate_json.relative_to(REPO)),
        "log_file": log_file, "log_source": log_source, "trajectory_evidence": evidence_source,
        "stored_live_verdict": stored_gate.get("verdict"),
        "stored_failing_binding_gates": stored_gate.get("failing_binding_gates"),
        "old_version": old, "new_version": new,
        "clause_matches_stored": new["clause"] == stored_gate["applicable_clause"],
        "thermo_pass_flags_changed_besides_components": changed_thermo,
        "energy_components_new": {k: {x: v.get(x) for x in ("drift_sigma", "drift_pct", "p_value", "pass")}
                                  for k, v in components.items()},
    }


def recorded_verdicts(run: str, state: dict) -> dict:
    out = {}
    for stage, keys in (("thermal", ("tg_gate_verdict",)),
                        ("mechanical", ("bm_gate_verdict", "bm_convergence_verdict"))):
        attempt = state["stages"].get(stage, {}).get("accepted_attempt")
        if not attempt:
            continue
        es = json.loads((REPO / "data" / run / "attempts" / stage / attempt / "executor_state.json").read_text())
        o = es.get("outputs") or {}
        out[stage] = {k: o.get(k) for k in keys}
        if o.get("gate_verdict_advisory"):
            out[stage]["accepted_under_advisory_mode"] = True
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("runs", nargs="*", default=DEFAULT_RUNS)
    ap.add_argument("--out-dir", type=Path, default=Path(__file__).resolve().parent / "regrade")
    args = ap.parse_args()

    commit = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"],
                            capture_output=True, text=True).stdout.strip()
    dirty = bool(subprocess.run(["git", "-C", str(REPO), "status", "--porcelain", "--",
                                 str(CHECKER_DIR / "check_equilibration_comprehensive.py"),
                                 str(GATE_DIR / "enforce_gate.py")],
                                capture_output=True, text=True).stdout.strip())
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "gate_version": {
            "git_head": commit, "gate_files_uncommitted": dirty,
            "check_equilibration_comprehensive_sha256": sha256(CHECKER_DIR / "check_equilibration_comprehensive.py"),
            "enforce_gate_sha256": sha256(GATE_DIR / "enforce_gate.py"),
            "energy_component_criterion": "drift_sigma for all terms",
        },
        "runs": {},
    }
    for run in args.runs:
        state = json.loads((REPO / "data" / run / "workflow_state.json").read_text())
        plan = json.loads((REPO / "data" / run / "raw" / "run_plan.json").read_text())
        report["runs"][run] = {
            "stages": {s: regrade_stage(run, s, state, plan) for s in GATE_FILES},
            "recorded": recorded_verdicts(run, state),
        }

    args.out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d")
    (args.out_dir / f"regrade_{stamp}.json").write_text(json.dumps(report, indent=2))

    lines = [f"# stereo_r2 gate regrade ({stamp})", "",
             f"Gate code: HEAD {commit}{' + uncommitted gate changes' if dirty else ''}; "
             "energy components judged on drift/sigma for all terms.", "",
             "| Run | Stage | Clause | Old version | New version | Live verdict recorded |",
             "|---|---|---|---|---|---|"]
    for run, r in report["runs"].items():
        for stage, s in r["stages"].items():
            if "error" in s:
                lines.append(f"| {run} | {stage} | — | error | {s['error']} | — |")
                continue
            fmt = lambda g: g["verdict"] + (f" ({', '.join(g['failing_binding_gates'])})" if g["failing_binding_gates"] else "")
            lines.append(f"| {run} | {stage} | {s['new_version']['clause']} | {fmt(s['old_version'])} | "
                         f"{fmt(s['new_version'])} | {s['stored_live_verdict']} |")
    lines += ["", "Thermal / mechanical verdicts (as recorded, not regraded):", ""]
    for run, r in report["runs"].items():
        lines.append(f"- {run}: {json.dumps(r['recorded'])}")
    (args.out_dir / f"regrade_{stamp}.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
