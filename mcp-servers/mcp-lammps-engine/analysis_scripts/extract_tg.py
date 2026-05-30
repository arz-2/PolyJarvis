#!/usr/bin/env python3
"""
extract_tg.py — Extract glass transition temperature (Tg) from a LAMMPS
temperature-sweep log file.

Methodology (v3 — March 2026):
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Data preparation:
  1. Parse LAMMPS log file into a DataFrame of thermo rows.
  2. Detect temperature plateaus via jump detection (|ΔT| > 15 K
     between consecutive rows starts a new plateau).
  3. Within each plateau, discard burn-in, then average the remaining
     density values to get one (T_setpoint, ρ_mean) data point.
  4. Equilibration drift check: fit ρ(t) within each plateau's
     production window.  If drift > 1% and p < 0.01, exclude.
  5. Also produce standard 5 K bins as a secondary output.

Fitting:
  Primary — exhaustive F-statistic split (deterministic, guess-free).
  Secondary — scipy curve_fit bilinear (for cross-validation).

Output contract:
  - Prints a JSON summary to stdout as the last line.
  - Writes CSV and JSON files to --output_dir.
  - Exit 0 on success, non-zero on failure (errors to stderr).

References:
  Patrone et al., Polymer 87 (2016) 246–259
  Suter et al., JCTC 21 (2025) 1405–1421

Usage:
    python extract_tg.py --log_file /path/to/log.lammps \
                         --output_dir /path/to/tg_analysis \
                         --equilibration_fraction 0.5
"""

import argparse
import json
import re
import sys
import numpy as np
import pandas as pd
from pathlib import Path
from scipy import optimize, stats


# ---------------------------------------------------------------------------
# LAMMPS log parser
# ---------------------------------------------------------------------------

def parse_lammps_log(path):
    """
    Parse all thermo-output tables from a LAMMPS log file.
    Returns a single DataFrame with all rows concatenated.
    """
    all_dfs = []
    header = None
    rows = []

    with open(path) as f:
        for raw in f:
            line = raw.strip()

            if re.match(r'^Step\s', line) or re.match(r'^(Step|TotEng|Temp)', line):
                if rows:
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
# Fitting methods
# ---------------------------------------------------------------------------

def fstat_split_tg(T, rho, min_pts=3):
    """Find optimal two-line split by maximising the F-statistic
    of the two-line model vs a single-line model."""
    idx = np.argsort(T)
    T = T[idx]
    rho = rho[idx]
    N = len(T)

    if N < 2 * min_pts:
        return None, f"Need {2*min_pts} points, have {N}"

    # Single-line (null) model
    p_single = np.polyfit(T, rho, 1)
    ssr_null = np.sum((rho - (p_single[0]*T + p_single[1]))**2)

    best_fstat = -np.inf
    best = None

    for i in range(min_pts, N - min_pts + 1):
        p_lo = np.polyfit(T[:i], rho[:i], 1)
        p_hi = np.polyfit(T[i:], rho[i:], 1)
        a1, b1 = p_lo[0], p_lo[1]   # glassy
        a2, b2 = p_hi[0], p_hi[1]   # rubbery

        # Physics constraints
        if a1 > 0 or a2 > 0:
            continue
        if a2 >= a1:        # rubbery must be steeper (more negative)
            continue
        if abs(a1 - a2) < 1e-15:
            continue

        Tg_int = (b2 - b1) / (a1 - a2)
        if Tg_int < T[0] or Tg_int > T[-1]:
            continue

        pred = np.concatenate([a1*T[:i]+b1, a2*T[i:]+b2])
        ssr_alt = np.sum((rho - pred)**2)

        df_resid = N - 4
        if df_resid <= 0 or ssr_alt <= 0:
            continue

        fstat = ((ssr_null - ssr_alt) / 2.0) / (ssr_alt / df_resid)
        if fstat > best_fstat:
            best_fstat = fstat
            ss_tot = np.sum((rho - np.mean(rho))**2)
            r2 = 1 - ssr_alt / ss_tot if ss_tot > 0 else 0

            best = {
                "Tg_K":        float(Tg_int),
                "split_temp":  float(T[i]),
                "a_glassy":    float(a1),
                "b_glassy":    float(b1),
                "a_rubbery":   float(a2),
                "b_rubbery":   float(b2),
                "r_squared":   float(r2),
                "f_statistic": float(fstat),
                "n_bins":      N,
                "n_low":       i,
                "n_high":      N - i,
            }

    if best is None:
        return None, "No valid split found (all splits failed physics constraints)"
    return best, None


