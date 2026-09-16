#!/usr/bin/env python3
"""Agent ablation on PTFE: the facts behind main-text Table `tab:recovery` and SI S8.

Read-only. Writes gen/out/recovery_ablation.json and never touches data/<run>/.

  1. formula sweep   -- the melt density-homogeneity signal under the per-frame formula, as
                        stored by each campaign run's accepted melt gate, plus both PTFE arms.
                        This is the evidence that the formula's false positive is chemistry
                        specific: every campaign chemistry passes it, PTFE fails it in both arms.
  2. current check   -- both PTFE melts regraded with the committed split_half form, by running
                        check_equilibration_comprehensive.py into gen/out/recovery_ablation/.
  3. arm outcomes    -- terminal status, agent decisions, operator interventions, and the
                        accepted 300 K density and K of each PolyJarvis arm; RadonPy stock arm
                        phase status from its timestamps.
"""
from __future__ import annotations

import glob
import json
import subprocess
import sys
from pathlib import Path

from replicates import REPO, reported_runs

OUT = Path(__file__).resolve().parent / "out"
WORK = OUT / "recovery_ablation"
CHECKER = REPO / "mcp-servers" / "mcp-lammps-engine" / "analysis_scripts" / "check_equilibration_comprehensive.py"
RADONPY = REPO / "benchmarks" / "polyjarvis_vs_radonpy" / "data" / "PTFE" / "radonpy"
ARMS = {"PTFE_noAI": "no agent", "PTFE_AI": "agent"}


def load(p: Path):
    try:
        return json.loads(Path(p).read_text())
    except (OSError, ValueError):
        return None


def accepted_attempt(run: str, stage: str) -> Path | None:
    ws = load(REPO / "data" / run / "workflow_state.json") or {}
    rec = (ws.get("stages") or {}).get(stage) or {}
    att = rec.get("accepted_attempt") or rec.get("current_attempt")
    if att:
        return REPO / "data" / run / "attempts" / stage / att
    found = sorted(glob.glob(str(REPO / "data" / run / "attempts" / stage / "attempt-*")))
    return Path(found[-1]) if found else None


def melt_formula_signal(run: str) -> dict:
    a = accepted_attempt(run, "equilibration")
    eq = load(a / "raw" / "equilibration.json") if a else None
    dh = ((eq or {}).get("spatial") or {}).get("density_homogeneity") or {}
    return {"run": run, "attempt": a.name if a else None, "decided_by": dh.get("decided_by", "formula"),
            "formula_signal": dh.get("cv_signal"), "formula_limit": dh.get("cv_signal_max"),
            "formula_verdict": dh.get("legacy_formula_verdict") or dh.get("verdict")}


def regrade_split_half(run: str) -> dict:
    a = accepted_attempt(run, "equilibration")
    w = a / "work"
    out = WORK / run
    out.mkdir(parents=True, exist_ok=True)
    if "--force" in sys.argv or not (out / "equilibration.json").exists():
        _run_checker(a, w, out)
    return _summarize(run, out)


def _run_checker(a: Path, w: Path, out: Path) -> None:
    cmd = [sys.executable, str(CHECKER),
           "--log_file", str(w / "npt_melt_hold" / "npt_melt_hold.log"),
           "--dump_file", str(w / "nvt_melt_hold" / "nvt_melt_hold.dump"),
           "--data_file", str(w / "npt_melt_hold" / "npt_melt_hold_out.data"),
           "--struct_dump_file", str(w / "npt_melt_hold" / "npt_melt_hold.dump"),
           "--struct_data_file", str(w / "npt_melt_hold" / "npt_melt_hold_out.data"),
           "--backbone_types", *map(str, (load(a / "raw" / "equilibration.json") or {}).get("backbone_types") or [1, 2]),
           "--homog_method", "split_half", "--output_dir", str(out)]
    subprocess.run(cmd, check=True, capture_output=True)


