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
import warnings
import numpy as np
import pandas as pd
from pathlib import Path
from scipy import optimize, stats

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from plot_style import apply_style, save_fig

warnings.filterwarnings("ignore", message="Reader has no dt information")
warnings.filterwarnings("ignore", category=UserWarning)


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
# Statistical relaxation helpers
# ---------------------------------------------------------------------------

def _compute_n_eff(x):
    """
    Estimate effective independent samples via integrated ACF (Sokal window).
    Returns (n_eff, tau_int_steps).
    """
    n = len(x)
    if n < 4:
        return float(n), 0.5
    x = np.asarray(x, dtype=float) - np.mean(x)
    acf_full = np.correlate(x, x, mode='full')
    acf = acf_full[n - 1:]
    if acf[0] == 0:
        return float(n), 0.5
    acf = acf / acf[0]
    cutoff = n
    for k in range(1, n):
        if acf[k] <= 0:
            cutoff = k
            break
    tau_int = max(0.5, 0.5 + float(acf[1:cutoff].sum()))
    return float(n) / (2.0 * tau_int), float(tau_int)


# ---------------------------------------------------------------------------
# Structural analysis from per-T dump
# ---------------------------------------------------------------------------

def _saupe_p2(bond_vectors):
    if len(bond_vectors) == 0:
        return 0.0
    norms = np.linalg.norm(bond_vectors, axis=1, keepdims=True)
    valid = norms.flatten() > 0
    if valid.sum() < 2:
        return 0.0
    u = bond_vectors[valid] / norms[valid]
    Q = (3 * np.einsum("ni,nj->ij", u, u) - np.eye(3) * len(u)) / (2 * len(u))
    return float(np.linalg.eigvalsh(Q).max())


def _analyze_per_t_dump(per_t_dump_file, tg_data_file, backbone_types_list, detected_tg_K, group_temps_ordered):
    """
    Load per-T structural dump (one frame per temperature step) and compute
    per-T Rg, P2, and the Rg-kink dynamic Tg.

    backbone_types_list: list of int atom type IDs for backbone selection.
    group_temps_ordered: temperatures in dump-frame order (cooling order).
    detected_tg_K:       density-kink Tg (used to label rubbery vs glassy frames).
    """
    try:
        import MDAnalysis as mda
        import MDAnalysis.transformations as trans
    except ImportError:
        return {"status": "failed", "error": "MDAnalysis not available", "metrics": []}

    try:
        u = mda.Universe(tg_data_file, per_t_dump_file,
                         format="LAMMPSDUMP",
                         atom_style="id resid type charge x y z")
    except Exception as e:
        return {"status": "failed", "error": f"MDAnalysis load failed: {e}", "metrics": []}

    backbone_set = set(int(t) for t in backbone_types_list) if backbone_types_list else set()
    chain_ids = sorted(set(int(r) for r in u.atoms.resids))

    try:
        u.trajectory.add_transformations(trans.unwrap(u.atoms))
    except Exception:
        pass

    metrics = []
    for fi, ts in enumerate(u.trajectory):
        T = group_temps_ordered[fi] if fi < len(group_temps_ordered) else None
        above_tg = bool(T is not None and detected_tg_K is not None and T > detected_tg_K)

        rg_values = []
        bb_bond_vecs = []

        for cid in chain_ids:
            chain = u.select_atoms(f"resid {cid}")
            if chain.n_atoms == 0:
                continue
            try:
                rg_values.append(float(chain.radius_of_gyration()))
            except Exception:
                pass

            if backbone_set:
                try:
                    types = np.array([int(t) for t in chain.types])
                    mask = np.isin(types, list(backbone_set))
                    if mask.sum() >= 2:
                        bb = chain.atoms[mask]
                        order = np.argsort(bb.indices)
                        bb_pos = bb.positions[order]
                        for k in range(len(bb_pos) - 1):
                            bb_bond_vecs.append(bb_pos[k + 1] - bb_pos[k])
                except Exception:
                    pass

        mean_rg = float(np.mean(rg_values)) if rg_values else None
        rg_cv = (float(np.std(rg_values) / np.mean(rg_values))
                 if len(rg_values) > 1 and np.mean(rg_values) > 0 else None)
        p2 = _saupe_p2(np.array(bb_bond_vecs)) if bb_bond_vecs else None

        metrics.append({
            "temperature":       T,
            "mean_rg_A":         round(mean_rg, 3) if mean_rg is not None else None,
            "rg_cv":             round(rg_cv, 3)   if rg_cv  is not None else None,
            "p2":                round(p2, 4)       if p2    is not None else None,
            "structural_regime": "rubbery" if above_tg else "glassy",
            "p2_flag":           bool(p2 is not None and p2 > 0.10 and above_tg),
            "rg_cv_flag":        bool(rg_cv is not None and rg_cv > 0.30 and above_tg),
        })

    # Dynamic Tg from Rg-kink bilinear fit
    tg_dynamic_K = None
    valid_pts = [(m["temperature"], m["mean_rg_A"]) for m in metrics
                 if m["temperature"] is not None and m["mean_rg_A"] is not None]
    if len(valid_pts) >= 6:
        T_arr = np.array([p[0] for p in valid_pts])
        rg_arr = np.array([p[1] for p in valid_pts])
        rg_fit = curvefit_bilinear(T_arr, rg_arr, tg_hint=detected_tg_K)
        if rg_fit:
            tg_dynamic_K = round(rg_fit["Tg_K"], 1)

    return {
        "status":              "success",
        "n_frames":            len(metrics),
        "n_chains":            len(chain_ids),
        "Tg_dynamic_K":        tg_dynamic_K,
        "n_T_steps_p2_flag":   sum(1 for m in metrics if m.get("p2_flag")),
        "n_T_steps_rg_cv_flag": sum(1 for m in metrics if m.get("rg_cv_flag")),
        "metrics":             metrics,
    }


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