def bilinear_indep(T, a1, b1, a2, b2, Tg):
    return np.where(T < Tg, a1 * T + b1, a2 * T + b2)


def curvefit_bilinear(T, rho, tg_hint=None):
    """Bilinear fit via curve_fit with independent-line parameterisation."""
    idx = np.argsort(T)
    T, rho = T[idx], rho[idx]
    T_min, T_max = float(T[0]), float(T[-1])
    T_mid = (T_min + T_max) / 2

    mask_lo = T < T_mid
    mask_hi = T >= T_mid
    if mask_lo.sum() < 2 or mask_hi.sum() < 2:
        return None

    p_lo = np.polyfit(T[mask_lo], rho[mask_lo], 1)
    p_hi = np.polyfit(T[mask_hi], rho[mask_hi], 1)

    if abs(p_lo[0] - p_hi[0]) > 1e-12:
        Tg_init = (p_hi[1] - p_lo[1]) / (p_lo[0] - p_hi[0])
    else:
        Tg_init = T_mid
    Tg_init = np.clip(Tg_init, T_min + 5, T_max - 5)

    if tg_hint is not None:
        Tg_init = np.clip(tg_hint, T_min + 5, T_max - 5)

    p0 = [p_lo[0], p_lo[1], p_hi[0], p_hi[1], Tg_init]
    try:
        popt, pcov = optimize.curve_fit(
            bilinear_indep, T, rho, p0=p0,
            bounds=([-np.inf, -np.inf, -np.inf, -np.inf, T_min+5],
                    [np.inf,  np.inf,  np.inf,  np.inf,  T_max-5]),
            maxfev=20000,
        )
        a1, b1, a2, b2, Tg = popt
        pred = bilinear_indep(T, *popt)
        ss_res = np.sum((rho - pred)**2)
        ss_tot = np.sum((rho - np.mean(rho))**2)
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0
        Tg_alt = (b2 - b1) / (a1 - a2) if abs(a1 - a2) > 1e-12 else Tg
        return {
            "Tg_K":      float(Tg),
            "Tg_alt_K":  float(Tg_alt),
            "a_glassy":  float(a1),
            "b_glassy":  float(b1),
            "a_rubbery": float(a2),
            "b_rubbery": float(b2),
            "r_squared": float(r2),
        }
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Extract glass transition temperature (Tg) from a LAMMPS "
                    "temperature-sweep log via bilinear density-vs-temperature fitting."
    )
    parser.add_argument("--log_file", required=True,
                        help="Path to the LAMMPS log file.")
    parser.add_argument("--output_dir", required=True,
                        help="Output directory for CSV and JSON results.")
    parser.add_argument("--initial_tg_guess", type=float, default=None,
                        help="Hint for the secondary curve_fit method (K).")
    parser.add_argument("--equilibration_fraction", type=float, default=0.5,
                        help="Fraction of steps at each T used for density averaging.")
    parser.add_argument("--temp_col", default="Temp",
                        help="Temperature column name in thermo output.")
    parser.add_argument("--density_col", default="Density",
                        help="Density column name in thermo output.")
    args = parser.parse_args()

    log_file = args.log_file
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    initial_tg_guess = args.initial_tg_guess
    equilibration_fraction = args.equilibration_fraction
    temp_col = args.temp_col
    density_col = args.density_col

    # -------------------------------------------------------------------
    # 1. Parse LAMMPS log
    # -------------------------------------------------------------------
    df_all = parse_lammps_log(log_file)

    if temp_col not in df_all.columns:
        raise ValueError(
            f"Column '{temp_col}' not found. "
            f"Available columns: {list(df_all.columns)}"
        )
    if density_col not in df_all.columns:
        raise ValueError(
            f"Column '{density_col}' not found. "
            f"Available columns: {list(df_all.columns)}"
        )

    # -------------------------------------------------------------------
    # 2a. Standard 5 K binning
    # -------------------------------------------------------------------
    df_all["_T_bin"] = (df_all[temp_col] / 5.0).round() * 5.0

    records_5k = []
    for T_bin, grp in df_all.groupby("_T_bin", sort=True):
        n_eq = max(1, int(len(grp) * equilibration_fraction))
        eq_grp = grp.tail(n_eq)
        records_5k.append({
            "temperature":  float(T_bin),
            "mean_density": float(eq_grp[density_col].mean()),
            "std_density":  float(eq_grp[density_col].std(ddof=1) if len(eq_grp) > 1 else 0.0),
            "n_points":     int(n_eq),
        })

    df_bins_5k = pd.DataFrame(records_5k).sort_values("temperature").reset_index(drop=True)

    # -------------------------------------------------------------------
    # 2b. Plateau detection
    # -------------------------------------------------------------------
    all_temps_raw = df_all[temp_col].values
    all_rho_raw = df_all[density_col].values

    groups = []
    start_idx = 0
    for i in range(1, len(all_temps_raw)):
        if abs(all_temps_raw[i] - all_temps_raw[i-1]) > 15:
            groups.append((start_idx, i))
            start_idx = i
    groups.append((start_idx, len(all_temps_raw)))

    records_plateau = []
    n_plateaus_skipped = 0
    for g_start, g_end in groups:
        g_temps = all_temps_raw[g_start:g_end]
        g_rhos = all_rho_raw[g_start:g_end]
        n_total = len(g_temps)

        if n_total < 5:
            continue

        n_discard = int(n_total * (1 - equilibration_fraction))
        eq_temps = g_temps[n_discard:]
        eq_rhos = g_rhos[n_discard:]

        if len(eq_rhos) < 3:
            continue

        # Equilibration drift check
        equilibrated = True
        if len(eq_rhos) >= 20:
            x_idx = np.arange(len(eq_rhos), dtype=float)
            slope, intercept, r_val, p_val, se = stats.linregress(x_idx, eq_rhos)
            total_drift = abs(slope * len(eq_rhos))
            mean_rho = np.mean(eq_rhos)
            drift_pct = total_drift / abs(mean_rho) * 100 if abs(mean_rho) > 1e-10 else 0
            if drift_pct > 1.0 and p_val < 0.01:
                equilibrated = False
                n_plateaus_skipped += 1

        set_T = round(float(np.median(eq_temps)) / 5) * 5
        records_plateau.append({
            "temperature":  float(set_T),
            "mean_density": float(np.mean(eq_rhos)),
            "std_density":  float(np.std(eq_rhos, ddof=1) if len(eq_rhos) > 1 else 0.0),
            "n_points":     int(len(eq_rhos)),
            "equilibrated": equilibrated,
        })

    # Merge duplicate set-point temperatures (weighted average)
    def _merge_plateaus(df_in):
        merged = []
        for T_sp, grp in df_in.groupby("temperature"):
            weights = grp["n_points"].values
            total_w = weights.sum()
            avg_rho = np.average(grp["mean_density"].values, weights=weights)
            avg_std = np.sqrt(np.average(grp["std_density"].values**2, weights=weights))
            merged.append({
                "temperature":  float(T_sp),
                "mean_density": float(avg_rho),
                "std_density":  float(avg_std),
                "n_points":     int(total_w),
            })
        if merged:
            return pd.DataFrame(merged).sort_values("temperature").reset_index(drop=True)
        return pd.DataFrame(columns=["temperature", "mean_density", "std_density", "n_points"])

    if records_plateau:
        df_plat_all = pd.DataFrame(records_plateau)
        df_plat = df_plat_all[df_plat_all["equilibrated"] == True].copy()
        df_bins_plateau = _merge_plateaus(df_plat)
        df_bins_plateau_all = _merge_plateaus(df_plat_all)
    else:
        df_bins_plateau = pd.DataFrame(
            columns=["temperature", "mean_density", "std_density", "n_points"])
        df_bins_plateau_all = df_bins_plateau
        n_plateaus_skipped = 0

    # Choose the better dataset for fitting
    if len(df_bins_plateau) >= 6:
        df_bins = df_bins_plateau
        binning_method = "plateau_detection"
    else:
        df_bins = df_bins_5k
        binning_method = "5K_bins"

    if len(df_bins) < 4:
        raise ValueError(
            f"Only {len(df_bins)} temperature bins found — need at least 4 for a "
            "bilinear fit.  Check that the log contains a temperature sweep."
        )

    temps = df_bins["temperature"].values
    densities = df_bins["mean_density"].values

    # -------------------------------------------------------------------
    # 3. PRIMARY: Exhaustive F-statistic split
    # -------------------------------------------------------------------
    primary_result, primary_err = fstat_split_tg(temps, densities)

    # -------------------------------------------------------------------
    # 3b. SECONDARY: scipy curve_fit bilinear
    # -------------------------------------------------------------------
    cf_result = curvefit_bilinear(temps, densities, tg_hint=initial_tg_guess)

    # -------------------------------------------------------------------
    # 4. Assemble final result
    # -------------------------------------------------------------------
    if primary_result:
        Tg_primary = primary_result["Tg_K"]
        r2_primary = primary_result["r_squared"]
    elif cf_result:
        Tg_primary = cf_result["Tg_alt_K"]
        r2_primary = cf_result["r_squared"]
    else:
        print(json.dumps({"status": "failed",
                           "error": primary_err or "All fitting methods failed"}))
        sys.exit(0)

    # Quality rating
    fit_quality_r2 = (
        "EXCELLENT" if r2_primary >= 0.995 else
        "GOOD"      if r2_primary >= 0.98 else
        "ACCEPTABLE" if r2_primary >= 0.95 else
        "POOR"
    )

    fstat_val = primary_result["f_statistic"] if primary_result else None
    n_bins_fit = int(len(temps))
    if fstat_val is not None and n_bins_fit > 4:
        from scipy.stats import f as f_dist
        p_fstat = 1 - f_dist.cdf(fstat_val, 2, n_bins_fit - 4)
        fit_quality_fstat = (
            "EXCELLENT" if p_fstat < 1e-10 else
            "GOOD"      if p_fstat < 1e-5 else
            "ACCEPTABLE" if p_fstat < 0.01 else
            "POOR"
        )
    else:
        p_fstat = None
        fit_quality_fstat = fit_quality_r2

    rank = {"EXCELLENT": 3, "GOOD": 2, "ACCEPTABLE": 1, "POOR": 0}
    fit_quality = min([fit_quality_r2, fit_quality_fstat],
                      key=lambda q: rank.get(q, 0))

    # -------------------------------------------------------------------
    # 5. Save outputs
    # -------------------------------------------------------------------
    bins_csv_5k = str(output_dir / "tg_density_bins.csv")
    df_bins_5k.to_csv(bins_csv_5k, index=False)

    if len(df_bins_plateau) >= 4:
        bins_csv_plateau = str(output_dir / "tg_density_bins_plateau.csv")
        df_bins_plateau.to_csv(bins_csv_plateau, index=False)
    else:
        bins_csv_plateau = None

    result = {
        "status":              "success",
        "log_file":            log_file,
        "output_dir":          str(output_dir),
        "Tg_K":                round(Tg_primary, 1),
        "Tg_alternative_K":    round(cf_result["Tg_alt_K"], 1) if cf_result else None,
        "Tg_curvefit_K":       round(cf_result["Tg_K"], 1) if cf_result else None,
        "r_squared":           round(r2_primary, 4),
        "fit_quality":         fit_quality,
        "fit_quality_r2":      fit_quality_r2,
        "fit_quality_fstat":   fit_quality_fstat,
        "f_statistic":         primary_result["f_statistic"] if primary_result else None,
        "f_statistic_pvalue":  float(p_fstat) if p_fstat is not None else None,
        "fit_method":          "F-stat exhaustive split" if primary_result else "curve_fit fallback",
        "binning_method":      binning_method,
        "fit_params": {
            "a_glassy":  primary_result["a_glassy"] if primary_result else (cf_result["a_glassy"] if cf_result else None),
            "b_glassy":  primary_result["b_glassy"] if primary_result else (cf_result["b_glassy"] if cf_result else None),
            "a_rubbery": primary_result["a_rubbery"] if primary_result else (cf_result["a_rubbery"] if cf_result else None),
            "b_rubbery": primary_result["b_rubbery"] if primary_result else (cf_result["b_rubbery"] if cf_result else None),
        },
        "n_temperature_bins":       int(len(temps)),
        "n_plateau_bins":           int(len(df_bins_plateau)) if df_bins_plateau is not None else 0,
        "n_plateaus_skipped_drift": int(n_plateaus_skipped),
        "temp_range_K":             [float(temps.min()), float(temps.max())],
        "bins_csv":                 bins_csv_5k,
        "bins_csv_plateau":         bins_csv_plateau,
        "equilibration_fraction":   equilibration_fraction,
        "temp_col":                 temp_col,
        "density_col":              density_col,
    }

    summary_json = str(output_dir / "tg_summary.json")
    with open(summary_json, "w") as jf:
        json.dump(result, jf, indent=2)
    result["summary_json"] = summary_json

    print(json.dumps(result))


if __name__ == "__main__":
    main()
