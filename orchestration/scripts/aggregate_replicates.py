#!/usr/bin/env python3
"""
aggregate_replicates.py — mean +/- SD across a class's completed replicates.

Invoked by the orchestrator (plain Bash, no agent) after the last replicate of a class's
campaign set has a run_summary.json. Reads each replicate's results.{tg,density,bulk_modulus}
and writes a single aggregate JSON with mean/sd/n per property, plus each replicate's raw
value and status for traceability.

Deliberately explicit about which runs to include (--run_names), not a directory glob --
guessing from data/<CLASS>* would risk pulling in stale or unrelated runs of the same class.

Usage:
  python3 orchestration/aggregate_replicates.py --polymer_class PACR \
      --run_names PMMA5,PMMA6,PMMA7,PMMA8 [--out PATH]
"""
import argparse
import json
import statistics
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

PROPERTIES = {
    "tg": "value_K",
    "density": "value_g_cm3",
    "bulk_modulus": "value_GPa",
}


def _run_summary_path(run_name: str) -> Path:
    """Same manuscript/data -> data fallback enforce_gate.py uses."""
    p = REPO_ROOT / "manuscript" / "data" / run_name / "raw" / "run_summary.json"
    if p.exists():
        return p
    return REPO_ROOT / "data" / run_name / "raw" / "run_summary.json"


def aggregate(polymer_class: str, run_names: list) -> dict:
    per_property = {prop: {"values": [], "runs_with_value": [], "runs_missing": [],
                            "statuses": {}} for prop in PROPERTIES}
    exp_ranges = {prop: None for prop in PROPERTIES}
    exp_range_conflicts = {prop: [] for prop in PROPERTIES}
    runs_missing_summary = []

    for run_name in run_names:
        path = _run_summary_path(run_name)
        if not path.exists():
            runs_missing_summary.append(run_name)
            continue
        summary = json.loads(path.read_text())
        results = summary.get("results", {})
        for prop, value_key in PROPERTIES.items():
            block = results.get(prop)
            if not block or block.get(value_key) is None:
                per_property[prop]["runs_missing"].append(run_name)
                continue
            val = block[value_key]
            per_property[prop]["values"].append(val)
            per_property[prop]["runs_with_value"].append({"run": run_name, "value": val,
                                                            "status": block.get("status")})
            status = block.get("status", "UNKNOWN")
            per_property[prop]["statuses"][status] = per_property[prop]["statuses"].get(status, 0) + 1

            exp_range = block.get("exp_range_K") or block.get("exp_range_g_cm3") or block.get("exp_range_GPa")
            if exp_range is not None:
                if exp_ranges[prop] is None:
                    exp_ranges[prop] = exp_range
                elif exp_ranges[prop] != exp_range:
                    exp_range_conflicts[prop].append({"run": run_name, "exp_range": exp_range})

    aggregated = {}
    for prop in PROPERTIES:
        vals = per_property[prop]["values"]
        n = len(vals)
        mean = statistics.fmean(vals) if n else None
        sd = statistics.stdev(vals) if n >= 2 else None
        aggregated[prop] = {
            "n": n,
            "mean": mean,
            "sd": sd,
            "sd_note": None if n >= 2 else ("insufficient replicates for SD (n<2)" if n else "no valid values"),
            "replicates": per_property[prop]["runs_with_value"],
            "runs_missing_value": per_property[prop]["runs_missing"],
            "status_counts": per_property[prop]["statuses"],
            "exp_range": exp_ranges[prop],
            "exp_range_conflicts": exp_range_conflicts[prop] or None,
        }

    return {
        "polymer_class": polymer_class.upper(),
        "run_names": run_names,
        "runs_missing_run_summary": runs_missing_summary,
        "n_replicates_requested": len(run_names),
        "n_replicates_found": len(run_names) - len(runs_missing_summary),
        "results": aggregated,
    }


def main():
    p = argparse.ArgumentParser(description="Aggregate mean/SD across a class's replicates.")
    p.add_argument("--polymer_class", required=True)
    p.add_argument("--run_names", required=True,
                   help="Comma-separated replicate run names, e.g. PMMA5,PMMA6,PMMA7,PMMA8")
    p.add_argument("--out", default=None,
                   help="Output path; default data/<CLASS>_campaign_summary.json")
    args = p.parse_args()

    run_names = [r.strip() for r in args.run_names.split(",") if r.strip()]
    result = aggregate(args.polymer_class, run_names)

    out_path = (Path(args.out) if args.out
                else REPO_ROOT / "data" / f"{args.polymer_class.upper()}_campaign_summary.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"status": "success", "out_path": str(out_path),
                      "n_replicates_found": result["n_replicates_found"],
                      "n_replicates_requested": result["n_replicates_requested"]}))


if __name__ == "__main__":
    main()
