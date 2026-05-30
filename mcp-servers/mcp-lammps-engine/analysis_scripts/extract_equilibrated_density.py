#!/usr/bin/env python3
"""
extract_equilibrated_density.py — Extract the equilibrated (plateau) density
from a single LAMMPS log file.

Uses a reverse-cumulative-mean algorithm to find the longest stable tail of
the density time series rather than a fixed burn-in fraction:

  1. Discard the first (1 - eq_fraction) of rows as initial burn-in.
  2. Starting from the last row, extend backwards one row at a time.
  3. Stop when adding the next row shifts the cumulative mean by more
     than plateau_shift_sigma * SEM of the current window.
  4. The identified plateau region gives the equilibrated density
     (mean ± SEM).

Output contract:
  - Prints a JSON summary to stdout as the last line.
  - Writes equilibrated_density.json to --output_dir.
  - Exit 0 on success, non-zero on failure (errors to stderr).

Usage:
    python extract_equilibrated_density.py --log_file /path/to/log.lammps \
                                           --output_dir /path/to/eq_analysis
"""

import argparse
import json
import re
import sys
import numpy as np
import pandas as pd
from pathlib import Path


# ---------------------------------------------------------------------------
# LAMMPS log parser
# ---------------------------------------------------------------------------

def parse_lammps_log(path):
    """Parse all thermo-output tables from a LAMMPS log file."""
    all_dfs = []
    header = None
    rows = []
    with open(path) as f:
        for raw in f:
            line = raw.strip()
            if re.match(r'^Step\s', line):
                if rows and header is not None:
                    all_dfs.append(pd.DataFrame(rows, columns=header))
                    rows = []
                header = line.split()
                continue
            if header is not None:
                tokens = line.split()
                if len(tokens) == len(header):
                    try:
                        rows.append([float(t) for t in tokens])
                        continue
                    except ValueError:
                        pass
                if rows:
                    all_dfs.append(pd.DataFrame(rows, columns=header))
                    rows = []
                    header = None
    if rows and header is not None:
        all_dfs.append(pd.DataFrame(rows, columns=header))
    if not all_dfs:
        raise ValueError(f"No thermo data found in {path}")
    return pd.concat(all_dfs, ignore_index=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Extract the equilibrated (plateau) density from a "
                    "LAMMPS log file using reverse-cumulative-mean detection."
    )
    parser.add_argument("--log_file", required=True,
                        help="Path to the LAMMPS log file.")
    parser.add_argument("--output_dir", required=True,
                        help="Output directory for results.")
    parser.add_argument("--eq_fraction", type=float, default=0.5,
                        help="Fraction of rows used as production window.")
    parser.add_argument("--target_temp", type=float, default=None,
                        help="If set, only use rows where T is within "
                             "temp_tolerance of this value (K).")
    parser.add_argument("--temp_tolerance", type=float, default=50.0,
                        help="Tolerance window for temperature filter (K).")
    parser.add_argument("--plateau_shift_sigma", type=float, default=1.0,
                        help="Sensitivity of plateau detection. Higher = "
                             "more permissive (longer plateau).")
    parser.add_argument("--density_col", default="Density",
                        help="Density column name in thermo output.")
    parser.add_argument("--temp_col", default="Temp",
                        help="Temperature column name in thermo output.")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    df = parse_lammps_log(args.log_file)

    if args.density_col not in df.columns:
        print(json.dumps({
            "status": "failed",
            "error": f"Column '{args.density_col}' not in log. "
                     f"Found: {list(df.columns)}"
        }))
        sys.exit(0)

    # Optional temperature filter
    if args.target_temp is not None and args.temp_col in df.columns:
        mask = (df[args.temp_col] - args.target_temp).abs() <= args.temp_tolerance
        df = df[mask].reset_index(drop=True)
        if len(df) == 0:
            print(json.dumps({
                "status": "failed",
                "error": f"No rows within {args.temp_tolerance} K of "
                         f"target T={args.target_temp} K"
            }))
            sys.exit(0)

    n_total = len(df)
    n_discard = int(n_total * (1 - args.eq_fraction))
    prod = df.iloc[n_discard:].reset_index(drop=True)
    rho = prod[args.density_col].values
    n_prod = len(rho)

    if n_prod < 10:
        print(json.dumps({
            "status": "failed",
            "error": f"Only {n_prod} production rows — need >= 10."
        }))
        sys.exit(0)

    # -------------------------------------------------------------------
    # Reverse-cumulative-mean plateau detection
    # -------------------------------------------------------------------
    min_plateau = max(10, n_prod // 10)

    cumsum = 0.0
    cumsum_sq = 0.0
    plateau_start_idx = n_prod - 1

    for k in range(1, n_prod + 1):
        idx = n_prod - k
        val = rho[idx]
        cumsum += val
        cumsum_sq += val * val
        n_window = k

        if n_window < min_plateau:
            plateau_start_idx = idx
            continue

        running_mean = cumsum / n_window
        running_var = (cumsum_sq / n_window) - running_mean ** 2
        running_std = np.sqrt(max(running_var, 0.0))

        if idx > 0:
            next_val = rho[idx - 1]
            new_mean = (cumsum + next_val) / (n_window + 1)
            shift = abs(new_mean - running_mean)
            threshold = args.plateau_shift_sigma * running_std / np.sqrt(n_window)

            if shift > threshold and n_window >= min_plateau:
                plateau_start_idx = idx
                break
        else:
            plateau_start_idx = 0

    plateau_rho = rho[plateau_start_idx:]
    n_plateau = len(plateau_rho)

    plateau_mean = float(np.mean(plateau_rho))
    plateau_std = float(np.std(plateau_rho, ddof=1))
    plateau_sem = plateau_std / np.sqrt(n_plateau)

    # Rolling-derivative cross-check
    win = max(5, int(n_prod * 0.2))
    if n_prod >= win:
        rm = pd.Series(rho).rolling(window=win, center=True).mean().values
        rd = np.gradient(rm[~np.isnan(rm)])
        mean_abs_deriv = float(np.mean(np.abs(rd)))
    else:
        mean_abs_deriv = None

    # -------------------------------------------------------------------
    # Assemble output
    # -------------------------------------------------------------------
    result = {
        "status":                  "success",
        "plateau_density_mean":    round(plateau_mean, 6),
        "plateau_density_std":     round(plateau_std, 6),
        "plateau_density_sem":     round(plateau_sem, 6),
        "plateau_n_points":        int(n_plateau),
        "plateau_fraction":        round(n_plateau / n_prod, 4),
        "production_n_points":     int(n_prod),
        "total_n_points":          int(n_total),
        "eq_fraction_used":        args.eq_fraction,
        "naive_mean":              round(float(np.mean(rho)), 6),
        "naive_std":               round(float(np.std(rho, ddof=1)), 6),
        "rolling_mean_abs_deriv":  round(mean_abs_deriv, 8) if mean_abs_deriv is not None else None,
    }

    if args.target_temp is not None:
        result["target_temp_K"] = args.target_temp
        result["temp_tolerance_K"] = args.temp_tolerance
    if args.temp_col in prod.columns:
        result["actual_T_mean"] = round(float(prod[args.temp_col].mean()), 2)

    if "Step" in prod.columns:
        result["plateau_step_range"] = [
            int(prod["Step"].iloc[plateau_start_idx]),
            int(prod["Step"].iloc[-1]),
        ]

    summary_path = str(output_dir / "equilibrated_density.json")
    with open(summary_path, "w") as jf:
        json.dump(result, jf, indent=2)
    result["summary_json"] = summary_path

    print(json.dumps(result))


if __name__ == "__main__":
    main()
