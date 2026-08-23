#!/usr/bin/env python3
"""
check_block_gate.py — Cheap, log-only convergence gate for a single adaptive block.

Used by the NPT-densification (stage 3) and blockwise-cooling (stage 6) adaptive
segments: unlike `check_equilibration_comprehensive.py`, this does not load the
trajectory dump via MDAnalysis — it reads only the LAMMPS thermo log, so it stays cheap
enough to run after every restart-continuation block rather than only post-hoc.

Because each adaptive block is one continuous, restart-extended trajectory (a growing
log, not independently-numbered per-attempt logs — see the "Restart-based continuation"
mechanism in the equilibration-protocol redesign), this script analyses only the most
recent `--window_rows` rows of the log (or the whole log if shorter), and compares the
first half of that window against the second half.

Checks:
  - Density half-window stability   (Δρ/ρ̄ < density_threshold_pct)
  - Non-bonded energy half-window stability (ΔE_nb/|E_nb| < energy_threshold_pct)
  - Monotonic volume trend           (persistent linear trend in Volume -> not converged)

None of these are hard hard-coded to "stage 3" or "stage 6" specifically — they are
generic block-convergence primitives; the caller decides which stage/segment they're
being applied to and what remedy follows a non-stable verdict.

Usage:
    python check_block_gate.py \
        --log_file /path/to/npt_densify.log \
        [--window_rows 200] \
        [--density_col Density] \
        [--nb_energy_cols E_vdwl E_coul E_long] \
        [--volume_col Volume] \
        [--density_threshold_pct 0.5] \
        [--energy_threshold_pct 0.5] \
        [--trend_pvalue 0.05]
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from scipy import stats as sp_stats

from analysis_utils import parse_lammps_log


def half_window_stability(values, threshold_pct):
    """PASS if the relative difference between the window's first-half and
    second-half means is below `threshold_pct`."""
    n = len(values)
    if n < 4:
        return {"available": False, "n_points": n}
    half = n // 2
    first_mean = float(np.mean(values[:half]))
    second_mean = float(np.mean(values[half:]))
    overall_mean = float(np.mean(values))
    rel_diff_pct = (abs(second_mean - first_mean) / abs(overall_mean) * 100
                    if abs(overall_mean) > 1e-12 else 0.0)
    return {
        "available": True,
        "n_points": n,
        "first_half_mean": first_mean,
        "second_half_mean": second_mean,
        "rel_diff_pct": round(rel_diff_pct, 4),
        "threshold_pct": threshold_pct,
        "stable": bool(rel_diff_pct < threshold_pct),
    }


def monotonic_trend(values, p_threshold=0.05, drift_threshold_pct=0.5):
    """A persistent trend requires BOTH statistical significance (p < p_threshold)
    AND a practically meaningful amplitude (total predicted change over the window,
    as a percent of the mean, > drift_threshold_pct) -- mirroring
    check_equilibration_comprehensive._analyse_property's drift test. A p-value alone
    is not enough: a near-noiseless series trips significance on a numerically tiny
    slope just from having many points, which would flag an already-converged plateau
    as still trending.
    """
    n = len(values)
    if n < 4:
        return {"available": False, "n_points": n}
    x = np.arange(n, dtype=float)
    slope, _, _, p_value, _ = sp_stats.linregress(x, values)
    mean_val = float(np.mean(values))
    total_change = abs(slope * n)
    drift_pct = (total_change / abs(mean_val) * 100) if abs(mean_val) > 1e-12 else 0.0
    monotonic = bool(p_value < p_threshold and drift_pct > drift_threshold_pct)
    return {
        "available": True,
        "n_points": n,
        "slope": float(slope),
        "p_value": float(p_value),
        "drift_pct": round(drift_pct, 4),
        "drift_threshold_pct": drift_threshold_pct,
        "monotonic_trend": monotonic,
    }


def check_block_gate(log_file, window_rows=None, density_col="Density",
                     nb_energy_cols=("E_vdwl", "E_coul", "E_long"), volume_col="Volume",
                     density_threshold_pct=0.5, energy_threshold_pct=0.5, trend_pvalue=0.05,
                     volume_drift_threshold_pct=0.5):
    df = parse_lammps_log(log_file)
    n_total = len(df)
    if window_rows is not None and window_rows > 0:
        window = df.iloc[-window_rows:].reset_index(drop=True)
    else:
        window = df

    density_result = {"available": False}
    if density_col in window.columns:
        density_result = half_window_stability(window[density_col].values, density_threshold_pct)

    nb_cols_present = [c for c in nb_energy_cols if c in window.columns]
    energy_result = {"available": False}
    if nb_cols_present:
        nb_energy = window[nb_cols_present].sum(axis=1).values
        energy_result = half_window_stability(nb_energy, energy_threshold_pct)
        energy_result["columns_used"] = nb_cols_present

    volume_trend_result = {"available": False}
    if volume_col in window.columns:
        volume_trend_result = monotonic_trend(window[volume_col].values, trend_pvalue,
                                              volume_drift_threshold_pct)

    stable = (
        density_result.get("stable", True)
        and energy_result.get("stable", True)
        and not volume_trend_result.get("monotonic_trend", False)
    )

    return {
        "status": "success",
        "n_total_rows": n_total,
        "n_window_rows": len(window),
        "density": density_result,
        "nonbonded_energy": energy_result,
        "volume_trend": volume_trend_result,
        "stable": bool(stable),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Cheap log-only block-convergence gate for adaptive densification/cooling blocks."
    )
    parser.add_argument("--log_file", required=True)
    parser.add_argument("--window_rows", type=int, default=None,
                        help="Only analyse the last N thermo rows (the most recent "
                             "restart-continuation block). Omit to use the whole log.")
    parser.add_argument("--density_col", default="Density")
    parser.add_argument("--nb_energy_cols", nargs="+", default=["E_vdwl", "E_coul", "E_long"],
                        help="Non-bonded energy thermo columns, summed. Requires "
                             "`thermo_style custom` to include them explicitly.")
    parser.add_argument("--volume_col", default="Volume")
    parser.add_argument("--density_threshold_pct", type=float, default=0.5)
    parser.add_argument("--energy_threshold_pct", type=float, default=0.5)
    parser.add_argument("--trend_pvalue", type=float, default=0.05)
    parser.add_argument("--volume_drift_threshold_pct", type=float, default=0.5)
    args = parser.parse_args()

    if not Path(args.log_file).exists():
        print(json.dumps({"status": "failed", "error": f"log_file not found: {args.log_file}"}))
        sys.exit(0)

    result = check_block_gate(
        log_file=args.log_file,
        window_rows=args.window_rows,
        density_col=args.density_col,
        nb_energy_cols=tuple(args.nb_energy_cols),
        volume_col=args.volume_col,
        density_threshold_pct=args.density_threshold_pct,
        energy_threshold_pct=args.energy_threshold_pct,
        trend_pvalue=args.trend_pvalue,
        volume_drift_threshold_pct=args.volume_drift_threshold_pct,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
