#!/usr/bin/env python3
"""Grade one cell against RadonPy's own equilibration criteria. Runs in the `radonpy` env.

Every number comes from RadonPy's code: `Equilibration_analyze` parses the log,
`analyze_thermo` computes each sma_sd with the unit conversions `get_all_prop` uses, `calc_rg`
reads the Rg profile, and every threshold is read off the analyzer's own `*_crit` attributes
rather than copied here. What this adds is bookkeeping `check_eq` does not do:

  * a NaN sma_sd is UNEVALUABLE, not a silent pass (see criteria.radonpy_criterion);
  * each criterion is reported with its value and threshold, not folded into one boolean;
  * `check_eq` itself is still called, and its boolean is recorded next to ours, so any
    disagreement is visible rather than assumed away.

`get_all_prop` is not called: it also computes fluctuation properties (Cp, compressibility)
that require init >= f_width and raise on a short log, and none of them is gated.

Usage (radonpy env):
    python radonpy_grader.py --log eq12.log --width 2000 --out native.json \
        [--tail-rows 2001] [--rg-profile rg.profile] \
        [--stored-conv-csv analyze/eq_conv_data.csv --stored-prop-csv analyze/eq_prop_data.csv]
"""
from __future__ import annotations

import argparse
import contextlib
import csv
import io
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from criteria import UNEVALUABLE, UNMEASURED, combine, radonpy_criterion  # noqa: E402

from radonpy.core import const  # noqa: E402
from radonpy.sim.preset.eq import Equilibration_analyze  # noqa: E402

# (analyzer attribute prefix, log column, conversion, relative?, stored-csv column)
# The conversions are get_all_prop's; relative/absolute mirrors check_eq's comparison per term
# (evdw and ecoul are absolute there, everything else is scaled by |mean|).
THERMO_TERMS = [
    ("totene", "TotEng", const.cal2j, True, "totene_sma_sd"),
    ("kinene", "KinEng", const.cal2j, True, "kinene_sma_sd"),
    ("ebond", "E_bond", const.cal2j, True, "ebond_sma_sd"),
    ("eangle", "E_angle", const.cal2j, True, "eangle_sma_sd"),
    ("edihed", "E_dihed", const.cal2j, True, "edihed_sma_sd"),
    ("evdw", "E_vdwl", const.cal2j, False, "evdw_sma_sd"),
    ("ecoul", "E_coul", const.cal2j, False, "ecoul_sma_sd"),
    ("elong", "E_long", const.cal2j, True, "elong_sma_sd"),
    ("dens", "Density", 1.0, True, "density_sma_sd"),
]


def _last_row(path):
    with open(path) as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        raise ValueError(f"{path} has no rows")
    return rows[-1]


def _num(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) else v


def _log_units(log):
    with open(log) as fh:
        for line in fh:
            if line.startswith("units"):
                return line.split()[1]
    return None


