#!/usr/bin/env python3
"""Benchmark CLI: normalizes both arms' completed output into results.json/results.csv.

Usage:
    python cli.py report --polymer PEG1 --exp-density-g-cm3 1.12

This does not launch either arm (see radonpy_runner.py for the RadonPy driver; the
PolyJarvis arm is launched by running the `novel-run-plan` skill in a Claude Code
session, per polyjarvis_runner.py's docstring). It only reads whatever both arms have
already produced and writes the normalized comparison table.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Optional

from config import DATA_ROOT, REPO_ROOT
from polyjarvis_runner import run_dir_for, campaign_status
from metrics.schema import ArmMetrics
from metrics.accuracy import extract_polyjarvis_accuracy, extract_radonpy_accuracy
from metrics.wall_time import extract_polyjarvis_wall_time, extract_radonpy_wall_time
from metrics.llm_contribution import extract_llm_contribution
from metrics.adaptive_gating import extract_adaptive_gating
from metrics.schema import LLMContributionBlock, HumanInterventionBlock


def build_polyjarvis_metrics(polymer_name: str, exp_density: Optional[float],
                              exp_k_range: Optional[list]) -> ArmMetrics:
    run_dir = run_dir_for(polymer_name)
    accuracy = extract_polyjarvis_accuracy(run_dir, exp_density, exp_k_range)
    wall_time = extract_polyjarvis_wall_time(run_dir)
    llm = extract_llm_contribution(run_dir)
    gating = extract_adaptive_gating(run_dir)

    forcefield = None
    charge_method = None
    run_plan_path = run_dir / "raw" / "run_plan.json"
    if run_plan_path.is_file():
        plan = json.loads(run_plan_path.read_text())
        decided = plan.get("decided_params", {})
        forcefield = decided.get("preferred_ff")
        charge_method = decided.get("charge_method")

    human = HumanInterventionBlock(cap_hit_intervention_needed=gating.cap_hit)

    return ArmMetrics(
        polymer=polymer_name, arm="polyjarvis",
        forcefield=forcefield, charge_method=charge_method,
        accuracy=accuracy, wall_time=wall_time,
        llm_contribution=llm, adaptive_gating=gating, human_intervention=human,
    )


def build_radonpy_metrics(polymer_name: str, exp_density: Optional[float],
                           exp_k_range: Optional[list]) -> ArmMetrics:
    harness_root = DATA_ROOT / polymer_name / "radonpy"
    accuracy = extract_radonpy_accuracy(harness_root, polymer_name, exp_density, exp_k_range)
    wall_time = extract_radonpy_wall_time(harness_root)

    interventions_path = harness_root.parent.parent / "interventions.jsonl"
    n_interventions = 0
    if interventions_path.is_file():
        n_interventions = sum(
            1 for line in interventions_path.read_text().splitlines()
            if json.loads(line).get("polymer") == polymer_name
        )
    human = HumanInterventionBlock(manual_interventions_logged=n_interventions)

    llm = LLMContributionBlock(
        applicable=False,
        note="RadonPy's FF/charge/electrostatics choices are hardcoded sample-script "
             "defaults, never reasoned per polymer -- this axis does not apply to this arm.",
    )

    return ArmMetrics(
        polymer=polymer_name, arm="radonpy",
        forcefield="GAFF2_mod", charge_method="RESP",
        accuracy=accuracy, wall_time=wall_time,
        llm_contribution=llm, human_intervention=human,
    )


def write_report(polymer_name: str, exp_density: Optional[float], exp_k_range: Optional[list]) -> None:
    pj = build_polyjarvis_metrics(polymer_name, exp_density, exp_k_range)
    rp = build_radonpy_metrics(polymer_name, exp_density, exp_k_range)

    out_dir = DATA_ROOT
    out_dir.mkdir(parents=True, exist_ok=True)
    results_path = out_dir / "results.json"

    existing = []
    if results_path.is_file():
        existing = json.loads(results_path.read_text())
        existing = [r for r in existing if r.get("polymer") != polymer_name]
    existing.extend([pj.to_dict(), rp.to_dict()])
    results_path.write_text(json.dumps(existing, indent=2))

    csv_path = out_dir / "results.csv"
    _write_csv(csv_path, existing)

    print(json.dumps({"polyjarvis": pj.to_dict(), "radonpy": rp.to_dict()}, indent=2))


def _flatten(d: dict, prefix: str = "") -> dict:
    flat = {}
    for k, v in d.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            flat.update(_flatten(v, key + "."))
        else:
            flat[key] = v
    return flat


def _write_csv(path: Path, records: list) -> None:
    if not records:
        return
    rows = [_flatten(r) for r in records]
    fieldnames = sorted({k for row in rows for k in row})
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    report = sub.add_parser("report", help="Normalize both arms' output for one polymer")
    report.add_argument("--polymer", required=True)
    report.add_argument("--exp-density-g-cm3", type=float, default=None)
    report.add_argument("--exp-k-min-gpa", type=float, default=None)
    report.add_argument("--exp-k-max-gpa", type=float, default=None)

    status = sub.add_parser("status", help="Print current status of both arms for one polymer")
    status.add_argument("--polymer", required=True)

    args = parser.parse_args()
    if args.command == "report":
        exp_k_range = None
        if args.exp_k_min_gpa is not None and args.exp_k_max_gpa is not None:
            exp_k_range = [args.exp_k_min_gpa, args.exp_k_max_gpa]
        write_report(args.polymer, args.exp_density_g_cm3, exp_k_range)
    elif args.command == "status":
        print(json.dumps(campaign_status(args.polymer), indent=2))


if __name__ == "__main__":
    main()
