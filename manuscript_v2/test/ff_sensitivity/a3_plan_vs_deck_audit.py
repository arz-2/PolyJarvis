#!/usr/bin/env python3
"""a3 — does each decided_param actually reach the LAMMPS deck that ran?

`decided_params` is what the manuscript reports as protocol. It is only a description of
the simulation if each value is threaded into the generated input. Two were already known
to drift; this checks every axis that leaves a mechanically detectable footprint in the
decks, by reading the archived .in files rather than the code that wrote them.

Each probe reports (recorded, executed, match). An axis with no detectable footprint is
reported as such -- not silently passed.

Writes results/a3_plan_vs_deck.json and .md.
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


def read(p):
    try:
        return p.read_text(errors="replace")
    except OSError:
        return None


def prod_deck(run):
    return read(DATA / run / "lammps/equil/npt_production/npt_production.in")


def tg_deck(run):
    for p in sorted((DATA / run / "lammps").rglob("tg_sweep*.in")):
        t = read(p)
        if t:
            return t
    return None


def probe_cutoff(dp, deck, _run):
    if deck is None:
        return None
    m = re.search(r"^pair_style\s+(\S+)((?:\s+[\d.]+)+)", deck, re.M)
    if not m:
        return None
    nums = [float(x) for x in m.group(2).split()]
    return {"recorded": dp.get("cutoff_A"), "executed": max(nums) if nums else None,
            "style": m.group(1)}


def probe_timestep(dp, deck, _run):
    if deck is None:
        return None
    m = re.search(r"^timestep\s+([\d.]+)", deck, re.M)
    return {"recorded": dp.get("dt_fs"),
            "executed": float(m.group(1)) if m else None}


def probe_electrostatics(dp, deck, _run):
    if deck is None:
        return None
    has_k = bool(re.search(r"^kspace_style\s+pppm", deck, re.M))
    rec = dp.get("electrostatics")
    return {"recorded": rec, "executed": "pppm" if has_k else "lj_cut",
            "match_override": (rec == "pppm") == has_k}


def probe_tg_step(dp, deck, _run):
    if deck is None:
        return None
    steps = [float(x) for x in re.findall(r"variable\s+t_step\s+equal\s+([\d.]+)", deck)]
    return {"recorded": dp.get("tg_t_step_K"), "executed": steps[0] if steps else None}


def probe_nchain(dp, _deck, run):
    d = read(DATA / run / "lammps/cell/cell.data")
    if d is None:
        return None
    m = re.search(r"^\s*(\d+)\s+atoms", d, re.M)
    return {"recorded": dp.get("nchain"), "executed_atoms": int(m.group(1)) if m else None,
            "note": "atom count is the observable; nchain is not written to the deck"}


# Axes with no mechanically detectable footprint anywhere in the decks.
NO_FOOTPRINT = {
    "eq_annealing_cycles": ("generate_equilibration_workflow has no annealing-cycles "
                            "parameter; the workflow runs one heat/compress/cool pass"),
}

PROBES = {
    "cutoff_A": probe_cutoff,
    "dt_fs": probe_timestep,
    "electrostatics": probe_electrostatics,
    "tg_t_step_K": probe_tg_step,
    "nchain": probe_nchain,
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default=str(OUT))
    args = ap.parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows, drift = [], defaultdict(list)
    for d in sorted(DATA.iterdir()):
        if not (d.is_dir() and RUN_RE.match(d.name)):
            continue
        run = d.name
        pf = d / "raw/run_plan.json"
        if not pf.exists():
            continue
        plan = json.loads(pf.read_text())
        dp = plan.get("decided_params", plan)
        deck, tgd = prod_deck(run), tg_deck(run)
        row = {"run": run, "probes": {}}
        for ax, fn in PROBES.items():
            res = fn(dp, tgd if ax.startswith("tg_") else deck, run)
            if res is None:
                row["probes"][ax] = {"status": "NO_DECK"}
                continue
            if "match_override" in res:
                ok = res.pop("match_override")
            elif "executed" in res and res["executed"] is not None \
                    and res["recorded"] is not None:
                ok = abs(float(res["recorded"]) - float(res["executed"])) < 1e-6
            else:
                ok = None
            res["match"] = ok
            row["probes"][ax] = res
            if ok is False:
                drift[ax].append({"run": run, "recorded": res.get("recorded"),
                                  "executed": res.get("executed")})
        for ax, why in NO_FOOTPRINT.items():
            recorded = dp.get(ax)
            row["probes"][ax] = {"recorded": recorded, "executed": None,
                                 "match": False if recorded not in (None, "null") else None,
                                 "why": why}
            if recorded not in (None, "null"):
                drift[ax].append({"run": run, "recorded": recorded, "executed": None})
        rows.append(row)

    summary = {
        "runs_audited": len(rows),
        "axes_with_drift": sorted(drift),
        "drift_counts": {k: len(v) for k, v in sorted(drift.items())},
        "known_drifts_rediscovered": sorted(
            set(drift) & {"cutoff_A", "eq_annealing_cycles"}),
    }
    (out_dir / "a3_plan_vs_deck.json").write_text(
        json.dumps({"summary": summary, "drift": dict(drift), "runs": rows}, indent=2))

    md = ["# a3 — recorded protocol vs the deck that ran", "",
          f"{summary['runs_audited']} runs audited by reading the archived `.in` files.", "",
          "| axis | runs drifting | recorded -> executed |", "|---|---|---|"]
    for ax, items in sorted(drift.items()):
        ex = items[0]
        md.append(f"| `{ax}` | {len(items)}/{summary['runs_audited']} | "
                  f"{ex['recorded']} -> {ex['executed']} |")
    md += ["", "Axes probed with no drift found: "
               + (", ".join(f"`{a}`" for a in PROBES if a not in drift) or "none") + ".", "",
           "## Notes", ""]
    for ax, why in NO_FOOTPRINT.items():
        md.append(f"- `{ax}`: {why}.")
    md += ["- `cutoff_A` reaches the deck only for TraPPE (`LJ_CUTOFF`); the PCFF and "
           "OPLS pair styles are hardcoded constants in `script_generator.py`, so the "
           "recorded value was decorative for every Class II run.", "",
           "This audit reads decks, not code, so an axis absent here is absent from the "
           "simulation that produced the published number."]
    (out_dir / "a3_plan_vs_deck.md").write_text("\n".join(md) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
