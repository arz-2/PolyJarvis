#!/usr/bin/env python3
"""Cross-grade PEG1: every cell under BOTH codes' convergence criteria. CPU only, no GPU.

    mcp-servers/.venv/bin/python benchmarks/polyjarvis_vs_radonpy/cross_grade/run_cross_grade.py
        [--only PEGCMP1,radonpy_retry9] [--reuse-checker]

For each PolyJarvis cell: rebuild RadonPy's rg.profile from the dump, grade it with RadonPy's
criteria at the native and the matched window, and run PolyJarvis's own checker + gate.
For each RadonPy cell: grade its log with RadonPy's criteria (reproducing its stored numbers
first) and with PolyJarvis's gate from the log and stored Rg.

Writes results/PEG1/<arm>/*.json, results/PEG1/cross_grade.json and cross_grade.md.
See README.md for the reading rule, which was fixed before any result was produced.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
BENCH = HERE.parent
REPO = HERE.parents[2]
sys.path.insert(0, str(BENCH))
sys.path.insert(0, str(HERE))

from config import RADONPY_ENV_PYTHON  # noqa: E402
import rg_profile  # noqa: E402

RESULTS = HERE / "results"
ROUNDTRIP_TOL_A = 1e-5  # the profile is written at 8 decimals


def resolve(path: str) -> Path:
    if path.startswith("repo:"):
        return REPO / path[len("repo:"):]
    if path.startswith("v1:"):
        root = Path(os.environ.get("POLYJARVIS_V1_ROOT", Path.home() / "PolyJarvis"))
        return root / path[len("v1:"):]
    raise ValueError(f"path without a root prefix: {path}")


def _run(cmd: list[str], label: str) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"{label} failed ({proc.returncode}):\n{proc.stdout[-2000:]}\n{proc.stderr[-2000:]}")


def radonpy_grade(out: Path, log: Path, window: dict, **extra) -> dict:
    cmd = [str(RADONPY_ENV_PYTHON), str(HERE / "radonpy_grader.py"), "--log", str(log),
           "--width", str(window["width"]), "--out", str(out)]
    if window.get("tail_rows"):
        cmd += ["--tail-rows", str(window["tail_rows"])]
    for flag, value in extra.items():
        if value is not None:
            cmd += [f"--{flag.replace('_', '-')}", str(value)]
    _run(cmd, f"radonpy_grader {out.name}")
    return json.loads(out.read_text())


def polyjarvis_grade(out: Path, args: list[str]) -> dict:
    _run([sys.executable, str(HERE / "polyjarvis_grader.py"), *args, "--out", str(out)],
         f"polyjarvis_grader {out.parent.name}")
    return json.loads(out.read_text())


def grade_polyjarvis_arm(arm: dict, windows: dict, reuse_checker: bool) -> dict:
    out = RESULTS / "PEG1" / arm["id"]
    out.mkdir(parents=True, exist_ok=True)
    log, dump, data = (resolve(arm[k]) for k in ("log", "dump", "data"))

    profile = out / "rg.profile"
    summary = rg_profile.build_profile(dump, data, profile)
    matrix = summary.pop("matrix")
    (out / "rg_profile_summary.json").write_text(json.dumps(summary, indent=2))

    radonpy = {}
    for name, window in windows.items():
        graded = radonpy_grade(out / f"radonpy_{name}.json", log, window, rg_profile=profile)
        # Round trip: the statistic RadonPy parsed out of our file must equal the one numpy
        # computes on the matrix that wrote it, or the format is wrong and nothing else counts.
        mine = rg_profile.window_stats(matrix, window["width"])
        theirs = graded["criteria"]["rg"]
        if theirs.get("value") is None or abs(theirs["value"] - mine["sd_max"]) > ROUNDTRIP_TOL_A:
            raise SystemExit(f"{arm['id']} {name}: rg.profile round trip failed -- RadonPy read "
                             f"sd_max={theirs.get('value')}, numpy says {mine['sd_max']}")
        graded["rg_roundtrip"] = {"numpy": mine, "abs_diff_A": abs(theirs["value"] - mine["sd_max"])}
        (out / f"radonpy_{name}.json").write_text(json.dumps(graded, indent=2))
        radonpy[name] = graded

    pj_args = ["trajectory", "--log", str(log), "--dump", str(dump), "--data", str(data),
               "--backbone-types", *map(str, arm["backbone_types"]),
               "--cutoff-a", str(arm["cutoff_A"]), "--dp", str(arm["dp"]),
               "--checker-dir", str(out / "checker")]
    if reuse_checker:
        pj_args.append("--reuse")
    polyjarvis = polyjarvis_grade(out / "polyjarvis.json", pj_args)
    return {"arm": arm, "side": "polyjarvis", "radonpy": radonpy, "polyjarvis": polyjarvis,
            "rg_profile": summary}


def _last_row(path: Path) -> dict:
    with open(path) as fh:
        return list(csv.DictReader(fh))[-1]


def grade_radonpy_arm(arm: dict, windows: dict) -> dict:
    out = RESULTS / "PEG1" / arm["id"]
    out.mkdir(parents=True, exist_ok=True)
    log, conv, prop = (resolve(arm[k]) for k in ("log", "stored_conv_csv", "stored_prop_csv"))

    radonpy = {}
    for name, window in windows.items():
        graded = radonpy_grade(out / f"radonpy_{name}.json", log, window,
                               stored_conv_csv=conv, stored_prop_csv=prop)
        if name == "native":
            unmatched = [k for k, c in graded["criteria"].items() if c.get("reproduces_stored") is False]
            if unmatched:
                raise SystemExit(f"{arm['id']}: RadonPy's analyzer did not reproduce its own stored "
                                 f"sma_sd for {unmatched} -- the grader is not grading what RadonPy graded")
        radonpy[name] = graded

    conv_row, prop_row = _last_row(conv), _last_row(prop)
    polyjarvis = polyjarvis_grade(out / "polyjarvis.json", [
        "log-only", "--log", str(log), "--cutoff-a", str(arm["cutoff_A"]),
        "--rg-mean-a", prop_row["Rg"], "--rg-chain-mean-sd-a", conv_row["Rg_mean_sd"]])
    return {"arm": arm, "side": "radonpy", "radonpy": radonpy, "polyjarvis": polyjarvis}


def _fmt_rg(graded: dict) -> str:
    rg = graded["criteria"]["rg"]
    if rg.get("value") is None:
        return rg["status"]
    return f"{rg['status']} ({rg['value']:.3f} vs {rg['threshold']:.3f} Å)"


def _fmt_radonpy(graded: dict) -> str:
    extra = []
    if graded["failing"]:
        extra.append("fails " + ", ".join(graded["failing"]))
    if graded["not_evaluated"]:
        extra.append("not evaluated " + ", ".join(graded["not_evaluated"]))
    return graded["verdict"] + (f" — {'; '.join(extra)}" if extra else "")


def _dihedral(pj: dict) -> str:
    d = (pj.get("energy_component_drift") or {}).get("dihedral") or {}
    if not d:
        return "—"
    return f"{d.get('drift_pct')}% (p_eff {d.get('p_value')}, p_naive {d.get('p_value_naive')})"


def write_table(rows: list[dict], path: Path) -> None:
    lines = [
        "# PEG1 cross-grade", "",
        f"Generated {datetime.now(timezone.utc).isoformat(timespec='seconds')} by `run_cross_grade.py`. "
        "Read with the rule in README.md.", "",
        "| cell | field | chains | RadonPy criteria, native | RadonPy criteria, matched | RadonPy Rg sd_max, matched | PolyJarvis gate (require_rubbery) | dihedral drift |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        arm, pj = r["arm"], r["polyjarvis"]
        pj_text = pj["verdict"]
        if pj["failing_binding"]:
            pj_text += " — fails " + ", ".join(pj["failing_binding"])
        if pj["unmeasured_binding"]:
            pj_text += " — unmeasured " + ", ".join(pj["unmeasured_binding"])
        if pj["component_drift_failing_under_naive_p"]:
            pj_text += " (naive p would fail " + ", ".join(pj["component_drift_failing_under_naive_p"]) + ")"
        lines.append(f"| {arm['id']} ({r['side']}) | {arm['field']} | {arm['nchain']} | "
                     f"{_fmt_radonpy(r['radonpy']['native'])} | {_fmt_radonpy(r['radonpy']['matched'])} | "
                     f"{_fmt_rg(r['radonpy']['matched'])} | {pj_text} | {_dihedral(pj)} |")
    fail_open = [f"{r['arm']['id']} ({w})" for r in rows for w, g in r["radonpy"].items()
                 if g.get("radonpy_check_eq_passes_an_unevaluable_window")]
    skipped_rg = [f"{r['arm']['id']} ({w})" for r in rows for w, g in r["radonpy"].items()
                  if g.get("radonpy_check_eq_skipped_rg")]
    lines += ["", "RadonPy `check_eq` returned True on a window it could not compute: "
              + (", ".join(fail_open) if fail_open else "none"),
              "", "RadonPy `check_eq` returned True with no Rg profile, i.e. without its Rg criterion: "
              + (", ".join(skipped_rg) if skipped_rg else "none"), ""]
    path.write_text("\n".join(lines))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", help="comma-separated arm ids")
    parser.add_argument("--reuse-checker", action="store_true",
                        help="reuse an existing checker equilibration.json instead of re-running it")
    args = parser.parse_args()

    manifest = json.loads((HERE / "arms.json").read_text())
    windows = manifest["windows"]
    wanted = {s.strip() for s in args.only.split(",")} if args.only else None
    known = {a["id"] for a in manifest["radonpy_arms"] + manifest["polyjarvis_arms"]}
    if wanted and wanted - known:
        parser.error(f"unknown arms: {sorted(wanted - known)}")

    rows = []
    for arm in manifest["radonpy_arms"]:
        if not wanted or arm["id"] in wanted:
            print(f"grading {arm['id']} (RadonPy cell)", flush=True)
            rows.append(grade_radonpy_arm(arm, windows))
    for arm in manifest["polyjarvis_arms"]:
        if not wanted or arm["id"] in wanted:
            print(f"grading {arm['id']} (PolyJarvis cell)", flush=True)
            rows.append(grade_polyjarvis_arm(arm, windows, args.reuse_checker))

    out = RESULTS / "PEG1"
    out.mkdir(parents=True, exist_ok=True)
    (out / "cross_grade.json").write_text(json.dumps(
        {"generated_at": datetime.now(timezone.utc).isoformat(), "manifest": manifest, "rows": rows},
        indent=2, default=str))
    write_table(rows, out / "cross_grade.md")
    print((out / "cross_grade.md").read_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
