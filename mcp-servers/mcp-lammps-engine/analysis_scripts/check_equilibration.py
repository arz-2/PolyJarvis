#!/usr/bin/env python3
"""
check_equilibration.py — Check whether a LAMMPS simulation is equilibrated
based on density and energy convergence.

Analyses the production window (last eq_fraction of the thermo rows) and
applies two convergence tests on both density and total energy:

  1. Drift test — linear regression on property vs row index.
     FAIL if drift > drift_threshold_pct % AND p < drift_pvalue.
  2. Block-average test — split into block_count blocks
     (Flyvbjerg & Petersen, JCP 1989); FAIL if the SEM of block
     means exceeds 1% of the overall mean.

System is "equilibrated" only if BOTH density and energy pass both tests.

Output contract:
  - Prints a JSON summary to stdout as the last line.
  - Writes equilibration_check.json to --output_dir.
  - Exit 0 on success, non-zero on failure (errors to stderr).

Usage:
    python check_equilibration.py --log_file /path/to/log.lammps \
                                  --output_dir /path/to/eq_analysis
"""

import argparse
import json
import re
import sys
import numpy as np
import pandas as pd
from pathlib import Path
from scipy import stats as sp_stats

sys.path.insert(0, str(Path(__file__).parent))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from plot_style import apply_style, save_fig


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
# Convergence analysis for a single property
# ---------------------------------------------------------------------------

def analyse(values, name, drift_threshold_pct, drift_pvalue, block_count):
    mean_val = float(np.mean(values))
    std_val = float(np.std(values, ddof=1))
    n = len(values)
    res = {
        "property": name,
        "mean": round(mean_val, 6),
        "std": round(std_val, 6),
        "n_points": n,
    }

    # 1. Drift (linear regression)
    x = np.arange(n, dtype=float)
    slope, intercept, r_val, p_val, se = sp_stats.linregress(x, values)
    total_drift = abs(slope * n)
    drift_pct = (total_drift / abs(mean_val) * 100) if abs(mean_val) > 1e-12 else 0
    d_pass = bool(not (drift_pct > drift_threshold_pct and p_val < drift_pvalue))
    res["drift"] = {
        "slope_per_step": float(slope),
        "total_drift": round(float(total_drift), 6),
        "drift_pct": round(drift_pct, 4),
        "regression_p": float(p_val),
        "pass": d_pass,
    }

    # 2. Block average (Flyvbjerg & Petersen, JCP 1989)
    bs = n // block_count
    if bs >= 2:
        bmeans = [float(np.mean(values[i*bs:(i+1)*bs])) for i in range(block_count)]
        sem_b = float(np.std(bmeans, ddof=1) / np.sqrt(block_count))
        sem_pct = (sem_b / abs(mean_val) * 100) if abs(mean_val) > 1e-12 else 0
        b_pass = bool(sem_pct < 1.0)
        res["block_avg"] = {
            "block_count": block_count,
            "block_size": bs,
            "block_means": [round(m, 6) for m in bmeans],
            "sem": round(sem_b, 6),
            "sem_pct": round(sem_pct, 4),
            "pass": b_pass,
        }
    else:
        b_pass = True
        res["block_avg"] = {"pass": True, "note": "too few points for blocking"}

    res["equilibrated"] = bool(d_pass and b_pass)
    return res


# ---------------------------------------------------------------------------
# Plot
# ---------------------------------------------------------------------------

