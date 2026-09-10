#!/usr/bin/env python3
"""R1 -- score the recovery events real campaigns have already produced. Zero GPU.

Reviewer comment 3 asks that recovery be defined as "successful completion of the intended
simulation and property calculation," not as a correct diagnosis. Round 1's own artifacts
show why that distinction matters: RECOV_F5_AGENT/ and RECOV_F6_AGENT/ record
`"resolved": true` while their run logs say "Rebuild + equilibration not executed (task
scope = diagnose + decide)" and their `stages_completed` is []. This scorer applies the
reviewer's definition instead.

RECOVERED means: the stage the finding fired on subsequently reached status `accepted`.
Not "a remedy was applied", not "no more errors in the log". A stage still in flight scores
PENDING and is excluded from the rate's denominator rather than counted as either outcome.

These are unplanned failures from production runs -- the strictest reading of the reviewer's
"unseen failure cases", since nobody chose them.

    python3 benchmarks/recovery_r2/harvest.py [--json] [--runs A,B]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent

#: stereo_r2 is the manuscript campaign. Anything else (probes, gate validations) is a
#: different denominator and is reported separately rather than pooled into the headline.
CAMPAIGN_PREFIXES = ("iPMMA_", "aPS_", "sPVC_", "PLLA_", "PE_", "PEEK_", "PSU_")


def is_campaign(run: str) -> bool:
    return any(run.startswith(p) for p in CAMPAIGN_PREFIXES)


def outcome_for(state: dict, stage: str) -> str:
    """The reviewer's predicate, read straight off the stage record."""
    record = (state.get("stages") or {}).get(stage)
    if record is None:
        return "stage_absent"
    status = record.get("status")
    if status == "accepted":
        return "recovered"
    if status in ("running", "pending", "remedy_required"):
        return "pending"
    return "not_recovered"


def harvest_run(path: Path) -> dict:
    state = json.loads(path.read_text())
    run = path.parent.name
    events = []
    for event in state.get("remedy_history") or []:
        finding = event.get("finding") or {}
        stage = finding.get("stage")
        events.append({
            "run": run, "at": event.get("at"), "stage": stage,
            "code": finding.get("code"), "remedy_id": event.get("remedy_id"),
            "application": event.get("application"),
            "severity": finding.get("severity"),
            "outcome": outcome_for(state, stage),
            "detail": str((finding.get("details") or {}).get("error", ""))[:160],
        })
    # Escalations must be read from BOTH lists: an operator can retire a spent escalation
    # (PLLA_1 and aPS_1, 2026-09-09), and reading only the live counter under-reports the
    # autonomy cost -- both runs currently show agent_escalations=0 having actually spent two.
    live = state.get("agent_escalations") or []
    retired = state.get("agent_escalations_retired_by_operator") or []
    # The retired entries carry the agent's ACTUAL decision, not just a count. That is the
    # {retry, revise_plan, stop} distribution R3 was designed to measure, already partly on
    # disk -- so extract it rather than re-deriving it from injected faults alone.
    decisions = [{"run": run, "at": e.get("at"), "retired": src == "retired",
                  "action": (e.get("decision") or {}).get("action"),
                  "modifications": (e.get("decision") or {}).get("modifications") or {},
                  "rationale": str((e.get("decision") or {}).get("rationale") or "")[:400]}
                 for src, entries in (("live", live), ("retired", retired))
                 for e in entries]
    return {
        "agent_decisions": decisions,
        "run": run,
        "campaign": is_campaign(run),
        "status": state.get("status"),
        "events": events,
        "escalations_live": len(live),
        "escalations_retired_by_operator": len(retired),
        "escalations_total": len(live) + len(retired),
        "operator_interventions": len(state.get("operator_interventions") or []),
        "stages": {k: v.get("status") for k, v in (state.get("stages") or {}).items()},
    }


def summarize(runs: list[dict]) -> dict:
    events = [e for r in runs if r["campaign"] for e in r["events"]]
    scored = [e for e in events if e["outcome"] in ("recovered", "not_recovered")]
    recovered = [e for e in scored if e["outcome"] == "recovered"]
    by_remedy: dict[str, Counter] = {}
    for e in events:
        by_remedy.setdefault(e["remedy_id"] or "?", Counter())[e["outcome"]] += 1
    campaign = [r for r in runs if r["campaign"]]
    decisions = [d for r in campaign for d in r["agent_decisions"]]
    return {
        "agent_decision_actions": dict(Counter(d["action"] for d in decisions)),
        "agent_decisions_with_a_plan_change": sum(1 for d in decisions if d["modifications"]),
        "runs_with_state": len(runs),
        "campaign_runs": len(campaign),
        "remedy_events_total": len(events),
        "scored": len(scored),
        "pending_excluded": len(events) - len(scored),
        "recovered": len(recovered),
        "completion_rate": (round(len(recovered) / len(scored), 3) if scored else None),
        "by_remedy": {k: dict(v) for k, v in sorted(by_remedy.items())},
        "by_code": dict(Counter(e["code"] for e in events).most_common()),
        "escalations_total": sum(r["escalations_total"] for r in campaign),
        "escalations_retired_by_operator": sum(r["escalations_retired_by_operator"]
                                               for r in campaign),
        "operator_interventions": sum(r["operator_interventions"] for r in campaign),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--runs", help="Comma-separated run names; default every run with state")
    ap.add_argument("--out", default=str(HERE / "harvest.json"))
    args = ap.parse_args()

    paths = sorted((REPO_ROOT / "data").glob("*/workflow_state.json"))
    if args.runs:
        wanted = {s.strip() for s in args.runs.split(",") if s.strip()}
        paths = [p for p in paths if p.parent.name in wanted]
    runs = [harvest_run(p) for p in paths]
    summary = summarize(runs)
    payload = {"summary": summary, "runs": runs}
    Path(args.out).write_text(json.dumps(payload, indent=2) + "\n")

    if args.json:
        print(json.dumps(payload, indent=2))
        return 0

    print(f"{summary['campaign_runs']} campaign run(s), "
          f"{summary['remedy_events_total']} remedy event(s)\n")
    print(f"{'run':10s} {'stage':14s} {'code':26s} {'remedy':20s} outcome")
    for r in runs:
        for e in r["events"]:
            flag = "" if r["campaign"] else "  (non-campaign)"
            print(f"{e['run']:10s} {e['stage'] or '?':14s} {e['code'] or '?':26s} "
                  f"{e['remedy_id'] or '?':20s} {e['outcome']}{flag}")
    print(f"\nCOMPLETION RATE (campaign runs, reviewer's definition):")
    print(f"  recovered {summary['recovered']} / {summary['scored']} scored"
          + (f" = {summary['completion_rate']:.0%}" if summary["completion_rate"] is not None else "")
          + f"   ({summary['pending_excluded']} still in flight, excluded)")
    print(f"  by remedy: {summary['by_remedy']}")
    print(f"\nAUTONOMY COST")
    print(f"  agent escalations: {summary['escalations_total']} "
          f"({summary['escalations_retired_by_operator']} retired by an operator -- the live "
          f"counter alone under-reports)")
    print(f"  operator interventions: {summary['operator_interventions']}")
    print(f"  recovery-agent decisions: {summary['agent_decision_actions']} "
          f"({summary['agent_decisions_with_a_plan_change']} carried an actual plan change)")
    for r in runs:
        for d in r.get("agent_decisions", []):
            print(f"      {d['run']:9s} {str(d['at'])[:19]} {d['action']:12s} "
                  f"mods={d['modifications'] or '{}'}")
    print(f"\nwrote {Path(args.out).relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