def _summarize(run: str, out: Path) -> dict:
    res = load(out / "equilibration.json")
    dh = res["spatial"]["density_homogeneity"]
    failing = [k for k, v in (res.get("gate", {}).get("binding_gates") or {}).items() if v is False]
    return {"run": run, "method": dh.get("decided_by"), "persistent_cv": (dh.get("split_half") or {}).get("persistent_cv"),
            "limit": dh.get("signal_max"), "frames": (dh.get("split_half") or {}).get("frames"),
            "homogeneity_pass": dh.get("pass"), "overall_pass": res.get("overall_pass"),
            "formula_signal_same_trajectory": dh.get("cv_signal")}


def arm_outcome(run: str) -> dict:
    d = REPO / "data" / run
    ws = load(d / "workflow_state.json") or {}
    stages = {k: v.get("status") for k, v in (ws.get("stages") or {}).items()}
    summ = accepted_attempt(run, "summary")
    rs = None
    if summ:
        hits = glob.glob(str(summ / "**" / "run_summary.json"), recursive=True)
        rs = load(Path(hits[0])) if hits else None
    decisions = []
    for line in (d / "recovery_log.jsonl").read_text().splitlines() if (d / "recovery_log.jsonl").exists() else []:
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        # Agent decisions are the escalation events that carry an action; auto_remedy_* events
        # are the deterministic layer.
        if ev.get("event") == "escalation" and ev.get("action"):
            decisions.append({"at": ev.get("at"), "stage": ev.get("stage"), "code": ev.get("code"),
                              "action": ev.get("action"), "outcome": ev.get("outcome")})
    return {"run": run, "arm": ARMS[run], "stages": stages, "terminated_by": ws.get("terminated_by"),
            "operator_interventions": [{k: i.get(k) for k in ("action", "at", "arm_note")}
                                       for i in ws.get("operator_interventions") or []],
            "agent_decisions": decisions, "run_summary": rs}


def radonpy_arm() -> dict:
    phases = {}
    for name in ("timestamps_qm.json", "timestamps_gpu_crash_20260914.json", "timestamps.json"):
        t = load(RADONPY / name)
        if t:
            phases[name] = {"status": t.get("status"), "phases": t.get("phases"),
                            "deviations_from_stock": t.get("deviations_from_stock")}
    log = (RADONPY / "eq.log").read_text(errors="ignore").splitlines() if (RADONPY / "eq.log").exists() else []
    return {"records": phases, "eq_log_last_info": [l for l in log if l.startswith("RadonPy info")][-4:]}


def main() -> int:
    campaign = [melt_formula_signal(run) for _, _, run in reported_runs()]
    ptfe = [melt_formula_signal(r) for r in ARMS]
    signals = [c["formula_signal"] for c in campaign if c["formula_signal"] is not None]
    doc = {
        "formula_sweep": {"campaign": campaign, "ptfe": ptfe,
                          "campaign_max_signal": max(signals) if signals else None,
                          "campaign_n_pass": sum(c["formula_verdict"] == "HOMOG_PASS" for c in campaign),
                          "campaign_n": len(campaign)},
        "split_half_regrade": [regrade_split_half(r) for r in ARMS],
        "arms": [arm_outcome(r) for r in ARMS],
        "radonpy_stock": radonpy_arm(),
    }
    OUT.mkdir(exist_ok=True)
    (OUT / "recovery_ablation.json").write_text(json.dumps(doc, indent=1, default=str))
    print(json.dumps({"campaign_formula_pass": f"{doc['formula_sweep']['campaign_n_pass']}/{doc['formula_sweep']['campaign_n']}",
                      "campaign_max_signal": doc["formula_sweep"]["campaign_max_signal"],
                      "ptfe_formula": [(p["run"], p["formula_signal"], p["formula_verdict"]) for p in ptfe],
                      "split_half": [(s["run"], s["persistent_cv"], s["homogeneity_pass"], s["overall_pass"])
                                     for s in doc["split_half_regrade"]]}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
