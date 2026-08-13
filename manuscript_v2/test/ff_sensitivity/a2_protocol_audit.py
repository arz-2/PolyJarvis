#!/usr/bin/env python3
"""a2 — which protocol axes vary WITHIN each family's replicate set.

The manuscript reports family results as mean +/- SD across 4 replicates. That framing
is only honest if the replicates differ solely by random seed. Reviewer paragraph 4 asks
directly whether protocol variation is being folded into what is presented as stochastic
sampling uncertainty.

This tabulates, per family, every decided_params axis that is NOT constant across its
replicates -- so each reported SD can be labelled as sampling spread, protocol spread,
or a mixture.

Writes results/a2_protocol_audit.json and .md.
"""
import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
DATA = REPO / "manuscript/data"
OUT = Path(__file__).resolve().parent / "results"

RUN_RE = re.compile(r"^(cis-PBD|PEEK|PEG|PMMA|PSU|PVC|PLA|PS|PE)(\d+)$")

# make_deterministic_plan.SNAPSHOT_KEYS plus the three sweep axes the reviewer names.
AXES = [
    "preferred_ff", "preferred_builder", "charge_method", "electrostatics",
    "cutoff_A", "dt_fs", "dp_typical", "nchain", "density_initial_gcm3",
    "T_equil_K", "annealing_T_high_K", "eq_annealing_cycles", "P_equil_atm",
    "t_equil_ns", "npt_prod_ns", "melt_npt_ns",
    "tg_t_high_K", "tg_t_low_K", "tg_t_step_K", "tg_steps_per_t", "tg_rates_K_per_ns",
    "tg_min_steps_per_T", "K_deform_rate_inv_s", "K_strain_max", "bm_pressures_atm",
]


def norm(v):
    return json.dumps(v, sort_keys=True) if isinstance(v, (list, dict)) else v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default=str(OUT))
    args = ap.parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    fams = defaultdict(dict)
    for d in sorted(DATA.iterdir()):
        m = RUN_RE.match(d.name) if d.is_dir() else None
        if not m:
            continue
        p = d / "raw/run_plan.json"
        if not p.exists():
            fams[m.group(1)][d.name] = None
            continue
        plan = json.loads(p.read_text())
        fams[m.group(1)][d.name] = plan.get("decided_params", plan)

    report, total = {}, 0
    for fam, runs in sorted(fams.items()):
        total += len(runs)
        varying, constant, missing = {}, {}, [r for r, v in runs.items() if v is None]
        present = {r: v for r, v in runs.items() if v is not None}
        for ax in AXES:
            vals = {r: norm(v.get(ax)) for r, v in present.items()}
            uniq = set(vals.values())
            if len(uniq) > 1:
                varying[ax] = vals
            elif uniq:
                constant[ax] = next(iter(uniq))
        report[fam] = {"n_runs": len(runs), "n_with_plan": len(present),
                       "runs_without_plan": missing,
                       "varying_axes": sorted(varying), "varying_detail": varying,
                       "n_varying": len(varying)}

    summary = {"families": len(report), "runs_total": total,
               "runs_sum_check": total == 36,
               "families_with_protocol_variation":
                   sorted(f for f, v in report.items() if v["n_varying"] > 0)}
    (out_dir / "a2_protocol_audit.json").write_text(
        json.dumps({"summary": summary, "families": report}, indent=2))

    md = ["# a2 — protocol variation within replicate sets", "",
          f"{summary['runs_total']} runs across {summary['families']} families "
          f"(sums to 36: {summary['runs_sum_check']}).", "",
          "A family with a non-empty list below does **not** have a pure-seed replicate "
          "set: its reported mean +/- SD mixes protocol variation into what is presented "
          "as sampling uncertainty.", "",
          "| family | n | axes varying | which |", "|---|---|---|---|"]
    for fam, v in sorted(report.items()):
        md.append(f"| {fam} | {v['n_runs']} | {v['n_varying']} | "
                  f"{', '.join(v['varying_axes']) or '— (seed-only)'} |")

    md += ["", "## Per-axis detail", ""]
    for fam, v in sorted(report.items()):
        if not v["varying_axes"]:
            continue
        md += [f"### {fam}", ""]
        for ax in v["varying_axes"]:
            vals = ", ".join(f"{r}={val}" for r, val in sorted(v["varying_detail"][ax].items()))
            md.append(f"- `{ax}`: {vals}")
        md.append("")
    (out_dir / "a2_protocol_audit.md").write_text("\n".join(md) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