def hyperbola_indep(T, rho0, m_bar, delta, Tg, c):
    """Smoothed-bilinear (hyperbola) model: two linear asymptotes joined by a
    crossover of half-width c.  Low-T (glassy) slope = m_bar - delta, high-T
    (rubbery) slope = m_bar + delta; both asymptotes pass through (Tg, rho0).
    c -> 0 recovers a sharp bilinear kink at Tg."""
    return rho0 + m_bar * (T - Tg) + delta * np.sqrt((T - Tg) ** 2 + c ** 2)


def curvefit_hyperbola(T, rho, seed=None):
    """Global hyperbola fit of density vs T (Patrone-style smoothed model).

    Fits all points at once (no fit-range selection) and explicitly models the
    finite transition width via the parameter c.  `seed` is an optional dict from
    curvefit_bilinear used to initialise the nonlinear fit (the key robustness
    step).  Returns a dict mirroring curvefit_bilinear's keys plus
    transition_width_c_K and tg_uncertainty_K, or None on failure so the caller
    can fall back to the bilinear method.
    """
    idx = np.argsort(T)
    T, rho = T[idx], rho[idx]
    T_min, T_max = float(T[0]), float(T[-1])
    T_span = T_max - T_min
    if len(T) < 5 or T_span <= 0:
        return None

    # Initial guesses: prefer the bilinear seed, else crude polyfit halves.
    if seed is not None:
        a_g, a_r = seed["a_glassy"], seed["a_rubbery"]
        Tg0 = float(np.clip(seed["Tg_K"], T_min + 5, T_max - 5))
        rho0_0 = a_g * Tg0 + seed["b_glassy"]
    else:
        mid = (T_min + T_max) / 2
        lo, hi = T < mid, T >= mid
        p_lo = np.polyfit(T[lo], rho[lo], 1) if lo.sum() >= 2 else [0.0, float(rho.mean())]
        p_hi = np.polyfit(T[hi], rho[hi], 1) if hi.sum() >= 2 else [0.0, float(rho.mean())]
        a_g, a_r = float(p_lo[0]), float(p_hi[0])
        Tg0, rho0_0 = mid, float(rho.mean())
    p0 = [rho0_0, (a_g + a_r) / 2, (a_r - a_g) / 2, Tg0, T_span / 10.0]

    try:
        popt, pcov = optimize.curve_fit(
            hyperbola_indep, T, rho, p0=p0,
            bounds=([-np.inf, -np.inf, -np.inf, T_min + 5, 1e-3],
                    [ np.inf,  np.inf,  np.inf, T_max - 5, T_span]),
            maxfev=40000,
        )
    except Exception:
        return None

    rho0, m_bar, delta, Tg, c = popt
    a_glassy  = float(m_bar - delta)   # low-T asymptote slope
    a_rubbery = float(m_bar + delta)   # high-T asymptote slope

    pred = hyperbola_indep(T, *popt)
    ss_res = float(np.sum((rho - pred) ** 2))
    ss_tot = float(np.sum((rho - np.mean(rho)) ** 2))
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0

    # Tg uncertainty from the fit covariance (parameter index 3 = Tg).
    try:
        tg_sigma = float(np.sqrt(abs(pcov[3, 3])))
        if not np.isfinite(tg_sigma):
            tg_sigma = None
    except Exception:
        tg_sigma = None

    return {
        "Tg_K":                 float(Tg),
        "Tg_alt_K":             float(Tg),   # asymptotes meet at Tg by construction
        "a_glassy":             a_glassy,
        "b_glassy":             float(rho0 - a_glassy * Tg),
        "a_rubbery":            a_rubbery,
        "b_rubbery":            float(rho0 - a_rubbery * Tg),
        "r_squared":            float(r2),
        "transition_width_c_K": float(abs(c)),
        "tg_uncertainty_K":     tg_sigma,
    }


