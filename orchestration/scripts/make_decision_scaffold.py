#!/usr/bin/env python3
"""
make_decision_scaffold.py — Emit a deterministic decision.json scaffold for a polymer class.

This is the SMALL agent-facing scaffold (PlanDecision's schema in scientific_control.py), not
the full run_plan.json (see make_deterministic_plan.py for that). It pre-populates
decision_evaluations with one row per build_decisions() policy id, each carrying the class's
current default_choice, criteria_evaluated, and any transcribable evidence -- so the
novel-run-plan skill's planning agent edits/annotates this file in place instead of authoring
it from scratch.

default_choice is READ-ONLY provenance: materialize_plan() only reads criteria_evaluated /
evidence / alternatives off each decision_evaluations row, so editing default_choice has no
effect on the materialized plan. To disagree with a shown default, add the corresponding key
to top-level `overrides` instead.

rationale is intentionally left [] and confidence intentionally left "unreviewed" -- both are
invalid per scientific_control.py's _validate_decision()/VALID_CONFIDENCE, so materialization
stays blocked until the agent has actually written real reasoning and picked low/medium/high.

Usage:
  python3 orchestration/scripts/make_decision_scaffold.py \
      --run_name PE7 --polymer_class PHYC \
      [--smiles "*CC*"] [--properties density,tg,bulk_modulus] \
      [--out PATH] [--force]   # default out: data/<run_name>/raw/decision.json; "-" = stdout
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hw_common import load_rules, get_class_entry  # noqa: E402
from make_deterministic_plan import build_decisions  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def make_decision_scaffold(polymer_class: str, properties: set) -> dict:
    rules = load_rules()
    if polymer_class.upper() not in rules.get("classes", {}):
        raise ValueError(f"unknown polymer class {polymer_class!r}")
    cls = get_class_entry(rules, polymer_class)
    decision_evaluations = {
        row["id"]: {
            "default_choice": row["choice"],
            "criteria_evaluated": row["criteria_evaluated"],
            "evidence": row["evidence"],
            "alternatives": row["alternatives"],
        }
        for row in build_decisions(cls)
    }
    return {
        "polymer_class": polymer_class.upper(),
        "properties": sorted(properties),
        "rationale": [],
        "overrides": {},
        "decision_evaluations": decision_evaluations,
        "assumptions": [],
        "dominant_uncertainty": "protocol_transferability",
        "confidence": "unreviewed",
        "provenance": {"generator": "make_decision_scaffold.py",
                       "generated_at": datetime.now(timezone.utc).isoformat()},
    }


def main():
    p = argparse.ArgumentParser(description="Emit a deterministic decision.json scaffold.")
    p.add_argument("--run_name")
    p.add_argument("--polymer_class", required=True)
    p.add_argument("--smiles", default=None,
                   help="Accepted for CLI parity with make_deterministic_plan.py; decision.json "
                        "has no smiles field (that lives in the run's ScientificIntent), so this "
                        "is not used to generate the scaffold's content.")
    p.add_argument("--properties", default="all",
                   help="Comma-separated: density,tg,bulk_modulus or 'all'")
    p.add_argument("--out", default=None,
                   help="Output path; default data/<run_name>/raw/decision.json; '-' = stdout")
    p.add_argument("--force", action="store_true",
                   help="Overwrite an existing decision.json (default: refuse, to protect "
                        "in-progress annotation work)")
    args = p.parse_args()

    if not args.run_name:
        p.error("--run_name is required")

    props_str = args.properties.strip().lower()
    properties = ({"density", "tg", "bulk_modulus"} if props_str == "all"
                  else {x.strip().lower() for x in props_str.split(",") if x.strip()})

    scaffold = make_decision_scaffold(args.polymer_class, properties)
    text = json.dumps(scaffold, indent=2)

    if args.out == "-":
        print(text)
        return
    out_path = (Path(args.out) if args.out
                else REPO_ROOT / "data" / args.run_name / "raw" / "decision.json")
    if out_path.exists() and not args.force:
        print(json.dumps({
            "status": "error",
            "error": f"{out_path} already exists; pass --force to overwrite (this destroys "
                     "any annotation already written)",
        }), file=sys.stderr)
        sys.exit(1)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text)
    print(json.dumps({"status": "success", "decision_file": str(out_path),
                      "decision_ids": sorted(scaffold["decision_evaluations"])}))


if __name__ == "__main__":
    main()
