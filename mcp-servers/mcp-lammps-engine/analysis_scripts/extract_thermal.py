#!/usr/bin/env python3
"""
extract_thermal.py — Extract thermal properties (Tg, CTE, ΔCp) from a LAMMPS
temperature-sweep log file.

Methodology (v5 — June 2026):
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Data preparation:
  1. Parse LAMMPS log file into a DataFrame of thermo rows.
  2. Detect temperature plateaus via jump detection (|ΔT| > 15 K
     between consecutive rows starts a new plateau).
  3. Within each plateau, discard burn-in, then average the remaining
     density and enthalpy values to get one (T_setpoint, ρ_mean, H_mean)
     data point.
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

Thermal properties extracted:
  - Tg:  density-kink glass transition temperature (K)
  - CTE: α_g = -a_glassy / ρ_mean_glassy, α_r = -a_rubbery / ρ_mean_rubbery  (K⁻¹)
  - ΔCp: from bilinear fit of H(T) = enthalpy vs T; requires tg_data_file for
         mass normalisation.  ΔCp [J/(g·K)] = (a_H_rubbery - a_H_glassy) × 4184 /
         system_mass_g_per_mol.  Skipped gracefully if Enthalpy column absent or
         tg_data_file not provided.

Output contract:
  - Prints a JSON summary to stdout as the last line.
  - Writes CSV and JSON files to --output_dir.
  - Exit 0 on success, non-zero on failure (errors to stderr).

References:
  Afzal et al., ACS Appl. Polym. Mater. 3 (2021) 6213–6228
  Hayashi et al., npj Comput. Mater. 8 (2022) 222
  Patrone et al., Polymer 87 (2016) 246–259

Usage:
    python extract_thermal.py --log_file /path/to/log.lammps \
                              --output_dir /path/to/tg_analysis \
                              --tg_data_file /path/to/system.data \
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
from analysis_utils import parse_lammps_log

warnings.filterwarnings("ignore", message="Reader has no dt information")
warnings.filterwarnings("ignore", category=UserWarning)


# ---------------------------------------------------------------------------
# LAMMPS log parser
# ---------------------------------------------------------------------------


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
# System mass from LAMMPS .data file (needed for ΔCp normalisation)
# ---------------------------------------------------------------------------

def _parse_system_mass_from_data_file(data_file_path):
    """
    Compute total system mass (g/mol) from a LAMMPS .data file.

    Reads the Masses section (atom type → atomic mass) and counts atoms per
    type from the Atoms section.  Returns (mass_g_per_mol, error_msg); on
    failure mass_g_per_mol is None and error_msg explains why.

    Supports LAMMPS `full` atom style (PCFF/EMC output: atom_id mol_id type_id
    charge x y z — type at column 2) and `charge`/`molecular` styles (type at
    column 1).  Style is auto-detected from the `Atoms  # full` comment.
    """
    try:
        p = Path(data_file_path)
        if not p.exists():
            return None, f"file not found: {data_file_path}"

        n_atoms_total = 0
        type_masses = {}
        type_counts = {}
        in_masses = False
        in_atoms = False
        atom_style = "full"  # default (PCFF/EMC)

        with open(p) as fh:
            for raw in fh:
                line = raw.strip()

                if not line:
                    continue  # blank lines are separators, not section terminators

                # Header: "N atoms"
                m = re.match(r'^(\d+)\s+atoms\s*$', line)
                if m:
                    n_atoms_total = int(m.group(1))
                    continue

                # Section headers
                if re.match(r'^Masses\b', line):
                    in_masses = True
                    in_atoms = False
                    continue
                if re.match(r'^Atoms\b', line):
                    in_atoms = True
                    in_masses = False
                    if '# full' in line:
                        atom_style = 'full'
                    elif '# charge' in line:
                        atom_style = 'charge'
                    elif '# molecular' in line:
                        atom_style = 'molecular'
                    continue
                # Any new uppercase section header ends current section
                if re.match(r'^[A-Z][A-Za-z]', line):
                    if in_atoms:
                        break
                    in_masses = False
                    continue

                if line.startswith('#'):
                    continue

                if in_masses:
                    tokens = line.split()
                    if len(tokens) >= 2:
                        try:
                            type_masses[int(tokens[0])] = float(tokens[1])
                        except ValueError:
                            pass

                elif in_atoms:
                    tokens = line.split()
                    # full style: atom_id mol_id type_id charge x y z  → type at index 2
                    # charge/molecular style: atom_id type_id ...       → type at index 1
                    type_col = 2 if atom_style == 'full' else 1
                    if len(tokens) > type_col:
                        try:
                            type_id = int(tokens[type_col])
                            if type_id in type_masses:
                                type_counts[type_id] = type_counts.get(type_id, 0) + 1
                        except ValueError:
                            pass

        if not type_masses:
            return None, "Masses section not found or empty"

        if type_counts:
            total_mass = sum(cnt * type_masses.get(tid, 0.0)
                             for tid, cnt in type_counts.items())
        elif n_atoms_total > 0:
            mean_mass = float(np.mean(list(type_masses.values())))
            total_mass = n_atoms_total * mean_mass
        else:
            return None, "no atom count information"

        return round(float(total_mass), 2), None

    except Exception as exc:
        return None, f"parse error: {exc}"


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
        description="Extract thermal properties (Tg, CTE, ΔCp) from a LAMMPS "
                    "temperature-sweep log via bilinear fitting."
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
    parser.add_argument("--enthalpy_col", default="Enthalpy",
                        help="Enthalpy column name in thermo output (for ΔCp).")
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
                        help="LAMMPS .data file used for the Tg sweep (topology/masses). "
                             "Required for ΔCp mass normalisation and MDAnalysis structural analysis.")
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
    enthalpy_col = args.enthalpy_col
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

    # Detect enthalpy column (optional — needed for ΔCp)
    _enth_col = enthalpy_col if enthalpy_col in df_all.columns else next(
        (c for c in df_all.columns if c.lower() == enthalpy_col.lower()), None)
    all_enthalpy_raw = df_all[_enth_col].values if _enth_col else None

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

    # -------------------------------------------------------------------
    # 3b. Hard physics-validity gate on the PRIMARY fit.
    # A fit that violates a hard constraint (slope signs not both negative, a degenerate
    # near-zero crossover width, or a Tg pinned to the sweep endpoints) is physically invalid
    # and must NOT headline tg_summary.json as Tg_K — it poisons the multi-rate extrapolation
    # and the run-summary (PSU1/PVC2: a 578 K endpoint-pinned hyperbola masked a valid ~437 K
    # bilinear). If the primary is invalid but the alternative fit is valid, swap it in.
    # If neither is valid, keep the primary but flag primary_fit_invalid so downstream guards.
    _span = float(temps.max()) - float(temps.min())

    def _hard_violations(cf):
        if not cf:
            return ["fit_missing"]
        v = []
        ag, ar = cf.get("a_glassy"), cf.get("a_rubbery")
        if not (isinstance(ag, (int, float)) and isinstance(ar, (int, float)) and ag < 0 and ar < 0):
            v.append("slope_sign_invalid")
        cw = cf.get("transition_width_c_K")
        if cw is not None and cw < 5.0:
            v.append("transition_width_degenerate")
        tgk = cf.get("Tg_K")
        if _span > 0 and isinstance(tgk, (int, float)) and (
                tgk <= float(temps.min()) + 0.05 * _span
                or tgk >= float(temps.max()) - 0.05 * _span):
            v.append("tg_pinned_to_sweep_endpoint")
        return v

    primary_violations = _hard_violations(cf_result)
    fit_swap_note = None
    if primary_violations and alt_result is not None and not _hard_violations(alt_result):
        invalid_method = fit_method_used
        invalid_tg = Tg_primary
        invalid_reasons = ",".join(primary_violations)
        cf_result, alt_result = alt_result, cf_result
        fit_method_used = "bilinear_curvefit"
        Tg_primary = cf_result["Tg_K"]
        r2_primary = cf_result["r_squared"]
        primary_violations = _hard_violations(cf_result)
        fit_swap_note = (
            f"primary_fit_swapped: {invalid_method} (Tg={invalid_tg:.1f} K) was physically "
            f"invalid [{invalid_reasons}]; swapped to bilinear_curvefit (Tg={Tg_primary:.1f} K)"
        )
    primary_fit_invalid = bool(primary_violations)

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
    if fit_swap_note:
        fit_warnings.append(fit_swap_note)
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
        # Too-narrow / degenerate transition: a near-zero crossover width is a fit artifact
        # (a sharp kink fit to noise), not a physical Tg. It can score high R² yet return an
        # outlier Tg — this is the PSU1 160 K/ns "width≈0 → Tg=565 K" failure that poisoned the
        # multi-rate extrapolation. A real glass transition spans ≳5–10 K; below that the
        # crossover is unresolved. Demote to POOR so the aggregation filter (>= ACCEPTABLE) drops it.
        elif c_width < 5.0:
            fit_quality = "POOR"
            fit_warnings.append(
                f"transition_width_degenerate: c={c_width:.2f} K (< 5 K) — unresolved kink "
                "artifact, Tg unreliable; excluded from multi-rate aggregation"
            )

    # Endpoint-pinned Tg: a transition fit whose Tg sits within ~5% of the sweep span from either
    # bound never captured a real crossover (the sweep didn't bracket Tg, or the fit ran to the
    # boundary). Demote to POOR so it is filtered rather than extrapolated from.
    _span = float(temps.max()) - float(temps.min())
    if _span > 0 and (Tg_primary <= float(temps.min()) + 0.05 * _span
                      or Tg_primary >= float(temps.max()) - 0.05 * _span):
        fit_quality = "POOR"
        fit_warnings.append(
            f"tg_pinned_to_sweep_endpoint: Tg={Tg_primary:.1f} K within 5% of the sweep bounds "
            f"[{float(temps.min()):.0f}, {float(temps.max()):.0f}] — sweep did not bracket Tg"
        )

    # -------------------------------------------------------------------
    # 4c. CTE from bilinear density fit slopes
    #     α = -(1/ρ) dρ/dT = -a_branch / ρ_mean_branch   [K⁻¹]
    # -------------------------------------------------------------------
    cte_glassy_per_K = None
    cte_rubbery_per_K = None
    if cf_result and slope_signs_valid:
        glassy_pts  = df_bins[df_bins["temperature"] <  Tg_primary]["mean_density"].values
        rubbery_pts = df_bins[df_bins["temperature"] >= Tg_primary]["mean_density"].values
        if len(glassy_pts) >= 2:
            rho_g = float(glassy_pts.mean())
            if rho_g > 0:
                cte_glassy_per_K = round(-cf_result["a_glassy"] / rho_g, 9)
        if len(rubbery_pts) >= 2:
            rho_r = float(rubbery_pts.mean())
            if rho_r > 0:
                cte_rubbery_per_K = round(-cf_result["a_rubbery"] / rho_r, 9)

    # -------------------------------------------------------------------
    # 4d. ΔCp from bilinear fit of enthalpy vs T
    #     ΔCp [J/(g·K)] = (a_H_rubbery − a_H_glassy) × 4184 / system_mass_g_per_mol
    #     Requires: Enthalpy column in log + tg_data_file for mass.
    # -------------------------------------------------------------------
    dCp_fields = {}
    if all_enthalpy_raw is None:
        dCp_fields["dCp_status"] = f"skipped (column '{enthalpy_col}' not in log)"
    elif tg_data_file is None:
        dCp_fields["dCp_status"] = "skipped (tg_data_file not provided for mass calculation)"
    else:
        system_mass, mass_err = _parse_system_mass_from_data_file(tg_data_file)
        if system_mass is None:
            dCp_fields["dCp_status"] = f"skipped (mass parse failed: {mass_err})"
        else:
            # Plateau averages of enthalpy (same groups as density)
            h_records = []
            for g_start, g_end in groups:
                g_t = all_temps_raw[g_start:g_end]
                g_h = all_enthalpy_raw[g_start:g_end]
                n_total = len(g_t)
                if n_total < 5:
                    continue
                n_discard = int(n_total * (1 - equilibration_fraction))
                eq_t = g_t[n_discard:]
                eq_h = g_h[n_discard:]
                if len(eq_h) < 3:
                    continue
                set_T = round(float(np.median(eq_t)) / 5) * 5
                h_records.append({
                    "temperature":   float(set_T),
                    "mean_enthalpy": float(np.mean(eq_h)),
                    "n_points":      int(len(eq_h)),
                })

            if len(h_records) >= 4:
                df_h = (pd.DataFrame(h_records)
                        .sort_values("temperature").reset_index(drop=True))
                h_fit = curvefit_bilinear(
                    df_h["temperature"].values,
                    df_h["mean_enthalpy"].values,
                    tg_hint=Tg_primary,
                )
                if h_fit:
                    delta_dH_dT = h_fit["a_rubbery"] - h_fit["a_glassy"]  # kcal/mol/K
                    dCp_J_per_g_K = delta_dH_dT * 4184.0 / system_mass
                    H_r2 = h_fit["r_squared"]
                    H_fit_quality = (
                        "EXCELLENT"  if H_r2 >= 0.995 else
                        "GOOD"       if H_r2 >= 0.98  else
                        "ACCEPTABLE" if H_r2 >= 0.95  else
                        "POOR"
                    )
                    dCp_fields = {
                        "dCp_status":                    "success",
                        "dCp_J_per_g_K":                 round(dCp_J_per_g_K, 4),
                        "H_slope_glassy_kcal_per_mol_K": round(h_fit["a_glassy"], 4),
                        "H_slope_rubbery_kcal_per_mol_K": round(h_fit["a_rubbery"], 4),
                        "H_r_squared":                   round(H_r2, 4),
                        "H_fit_quality":                 H_fit_quality,
                        "system_mass_g_per_mol":         system_mass,
                    }
                else:
                    dCp_fields["dCp_status"] = "skipped (enthalpy bilinear fit failed)"
            else:
                dCp_fields["dCp_status"] = (
                    f"skipped (only {len(h_records)} enthalpy plateau(s) — need ≥ 4)"
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
    # 6. Assemble final result
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
        # primary_fit_invalid: the headline Tg_K still violates a hard physics constraint (no valid
        # alternative existed to swap in). Downstream (generate_run_summary, is_glassy) must NOT
        # silently headline it. fit_swapped: a physically-invalid primary was replaced by the alt fit.
        "primary_fit_invalid":       primary_fit_invalid,
        "fit_swapped":               fit_swap_note is not None,
        "fit_warnings":              fit_warnings,
        "relaxation_metrics":        relaxation_metrics,
        # CTE (always present when bilinear fit succeeds and slopes are physical)
        "cte_glassy_per_K":          cte_glassy_per_K,
        "cte_rubbery_per_K":         cte_rubbery_per_K,
    }

    # ΔCp fields (present only when enthalpy column + tg_data_file available)
    result.update(dCp_fields)

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