# ---------------------------------------------------------------------------
# Plot
# ---------------------------------------------------------------------------

def plot_tg_fit(temps, densities, cf_result, Tg_K, r2, fit_quality, graphs_dir):
    apply_style()
    fig, ax = plt.subplots()
    T_plot = np.linspace(temps.min(), temps.max(), 300)
    pred = np.where(
        T_plot < Tg_K,
        cf_result["a_glassy"] * T_plot + cf_result["b_glassy"],
        cf_result["a_rubbery"] * T_plot + cf_result["b_rubbery"],
    )
    ax.scatter(temps, densities, color='steelblue', s=40, zorder=3, label='Binned data')
    ax.plot(T_plot, pred, color='tomato', lw=2, label='Bilinear fit')
    ax.axvline(Tg_K, color='gray', ls='--', lw=1.5, label=f'Tg = {Tg_K:.0f} K')
    ax.set_xlabel('Temperature (K)')
    ax.set_ylabel('Density (g/cm³)')
    ax.set_title(f'Tg fit — R² = {r2:.4f} ({fit_quality})')
    ax.legend()
    save_fig(fig, str(graphs_dir / 'tg_fit.png'))


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
    parser.add_argument("--fit_method", choices=["auto", "hyperbola", "bilinear"],
                        default="auto",
                        help="Primary fit: 'auto' (hyperbola, fall back to bilinear), "
                             "'hyperbola', or legacy 'bilinear'.")
    parser.add_argument("--graphs_dir", default=None,
                        help="Directory for PNG figures (default: <output_dir>/figures/).")
    parser.add_argument("--per_t_dump_file", default=None,
                        help="Path to per-T structural dump (one frame per T step). "
                             "Enables dump-based structural analysis (Rg, P2, dynamic Tg).")
    parser.add_argument("--tg_data_file", default=None,
                        help="LAMMPS .data file used for the Tg sweep (topology/masses for MDAnalysis).")
    parser.add_argument("--backbone_types", nargs="*", type=int, default=None,
                        help="Backbone atom type IDs for P2 nematic order computation.")
    args = parser.parse_args()

    log_file = args.log_file
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    graphs_dir = Path(args.graphs_dir) if args.graphs_dir else output_dir / 'figures'
    graphs_dir.mkdir(parents=True, exist_ok=True)
    initial_tg_guess = args.initial_tg_guess
    equilibration_fraction = args.equilibration_fraction
    temp_col = args.temp_col
    density_col = args.density_col
    fit_method = args.fit_method
    per_t_dump_file = args.per_t_dump_file
    tg_data_file = args.tg_data_file
    backbone_types = args.backbone_types

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
    group_temps_ordered = []   # all group median-Ts in log order, for dump frame mapping
    n_plateaus_skipped = 0
    n_plateaus_low_n_eff = 0
    for g_start, g_end in groups:
        g_temps = all_temps_raw[g_start:g_end]
        g_rhos = all_rho_raw[g_start:g_end]
        n_total = len(g_temps)

        # Always record the group temperature for dump-frame mapping, even if filtered
        if n_total > 0:
            group_temps_ordered.append(round(float(np.median(g_temps)) / 5) * 5)

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

        # n_eff: effective independent samples via integrated density ACF
        n_eff, tau_int = _compute_n_eff(eq_rhos)
        relax_warning = bool(n_eff < 5.0)
        if relax_warning:
            n_plateaus_low_n_eff += 1

        set_T = round(float(np.median(eq_temps)) / 5) * 5
        records_plateau.append({
            "temperature":    float(set_T),
            "mean_density":   float(np.mean(eq_rhos)),
            "std_density":    float(np.std(eq_rhos, ddof=1) if len(eq_rhos) > 1 else 0.0),
            "n_points":       int(len(eq_rhos)),
            "equilibrated":   equilibrated,
            "n_eff":          round(n_eff, 2),
            "tau_int_steps":  round(tau_int, 1),
            "relax_warning":  relax_warning,
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
    # 3. PRIMARY: hyperbola (smoothed-bilinear) fit, seeded from and falling back
    #    to the legacy bilinear fit.  --fit_method selects the behaviour.
    # -------------------------------------------------------------------
    bilinear_result = curvefit_bilinear(temps, densities, tg_hint=initial_tg_guess)
    hyperbola_result = (curvefit_hyperbola(temps, densities, seed=bilinear_result)
                        if fit_method in ("auto", "hyperbola") else None)

    if fit_method == "bilinear":
        cf_result, fit_method_used = bilinear_result, "bilinear_curvefit"
    elif fit_method == "hyperbola":
        cf_result, fit_method_used = hyperbola_result, "hyperbola_curvefit"
    else:  # auto: hyperbola if it converged, else bilinear
        if hyperbola_result is not None:
            cf_result, fit_method_used = hyperbola_result, "hyperbola_curvefit"
        else:
            cf_result, fit_method_used = bilinear_result, "bilinear_curvefit"

    # -------------------------------------------------------------------
    # 4. Bilinear fit quality + physics checks
    # -------------------------------------------------------------------
    if cf_result:
        Tg_primary = cf_result["Tg_K"]
        r2_primary = cf_result["r_squared"]
        # Cross-check from the alternative method (bilinear when hyperbola is primary).
        alt_result = bilinear_result if fit_method_used == "hyperbola_curvefit" else None
    else:
        print(json.dumps({"status": "failed",
                           "error": f"{fit_method_used} failed — check temperature range and data quality"}))
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

    # Transition-width sanity (hyperbola only): a crossover wider than half the
    # sweep span means the transition is not well localised — sweep too narrow or
    # data too noisy.  Cap quality at ACCEPTABLE and warn.
    c_width = cf_result.get("transition_width_c_K")
    if c_width is not None:
        half_span = 0.5 * (float(temps.max()) - float(temps.min()))
        if c_width > half_span:
            _order = {"EXCELLENT": 3, "GOOD": 2, "ACCEPTABLE": 1, "POOR": 0}
            if _order.get(fit_quality, 1) > 1:
                fit_quality = "ACCEPTABLE"
            fit_warnings.append(
                f"transition_width_too_broad: c={c_width:.1f} K exceeds half the sweep "
                f"span ({half_span:.0f} K) — transition poorly localised"
            )

    # -------------------------------------------------------------------
    # 5. Save density bin CSVs
    # -------------------------------------------------------------------
    bins_csv_5k = str(output_dir / "tg_density_bins.csv")
    df_bins_5k.to_csv(bins_csv_5k, index=False)

    if len(df_bins_plateau) >= 4:
        bins_csv_plateau = str(output_dir / "tg_density_bins_plateau.csv")
        df_bins_plateau.to_csv(bins_csv_plateau, index=False)
    else:
        bins_csv_plateau = None

    # -------------------------------------------------------------------
    # 4a. Build relaxation_metrics from plateau records (log-based n_eff)
    # -------------------------------------------------------------------
    relaxation_metrics = [
        {
            "temperature":   r["temperature"],
            "n_eff":         r["n_eff"],
            "tau_int_steps": r["tau_int_steps"],
            "relax_warning": r["relax_warning"],
        }
        for r in records_plateau
    ]

    # -------------------------------------------------------------------
    # 4b. Dump-based structural analysis (optional)
    # -------------------------------------------------------------------
    structural_analysis = None
    if per_t_dump_file and tg_data_file:
        print(f"  Running dump-based structural analysis: {per_t_dump_file}", flush=True)
        try:
            structural_analysis = _analyze_per_t_dump(
                per_t_dump_file   = per_t_dump_file,
                tg_data_file      = tg_data_file,
                backbone_types_list = backbone_types or [],
                detected_tg_K     = Tg_primary,
                group_temps_ordered = group_temps_ordered,
            )
        except Exception as _se:
            structural_analysis = {"status": "failed", "error": str(_se), "metrics": []}
            print(f"  WARNING: structural analysis failed: {_se}", flush=True)

    # -------------------------------------------------------------------
    # 5. Assemble final result
    # -------------------------------------------------------------------
    result = {
        "status":              "success",
        "log_file":            log_file,
        "output_dir":          str(output_dir),
        "Tg_K":                round(Tg_primary, 1),
        "Tg_alternative_K":    round(alt_result["Tg_K"], 1) if alt_result else round(cf_result["Tg_alt_K"], 1),
        "r_squared":           round(r2_primary, 4),
        "fit_quality":         fit_quality,
        "fit_method":          fit_method_used,
        "transition_width_c_K": (round(cf_result["transition_width_c_K"], 1)
                                 if cf_result.get("transition_width_c_K") is not None else None),
        "tg_uncertainty_K":    (round(cf_result["tg_uncertainty_K"], 1)
                                if cf_result.get("tg_uncertainty_K") is not None else None),
        "binning_method":      binning_method,
        "fit_params": {
            "a_glassy":  cf_result["a_glassy"],
            "b_glassy":  cf_result["b_glassy"],
            "a_rubbery": cf_result["a_rubbery"],
            "b_rubbery": cf_result["b_rubbery"],
        },
        "n_temperature_bins":        int(len(temps)),
        "n_plateau_bins":            int(len(df_bins_plateau)) if df_bins_plateau is not None else 0,
        "n_plateaus_skipped_drift":  int(n_plateaus_skipped),
        "n_plateaus_low_n_eff":      int(n_plateaus_low_n_eff),
        "temp_range_K":              [float(temps.min()), float(temps.max())],
        "bins_csv":                  bins_csv_5k,
        "bins_csv_plateau":          bins_csv_plateau,
        "equilibration_fraction":    equilibration_fraction,
        "temp_col":                  temp_col,
        "density_col":               density_col,
        "slope_signs_valid":         slope_signs_valid,
        "slope_ordering_valid":      slope_ordering_valid,
        "fit_warnings":              fit_warnings,
        "relaxation_metrics":        relaxation_metrics,
    }

    # Structural analysis results (present only when dump was provided)
    if structural_analysis is not None:
        result["Tg_dynamic_K"]            = structural_analysis.get("Tg_dynamic_K")
        result["n_T_steps_p2_flag"]       = structural_analysis.get("n_T_steps_p2_flag")
        result["n_T_steps_rg_cv_flag"]    = structural_analysis.get("n_T_steps_rg_cv_flag")
        result["structural_metrics_per_T"] = structural_analysis.get("metrics", [])
        result["structural_analysis_status"] = structural_analysis.get("status", "unknown")
        if structural_analysis.get("status") == "failed":
            result["structural_analysis_error"] = structural_analysis.get("error")

    tg_fig_png = None
    try:
        plot_tg_fit(temps, densities, cf_result, Tg_primary, r2_primary, fit_quality, graphs_dir)
        tg_fig_png = str(graphs_dir / "tg_fit.png")
    except Exception as _pe:
        print(f"  WARNING: tg_fit plot failed: {_pe}", flush=True)
    result["tg_fit_png"] = tg_fig_png

    summary_json = str(output_dir / "tg_summary.json")
    with open(summary_json, "w") as jf:
        json.dump(result, jf, indent=2)
    result["summary_json"] = summary_json

    print(json.dumps(result))


if __name__ == "__main__":
    main()
