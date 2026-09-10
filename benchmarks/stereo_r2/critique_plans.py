#!/usr/bin/env python3
"""Run the literature critic + adjudicator over an already-autofilled run plan.

The architecture is tool-autofills / agent-critiques, and `confidence` is the gate:
`make_deterministic_plan` stamps "unreviewed", which is deliberately INVALID, and
critique -> adjudicate is what clears it. Building the plans with `--baseline` (confidence
"low") skipped that gate entirely, which is what this repairs.

Why not just run `run_graph.py`: its `plan` node re-runs `make_deterministic_plan --force`,
which would discard the per-system `overrides` block (stereo-corrected experimental Tg, the
pinned bm_pressures ladder, T_workflow_K). Those pins are part of what the critic is supposed
to evaluate, not something to regenerate away. So this drives nodes.critique and
nodes.adjudicate directly against the plan already on disk.

polymer_class comes from MANIFEST.json, not from the classifier: polyinfo_classifier returns
PHAL for the sPVC dyad. classify still runs, because its chemistry profile is what the
adjudicator is handed as context -- the divergence is recorded rather than silently accepted.

Usage:
    python3 benchmarks/stereo_r2/critique_plans.py --only PEEK        # one system
    python3 benchmarks/stereo_r2/critique_plans.py                    # all seven
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "langgraph"))
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))

import nodes  # noqa: E402

INTERESTING = ("confidence", "dominant_uncertainty", "plan_mode")


def plan_snapshot(path: Path) -> dict:
    doc = json.loads(path.read_text())
    d01 = next((r for r in doc.get("decisions", []) if r["id"] == "D-01_ff"), {})
    return {
        "confidence": doc.get("confidence"),
        "dominant_uncertainty": doc.get("dominant_uncertainty"),
        "overrides": dict(doc.get("overrides") or {}),
        "d01_choice": d01.get("choice"),
        "evidence_origins": sorted({e.get("origin") for e in d01.get("evidence", [])}),
        "n_evidence": len(d01.get("evidence", [])),
    }


def run_one(name: str, spec: dict, properties: list[str],
            reuse_grounding: bool = False) -> dict:
    run_name = f"{name}_1"
    plan_path = REPO_ROOT / "data" / run_name / "raw" / "run_plan.json"
    if not plan_path.is_file():
        return {"system": name, "error": f"no plan at {plan_path}"}

    before = plan_snapshot(plan_path)
    state = {
        "run_name": run_name,
        "smiles": spec["smiles"],
        "properties": properties,
        "repo_root": str(REPO_ROOT),
        "plan_path": str(plan_path),
        "polymer_class": spec["polymer_class"],
    }

    classified = nodes.classify(dict(state))
    if classified.get("status") == "stopped":
        return {"system": name, "error": f"classify: {classified}"}
    # The chemistry profile and classification.json are wanted; the LABEL is not -- see the
    # module docstring. Record the divergence instead of adopting it.
    state["classification_path"] = classified.get("classification_path")
    state["chemistry"] = classified.get("chemistry")
    classifier_said = classified.get("polymer_class")

    grounding = REPO_ROOT / "data" / run_name / "raw" / "literature_grounding.json"
    if reuse_grounding and grounding.is_file():
        # Re-adjudicate against evidence already gathered. The critic has real run-to-run
        # variance (PEEK returned opposite verdicts on two runs over the same plan), so when
        # the question is "what would the adjudicator do with THIS evidence", re-searching
        # changes the input and answers a different question.
        critiqued = {"grounding_path": str(grounding),
                     "critic_verdict": (((json.loads(grounding.read_text()).get("critique") or {})
                                         .get("D-01_ff")) or {}).get("verdict")}
    else:
        critiqued = nodes.critique(dict(state))
    state.update({k: v for k, v in critiqued.items() if k != "events"})

    adjudicated = nodes.adjudicate(dict(state))
    after = plan_snapshot(plan_path)

    return {
        "system": name,
        "run_name": run_name,
        "polymer_class_used": spec["polymer_class"],
        "classifier_said": classifier_said,
        "critic_verdict": critiqued.get("critic_verdict"),
        "grounding_path": critiqued.get("grounding_path"),
        "adjudication": adjudicated.get("adjudication"),
        "before": before,
        "after": after,
        "changed": {k: [before[k], after[k]] for k in before if before[k] != after[k]},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", default=None, help="Comma-separated system ids.")
    parser.add_argument("--reuse-grounding", action="store_true",
                        help="Skip the literature search; adjudicate the grounding already on disk.")
    args = parser.parse_args()

    manifest = json.loads((HERE / "MANIFEST.json").read_text())
    systems = manifest["systems"]
    if args.only:
        wanted = {s.strip() for s in args.only.split(",") if s.strip()}
        systems = {k: v for k, v in systems.items() if k in wanted}

    results = []
    for name, spec in systems.items():
        print(f"=== {name}", flush=True)
        result = run_one(name, spec, manifest["design"]["properties"], args.reuse_grounding)
        results.append(result)
        print(json.dumps({k: v for k, v in result.items() if k != "before"}, indent=2)[:2000],
              flush=True)

    out = HERE / "critique_results.json"
    existing = json.loads(out.read_text()) if out.is_file() else []
    existing = [r for r in existing if r.get("system") not in {r2["system"] for r2 in results}]
    out.write_text(json.dumps(existing + results, indent=2))
    print(f"\nwrote {out.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