def grade(log, width, tail_rows=None, rg_profile=None, stored_conv_csv=None, stored_prop_csv=None):
    quiet = io.StringIO()
    with contextlib.redirect_stdout(quiet):
        analyzer = Equilibration_analyze(log_file=str(log), rg_file=str(rg_profile or "/nonexistent"))
    if analyzer.dfs is None:
        raise SystemExit(f"RadonPy could not parse {log}")
    rows_in_log = len(analyzer.dfs[-1])
    if tail_rows:
        analyzer.dfs[-1] = analyzer.dfs[-1].iloc[-tail_rows:]
    rows = len(analyzer.dfs[-1])
    units = _log_units(log)
    if units != "real":
        # Every conversion above assumes kcal/mol; evdw's absolute 30.0 bound is in kJ/mol.
        raise SystemExit(f"{log}: units {units!r}, expected 'real'")

    # analyze_thermo's sma_sd is the sd of the last width+1 rolling means; the first rolling mean
    # exists at row width-1, so the window is fully defined only when rows >= 2*width.
    window_ok = rows >= 2 * width
    native_window = tail_rows is None

    stored = _last_row(stored_conv_csv) if stored_conv_csv else None
    criteria, check = {}, []
    for prefix, column, conv, relative, stored_col in THERMO_TERMS:
        crit = getattr(analyzer, f"{prefix}_sma_sd_crit")
        try:
            with contextlib.redirect_stdout(quiet):
                data = analyzer.analyze_thermo(column, conv_a=conv, width=width, init=width)
        except Exception as exc:  # RadonPy raises RadonPyError on an out-of-range init
            data, error = None, f"{type(exc).__name__}: {exc}"
        else:
            error = None
        data = data or {}
        setattr(analyzer, f"{prefix}_data", data)
        entry = radonpy_criterion(_num(data.get("sma_sd")), _num(data.get("mean")), crit, relative)
        if not window_ok and entry["status"] != "NOT_GATED":
            entry["status"] = UNEVALUABLE
            entry["reason"] = f"{rows} rows < 2*width={2 * width}; the rolling window is undefined"
        if error:
            entry["status"], entry["reason"] = UNEVALUABLE, error
        entry.update({"column": column, "mean": _num(data.get("mean")), "crit": crit,
                      "rule": "sma_sd > |mean|*crit" if relative else "sma_sd > crit"})
        if stored and native_window and entry["value"] is not None and _num(stored.get(stored_col)):
            ref = _num(stored[stored_col])
            entry["stored_by_radonpy"] = ref
            entry["reproduces_stored"] = abs(entry["value"] - ref) <= 1e-9 * max(1.0, abs(ref))
        criteria[prefix] = entry
        check.append(entry["status"])

    rg_entry, rg_data = {"status": UNMEASURED}, {}
    if rg_profile:
        with contextlib.redirect_stdout(quiet):
            rg_data = analyzer.calc_rg(rg_file=str(rg_profile), init=-width) or {}
        n_frames = len(analyzer.read_ave(str(rg_profile)).index.unique(level=0)) if rg_data else 0
        rg_entry = radonpy_criterion(_num(rg_data.get("sd_max")), _num(rg_data.get("mean_mean")),
                                     analyzer.rg_sd_crit, True)
        if rg_data and n_frames < width:
            rg_entry["status"] = UNEVALUABLE
            rg_entry["reason"] = f"profile has {n_frames} outputs < width={width}"
        rg_entry.update({"source": "calc_rg on rg.profile", "n_profile_outputs": n_frames,
                         "per_chain_sd": [float(x) for x in rg_data.get("sd", [])],
                         "per_chain_mean": [float(x) for x in rg_data.get("mean", [])]})
    elif stored_conv_csv and stored_prop_csv and native_window and width == 2000:
        prop = _last_row(stored_prop_csv)
        rg_entry = radonpy_criterion(_num(stored.get("Rg_sd_max")), _num(prop.get("Rg")),
                                     analyzer.rg_sd_crit, True)
        rg_entry["source"] = ("stored by RadonPy's own run (eq_conv_data.csv Rg_sd_max, "
                              "eq_prop_data.csv Rg); its rg.profile was not preserved")
    else:
        rg_entry["reason"] = ("no rg.profile, and RadonPy's stored Rg statistic was computed at "
                              "width 2000 on the full log -- it cannot be re-windowed")
    rg_entry.update({"crit": analyzer.rg_sd_crit, "rule": "sd_max > mean_mean*crit"})
    if rg_entry.get("value") is not None and rg_entry.get("threshold"):
        rg_entry["sd_max_over_mean_pct"] = 100.0 * rg_entry["value"] / (rg_entry["threshold"] / analyzer.rg_sd_crit)
    criteria["rg"] = rg_entry
    check.append(rg_entry["status"])

    # RadonPy's own boolean, on the same populated data. It only sees Rg when a profile was read.
    analyzer.rg_data = rg_data
    with contextlib.redirect_stdout(quiet):
        radonpy_check_eq = bool(analyzer.check_eq())
    ours_on_what_check_eq_sees = combine([c["status"] for k, c in criteria.items()
                                          if k != "rg" or rg_profile])

    return {
        "log": str(log), "units": units, "rows_in_log": rows_in_log, "rows_graded": rows,
        "tail_rows": tail_rows, "width": width, "window_fully_defined": window_ok,
        "criteria": criteria,
        "verdict": combine(check),
        "failing": sorted(k for k, c in criteria.items() if c["status"] == "FAIL"),
        "not_evaluated": sorted(k for k, c in criteria.items() if c["status"] in (UNEVALUABLE, UNMEASURED)),
        "radonpy_check_eq_returned": radonpy_check_eq,
        # The fail-open, recorded where it happens: check_eq says converged on a window it could
        # not compute. Only meaningful when nothing we evaluated FAILED.
        "radonpy_check_eq_passes_an_unevaluable_window": bool(
            radonpy_check_eq and ours_on_what_check_eq_sees == "INCOMPLETE"),
        "radonpy_check_eq_agrees": (radonpy_check_eq == (ours_on_what_check_eq_sees == "PASS")
                                    if ours_on_what_check_eq_sees != "INCOMPLETE" else None),
        # The second fail-open: with no readable rg.profile, check_eq prints "Skip to check the
        # Rg convergence" and returns True without it -- the one criterion RadonPy's own PEG1
        # runs failed. True here means check_eq's boolean says nothing about Rg.
        "radonpy_check_eq_skipped_rg": bool(radonpy_check_eq and not rg_data),
        "radonpy_warnings": [l for l in quiet.getvalue().splitlines() if "RadonPy warning" in l],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--log", required=True)
    parser.add_argument("--width", type=int, default=2000)
    parser.add_argument("--tail-rows", type=int, default=None)
    parser.add_argument("--rg-profile", default=None)
    parser.add_argument("--stored-conv-csv", default=None)
    parser.add_argument("--stored-prop-csv", default=None)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    result = grade(args.log, args.width, args.tail_rows, args.rg_profile,
                   args.stored_conv_csv, args.stored_prop_csv)
    Path(args.out).write_text(json.dumps(result, indent=2))
    print(json.dumps({k: result[k] for k in ("verdict", "failing", "not_evaluated",
                                             "radonpy_check_eq_returned")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