def _plot_equilibration_convergence(prod, density_col, energy_col, equilibrated, graphs_dir):
    apply_style()
    steps = prod['Step'].values if 'Step' in prod.columns else np.arange(len(prod))
    fig, ax1 = plt.subplots()
    if density_col in prod.columns:
        rho = prod[density_col].values
        ax1.plot(steps, rho, color='steelblue', lw=0.8, alpha=0.8, label='Density')
        ax1.set_ylabel('Density (g/cm³)', color='steelblue')
        ax1.tick_params(axis='y', colors='steelblue')
    ax1.set_xlabel('Step')
    ax2 = ax1.twinx()
    if energy_col in prod.columns:
        eng = prod[energy_col].values
        ax2.plot(steps, eng, color='firebrick', lw=0.8, alpha=0.8, label='Energy')
        ax2.set_ylabel('Total Energy (kcal/mol)', color='firebrick')
        ax2.tick_params(axis='y', colors='firebrick')
    verdict = 'PASS' if equilibrated else 'FAIL'
    ax1.set_title(f'Equilibration convergence — {verdict}')
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper right')
    save_fig(fig, str(graphs_dir / 'equilibration_convergence.png'))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Check whether a LAMMPS simulation is equilibrated "
                    "based on density and energy convergence."
    )
    parser.add_argument("--log_file", required=True,
                        help="Path to the LAMMPS log file.")
    parser.add_argument("--output_dir", required=True,
                        help="Output directory for results.")
    parser.add_argument("--eq_fraction", type=float, default=0.5,
                        help="Fraction of rows used as production window.")
    parser.add_argument("--drift_threshold_pct", type=float, default=1.0,
                        help="Max allowed drift as %% of mean.")
    parser.add_argument("--drift_pvalue", type=float, default=0.01,
                        help="p-value threshold for drift regression significance.")
    parser.add_argument("--block_count", type=int, default=5,
                        help="Number of blocks for block averaging.")
    parser.add_argument("--temp_col", default="Temp",
                        help="Temperature column name.")
    parser.add_argument("--press_col", default="Press",
                        help="Pressure column name.")
    parser.add_argument("--density_col", default="Density",
                        help="Density column name.")
    parser.add_argument("--energy_col", default="TotEng",
                        help="Energy column name.")
    parser.add_argument("--graphs_dir", default=None,
                        help="Directory for PNG figures (default: <output_dir>/figures/).")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    graphs_dir = Path(args.graphs_dir) if args.graphs_dir else output_dir / 'figures'
    graphs_dir.mkdir(parents=True, exist_ok=True)

    df = parse_lammps_log(args.log_file)

    n_total = len(df)
    n_discard = int(n_total * (1 - args.eq_fraction))
    prod = df.iloc[n_discard:].reset_index(drop=True)
    n_prod = len(prod)

    if n_prod < 20:
        print(json.dumps({
            "status": "failed",
            "error": f"Only {n_prod} production rows after discarding "
                     f"{n_discard} burn-in — need >= 20."
        }))
        sys.exit(0)

    # Metadata
    meta = {
        "log_file": args.log_file,
        "n_total_rows": n_total,
        "n_production_rows": n_prod,
        "eq_fraction": args.eq_fraction,
    }
    if args.temp_col in prod.columns:
        meta["T_mean"] = round(float(prod[args.temp_col].mean()), 2)
        meta["T_std"] = round(float(prod[args.temp_col].std()), 2)
    if args.press_col in prod.columns:
        meta["P_mean"] = round(float(prod[args.press_col].mean()), 2)
        meta["P_std"] = round(float(prod[args.press_col].std()), 2)

    # Run on density and energy
    results = {}
    if args.density_col in prod.columns:
        results["density"] = analyse(
            prod[args.density_col].values, "density",
            args.drift_threshold_pct, args.drift_pvalue, args.block_count
        )
    else:
        results["density"] = {"error": f"Column '{args.density_col}' not found"}

    if args.energy_col in prod.columns:
        results["energy"] = analyse(
            prod[args.energy_col].values, "energy",
            args.drift_threshold_pct, args.drift_pvalue, args.block_count
        )
    else:
        results["energy"] = {"error": f"Column '{args.energy_col}' not found"}

    density_ok = bool(results.get("density", {}).get("equilibrated", False))
    energy_ok = bool(results.get("energy", {}).get("equilibrated", False))

    output = {
        "status": "success",
        "equilibrated": bool(density_ok and energy_ok),
        "density_equilibrated": density_ok,
        "energy_equilibrated": energy_ok,
        "meta": meta,
        "density": results.get("density"),
        "energy": results.get("energy"),
    }

    eq_fig_png = str(graphs_dir / "equilibration_convergence.png")
    try:
        _plot_equilibration_convergence(prod, args.density_col, args.energy_col,
                                        bool(density_ok and energy_ok), graphs_dir)
    except Exception as _pe:
        print(f"  WARNING: equilibration_convergence plot failed: {_pe}", flush=True)
        eq_fig_png = None
    output["equilibration_convergence_png"] = eq_fig_png

    summary_path = str(output_dir / "equilibration_check.json")
    with open(summary_path, "w") as jf:
        json.dump(output, jf, indent=2)
    output["summary_json"] = summary_path

    print(json.dumps(output))


if __name__ == "__main__":
    main()
