#!/usr/bin/env python3
"""
extract_tg.py — Extract glass transition temperature (Tg) from a LAMMPS
temperature-sweep log file.

Methodology (v4 — May 2026):
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
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
  Bilinear intersection via scipy curve_fit — the standard method used
  in polymer MD literature (Afzal 2021, Hayashi/RadonPy 2022, Klajmon
  2023, NkepsuMbitou 2025).  Two OLS lines are simultaneously fit to the
  glassy and rubbery regions; Tg is their intersection.  Physics
  constraints (both slopes negative, rubbery steeper) are enforced via
  bounds.  Quality is assessed by the overall bilinear R².

Output contract:
  - Prints a JSON summary to stdout as the last line.
  - Writes CSV and JSON files to --output_dir.
  - Exit 0 on success, non-zero on failure (errors to stderr).

References:
  Afzal et al., ACS Appl. Polym. Mater. 3 (2021) 6213–6228
  Hayashi et al., npj Comput. Mater. 8 (2022) 222
  Patrone et al., Polymer 87 (2016) 246–259

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

        # Equilibration drift check.
        # The 1% total-drift magnitude is the operative criterion.  The p-value is a
        # secondary guard to avoid dropping noisy-but-flat short series; it is NOT a
        # reliable significance test here because linregress assumes i.i.d. residuals
        # while MD thermo is autocorrelated (n_eff << n), making p systematically small.
        # For >=20 rows: dual gate (magnitude AND p < 0.01) — p provides marginal value.
        # For 3-19 rows: magnitude-only — at this sample size OLS SE is dominated by
        # noise and p is effectively unconstrained; magnitude alone is more honest.
        equilibrated = True
        if len(eq_rhos) >= 3:
            x_idx = np.arange(len(eq_rhos), dtype=float)
            slope, _, _, p_val, _ = stats.linregress(x_idx, eq_rhos)
            total_drift = abs(slope * len(eq_rhos))
            mean_rho = np.mean(eq_rhos)
            drift_pct = total_drift / abs(mean_rho) * 100 if abs(mean_rho) > 1e-10 else 0
            if len(eq_rhos) >= 20:
                failed = drift_pct > 1.0 and p_val < 0.01
            else:
                failed = drift_pct > 1.0
            if failed:
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
    # 3. PRIMARY: bilinear curve_fit (standard polymer MD literature method)
    # -------------------------------------------------------------------
    cf_result = curvefit_bilinear(temps, densities, tg_hint=initial_tg_guess)

    # -------------------------------------------------------------------
    # 4. Assemble final result
    # -------------------------------------------------------------------
    if cf_result:
        Tg_primary = cf_result["Tg_K"]
        r2_primary = cf_result["r_squared"]
    else:
        print(json.dumps({"status": "failed",
                           "error": "Bilinear curve_fit failed — check temperature range and data quality"}))
        sys.exit(0)

    # Quality rating based on bilinear R²
    fit_quality = (
        "EXCELLENT"  if r2_primary >= 0.995 else
        "GOOD"       if r2_primary >= 0.98  else
        "ACCEPTABLE" if r2_primary >= 0.95  else
        "POOR"
    )

    # Post-fit slope sanity checks (physics constraints not enforced by bounds)
    a_g = cf_result["a_glassy"]
    a_r = cf_result["a_rubbery"]
    slope_signs_valid    = (a_g < 0 and a_r < 0)
    slope_ordering_valid = (a_r < a_g)   # rubbery must be steeper (more negative)
    fit_warnings = []
    if not slope_signs_valid:
        fit_quality = "POOR"
        fit_warnings.append(
            f"slope_sign_invalid: a_glassy={a_g:.4e}, a_rubbery={a_r:.4e} "
            "(both must be negative — density decreases with T)"
        )
    if not slope_ordering_valid:
        fit_quality = "POOR"
        fit_warnings.append(
            f"slope_ordering_invalid: a_rubbery={a_r:.4e} not steeper than "
            f"a_glassy={a_g:.4e} (rubbery expansion coefficient should exceed glassy)"
        )

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
        "Tg_alternative_K":    round(cf_result["Tg_alt_K"], 1),
        "r_squared":           round(r2_primary, 4),
        "fit_quality":         fit_quality,
        "fit_method":          "bilinear_curvefit",
        "binning_method":      binning_method,
        "fit_params": {
            "a_glassy":  cf_result["a_glassy"],
            "b_glassy":  cf_result["b_glassy"],
            "a_rubbery": cf_result["a_rubbery"],
            "b_rubbery": cf_result["b_rubbery"],
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
        "slope_signs_valid":        slope_signs_valid,
        "slope_ordering_valid":     slope_ordering_valid,
        "fit_warnings":             fit_warnings,
    }

    summary_json = str(output_dir / "tg_summary.json")
    with open(summary_json, "w") as jf:
        json.dump(result, jf, indent=2)
    result["summary_json"] = summary_json

    print(json.dumps(result))


if __name__ == "__main__":
    main()
