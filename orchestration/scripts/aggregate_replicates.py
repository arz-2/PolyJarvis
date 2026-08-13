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


# Replicate spread is the only check that sees a run which passed every per-run gate yet
# disagrees with its siblings -- e.g. cis-PBD3's K is 16.3% below its family mean with
# r_squared=0.9985 and no admissibility violation. Per-run fit statistics are blind to it.
#
# Deviation is measured in LEAVE-ONE-OUT SDs, not pooled SDs. A pooled-SD rule is
# unsatisfiable at small n: the largest deviation any single point can have is (n-1)/sqrt(n)
# pooled SDs, which is 1.5 at n=4 -- so a "beyond 2 SD" rule can never fire on a 4-replicate
# family, because the outlier inflates the very SD it is compared against. Excluding the
# candidate first gives cis-PBD3 16.0 LOO-SD while every other archived family's worst point
# sits at 2.1-3.4.
#
# Both conditions must hold. LOO-SD alone would flag a trivially small deviation whenever the
# remaining replicates happen to agree very tightly (PVC3: 2.7 LOO-SD on a 3.0% deviation),
# and a percentage alone would flag ordinary replicate scatter (PS4 at 15.3%, PLA3 at 13.7%).
OUTLIER_LOO_SD = 4.0
OUTLIER_MIN_DEVIATION_PCT = 10.0
MIN_REPLICATES_REPORTABLE = 3


def _dispersion(replicates: list, mean, sd):
    """Flag replicates far from the mean of the OTHERS; report the worst deviation."""
    if mean is None or not replicates or abs(mean) < 1e-12:
        return [], None
    max_pct = max(abs(r["value"] - mean) / abs(mean) * 100 for r in replicates)
    outliers = []
    if len(replicates) >= 4:
        for i, r in enumerate(replicates):
            others = [o["value"] for j, o in enumerate(replicates) if j != i]
            o_mean = statistics.fmean(others)
            o_sd = statistics.stdev(others) if len(others) >= 2 else 0.0
            if o_sd <= 0 or abs(o_mean) < 1e-12:
                continue
            loo_sd = abs(r["value"] - o_mean) / o_sd
            dev_pct = abs(r["value"] - o_mean) / abs(o_mean) * 100
            if loo_sd > OUTLIER_LOO_SD and dev_pct > OUTLIER_MIN_DEVIATION_PCT:
                outliers.append({
                    "run": r["run"],
                    "value": r["value"],
                    "others_mean": round(o_mean, 4),
                    "deviation_pct": round(dev_pct, 2),
                    "loo_sd": round(loo_sd, 2),
                })
    return outliers, round(max_pct, 2)


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
        outliers, dispersion_pct = _dispersion(per_property[prop]["runs_with_value"], mean, sd)
        aggregated[prop] = {
            "n": n,
            "mean": mean,
            "sd": sd,
            "sd_note": None if n >= 2 else ("insufficient replicates for SD (n<2)" if n else "no valid values"),
            "max_deviation_pct": dispersion_pct,
            "dispersion_outliers": outliers or None,
            "reportable": n >= MIN_REPLICATES_REPORTABLE,
            "reportable_note": (
                None if n >= MIN_REPLICATES_REPORTABLE
                else f"only {n} replicate(s) with a value; need >={MIN_REPLICATES_REPORTABLE}"
            ),
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
