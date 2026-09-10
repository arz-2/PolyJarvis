#!/usr/bin/env python3
"""N-trial failure-injection runner. Two tiers, and the difference between them matters.

  TIER 1 -- ROUTING (this script, zero GPU, seconds)
      Really inject the fault into a real EMC cell and classify it through run_campaign's
      own validation call (injectors.py), then drive the REAL WorkflowEngine with the
      Finding that produced. Measures: which remedy the registry selects, how many
      applications it allows before the cap binds, whether it escalates, and -- the point of
      the ablation -- where the arms diverge. The executor is scripted, so COMPLETION here is
      scripted too: tier 1 measures the ladder's decisions, never physics.

  TIER 2 -- COMPLETION (needs GPU, not this script)
      The same injected cell driven through a real campaign, scored on whether the stage
      reaches `accepted` and the run yields a gate-passing property value. That is the
      reviewer's definition and only tier 2 can answer it.

Reporting tier 1 as if it were tier 2 would repeat exactly the error this benchmark exists to
correct -- round 1 recorded `resolved: true` for runs whose `stages_completed` was `[]`.

Arms, per reviewer comment 3's "incremental contribution of the LLM":
    A1 deterministic -- recovery_agent=None. Escalation is terminal.
    A2 full          -- a recovery agent is wired. Escalation consults it, capped at
                        MAX_AGENT_DECISIONS=2.
A0 (stock) is a planning-time arm and has no meaning here: it has no recovery ladder at all.

    python3 benchmarks/recovery_r2/run_trials.py [--trials 3] [--json]
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))

from workflow_engine import Finding, StageResult, WorkflowEngine, MAX_AGENT_DECISIONS  # noqa: E402
import injectors  # noqa: E402


class ScriptedExecutor:
    """Fails `n_failures` times with the injected finding, then succeeds.

    The finding is the one a REAL corrupted cell produced, not a string chosen here -- that
    is what ties tier 1 to tier 2. What is scripted is only how many times the fault recurs.
    """

    def __init__(self, stage: str, code: str, n_failures: int):
        self.stage, self.code, self.n_failures = stage, code, n_failures
        self.calls = 0

    def execute(self, stage, context):
        attempt = Path(context["attempt_dir"])
        artifact = attempt / f"{stage}.json"
        artifact.write_text(json.dumps({"stage": stage}))
        if stage == self.stage:
            self.calls += 1
            if self.calls <= self.n_failures:
                return StageResult("remedy_required",
                                   (Finding(self.code, stage, confidence="high",
                                            details={"error": "injected"}),),
                                   (str(artifact),), {})
        outputs = {}
        if stage == "thermal":
            outputs["tg_gate_verdict"] = "TG_REPORTABLE"
        if stage == "mechanical":
            outputs.update({"method": "murnaghan", "bm_gate_verdict": "BM_REPORTABLE"})
        return StageResult("accepted", artifacts=(str(artifact),), outputs=outputs)


class RecordingAgent:
    """A2's recovery agent. Records every consultation; never invents a fix.

    Returning `stop` is the honest stub: the live campaign's own four agent calls came back
    stop x3 / revise_plan x1, and a stub that always repaired would inflate A2 exactly where
    the ablation is trying to measure it.
    """

    def __init__(self):
        self.calls = []

    def __call__(self, payload):
        self.calls.append(payload)
        return {"action": "stop", "rationale": "benchmark stub", "modifications": {}}

    decide = __call__


def plan_for(stage: str) -> dict:
    props = {"build": ["density"], "equilibration": ["density"],
             "thermal": ["tg"], "mechanical": ["bulk_modulus"]}.get(stage, ["density"])
    return {"run_name": "INJ", "polymer_class": "PSTR", "properties": props,
            "decided_params": {"tg_t_step_K": 20, "tg_rate_K_per_ns": 100, "dt_fs": 1.0}}


def one_trial(stage: str, code: str, arm: str, n_failures: int, workdir: Path) -> dict:
    agent = RecordingAgent() if arm == "A2" else None
    executor = ScriptedExecutor(stage, code, n_failures)
    engine = WorkflowEngine(workdir, plan_for(stage), executor, recovery_agent=agent)
    try:
        result = engine.run()
        status = result.get("status") if isinstance(result, dict) else str(result)
    except Exception as exc:                                   # noqa: BLE001
        status = f"raised:{type(exc).__name__}"
    state = json.loads((workdir / "workflow_state.json").read_text())
    counters = state.get("remedy_counters") or {}
    return {
        "arm": arm, "status": status,
        "stage_status": (state.get("stages") or {}).get(stage, {}).get("status"),
        "remedies_applied": counters.get("total", 0),
        "by_id": counters.get("by_id", {}),
        "agent_calls": len(agent.calls) if agent else 0,
        "escalations": len(state.get("agent_escalations") or []),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--trials", type=int, default=3)
    ap.add_argument("--failures", type=int, default=3,
                    help="How many times the injected fault recurs before the cell would "
                         "build clean. Default 3 exceeds every automatic cap (max 2), so the "
                         "ladder is driven to exhaustion and the arms must diverge.")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    data, params = injectors.find_cell()
    if not data:
        print("no completed build to inject into")
        return 1

    # Tier 1 step 1: prove the codes are real before measuring anything about them.
    verified = injectors.verify(data, params)
    if verified["failures"]:
        print("injection verification FAILED -- not measuring routing on unproven codes:")
        for f in verified["failures"]:
            print(f"  {f}")
        return 1

    root = Path(tempfile.mkdtemp(prefix="trials_"))
    rows = []
    for inj in verified["injectors"]:
        code = inj["got"]
        stage = "build" if code in ("BUILD_CELL_INVALID", "SIZE_MIN_IMAGE_VIOLATION") else "equilibration"
        for arm in ("A1", "A2"):
            for trial in range(args.trials):
                wd = root / f"{inj['id']}_{arm}_{trial}"
                wd.mkdir(parents=True)
                rows.append({"injector": inj["id"], "code": code, "trial": trial,
                             **one_trial(stage, code, arm, args.failures, wd)})

    summary = {}
    for inj in verified["injectors"]:
        for arm in ("A1", "A2"):
            sel = [r for r in rows if r["injector"] == inj["id"] and r["arm"] == arm]
            summary[f"{inj['id']}/{arm}"] = {
                "status": dict(Counter(r["status"] for r in sel)),
                "remedies_applied": sorted({r["remedies_applied"] for r in sel}),
                "remedy_ids": sorted({k for r in sel for k in r["by_id"]}),
                "agent_calls": sorted({r["agent_calls"] for r in sel}),
            }
    payload = {"tier": "routing (tier 1) -- COMPLETION IS SCRIPTED, NOT MEASURED",
               "cell": str(data), "trials_per_arm": args.trials,
               "recurrences_injected": args.failures,
               "max_agent_decisions": MAX_AGENT_DECISIONS,
               "verification": verified, "summary": summary, "trials": rows}
    (HERE / "trials.json").write_text(json.dumps(payload, indent=2) + "\n")

    if args.json:
        print(json.dumps(payload, indent=2))
        return 0
    print(f"cell: {data}")
    print(f"control: clean cell produces no error\n")
    print(f"{len(verified['injectors'])}/{len(verified['injectors'])} injectors fire their "
          f"target code; {args.trials} trials/arm, fault recurs {args.failures}x "
          f"(every automatic cap is <= 2)\n")
    print(f"{'injector/arm':28s} {'status':26s} {'remedies':9s} {'agent':6s} remedy_ids")
    for key, row in summary.items():
        print(f"{key:28s} {str(row['status']):26s} {str(row['remedies_applied']):9s} "
              f"{str(row['agent_calls']):6s} {row['remedy_ids']}")
    print(f"\nwrote {(HERE / 'trials.json').relative_to(REPO_ROOT)}")
    print("\nTIER 1 measures routing, caps and arm divergence. It does NOT measure completion "
          "-- the executor is scripted. Completion is tier 2 and needs GPU.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
