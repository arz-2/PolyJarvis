#!/usr/bin/env python3
"""
extract_bulk_modulus.py — Extract isothermal bulk modulus from an NPT
simulation log using the volume fluctuation method (B_dyn) and the
definition formula cross-check (B_def).

Requirement: the input log must be from a constant-T, constant-P NPT
stage (e.g. Stage 7: 07_npt_production).  A temperature ramp or NVT
stage will give meaningless results.

Method 1 — volume fluctuation (B_dyn):
    K_T = kB * T * <V> / Var(V)

Method 2 — definition formula cross-check (B_def):
    B_def = -(dP / d ln V)_T
    from linear regression of instantaneous P vs ln V over the same
    production window (Wu, J. Phys. Chem. B 2020, 124, 10811, Eq. 4).
    Barostat-independent; R² of the fit is a quality diagnostic.

Both B_dyn and B_def are reported.  Agreement within 20% gives
confidence in B_dyn; larger disagreement flags possible barostat
artefacts or residual non-equilibrium drift.

Autocorrelation time τ_eff is estimated via batch-means plateau
(Flyvbjerg & Petersen, JCP 1989).  Block sizes for uncertainty are
set to ≥5×τ_eff to ensure near-independence.  Effective sample size
N_eff = n_prod / (2 τ_eff) is reported.

Output contract:
  - Prints a JSON summary to stdout as the last line.
  - Writes bulk_modulus.json and volume_timeseries.csv to --output_dir.
  - Exit 0 on success, non-zero on failure (errors to stderr).

Usage:
    python extract_bulk_modulus.py --log_file /path/to/07_npt_production.log \
                                   --output_dir /path/to/bulk_analysis \
                                   --eq_fraction 0.5

References:
    Allen & Tildesley, Computer Simulation of Liquids, 2nd ed. (2017)
    Frenkel & Smit, Understanding Molecular Simulation, 2nd ed. (2002)
    Flyvbjerg & Petersen, J. Chem. Phys. 91, 461 (1989)
    Wu, J. Phys. Chem. B 2020, 124, 10811
"""

import argparse
import json
import sys
import numpy as np
import pandas as pd
from pathlib import Path
from scipy import stats as sp_stats

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from plot_style import apply_style, save_fig

from analysis_utils import compute_tau_eff, parse_lammps_log


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

KB_SI = 1.380649e-23   # Boltzmann constant [J/K]
A3_TO_M3 = 1e-30       # Å³ -> m³
PA_TO_GPA = 1e-9        # Pa -> GPa
PA_TO_ATM = 1.0 / 101325.0  # Pa -> atm


# ---------------------------------------------------------------------------
# LAMMPS log parser
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Definition formula cross-check (B_def)
# ---------------------------------------------------------------------------

def compute_B_def(volumes, pressures):
    """
    Bulk modulus via definition formula: B_def = -(dP / d ln V)_T.
    Uses linear regression of instantaneous P vs ln(V).
    Wu, J. Phys. Chem. B 2020, 124, 10811, Eq. (4).

    Args:
        volumes:   array of instantaneous volumes (Å³)
        pressures: array of instantaneous pressures (atm)

    Returns:
        B_def_GPa (float), r_squared (float), meta (dict)
    """
    lnV = np.log(volumes)
    slope, intercept, r_val, p_val, se = sp_stats.linregress(lnV, pressures)
    # slope has units atm (P vs dimensionless ln V); convert to GPa
    B_def_GPa = float(-slope * 101325.0 * PA_TO_GPA)
    return B_def_GPa, float(r_val ** 2), {
        "slope_atm":   float(slope),
        "intercept_atm": float(intercept),
        "r_squared":   float(r_val ** 2),
        "p_value":     float(p_val),
        "n_points":    len(volumes),
    }


# ---------------------------------------------------------------------------
# Bulk modulus from volume fluctuation
# ---------------------------------------------------------------------------

def compute_bulk_modulus(volumes, temperature):
    """
    Compute isothermal bulk modulus from volume time series.

    K_T = kB * T * <V> / Var(V)

    Args:
        volumes: array of instantaneous volumes (Å³)
        temperature: mean temperature (K)

    Returns:
        K_GPa (float), K_atm (float), meta (dict)
    """
    V_mean = np.mean(volumes)
    V_var = np.var(volumes, ddof=1)  # sample variance

    if V_var <= 0 or V_mean <= 0:
        return None, None, {"error": "Zero or negative volume variance"}

    # K in Pa:  kB[J/K] * T[K] / (Var(V)[Å⁶] / <V>[Å³])
    #         = kB * T * <V> / Var(V)  [J/Å³]
    #         → multiply by 1/A3_TO_M3 to get Pa
    K_Pa = KB_SI * temperature * V_mean / V_var / A3_TO_M3
    K_GPa = K_Pa * PA_TO_GPA
    K_atm = K_Pa * PA_TO_ATM

    # Isothermal compressibility
    beta_T = 1.0 / K_Pa  # [1/Pa]

    meta = {
        "V_mean_A3": float(V_mean),
        "V_std_A3": float(np.sqrt(V_var)),
        "V_var_A6": float(V_var),
        "T_mean_K": float(temperature),
        "K_Pa": float(K_Pa),
        "beta_T_per_Pa": float(beta_T),
    }

    return float(K_GPa), float(K_atm), meta


# ---------------------------------------------------------------------------
# Plot
# ---------------------------------------------------------------------------

def plot_volume_fluctuations(volumes, V_mean, V_std, block_count, block_size, graphs_dir):
    apply_style()
    fig, ax = plt.subplots()
    frames = np.arange(len(volumes))
    ax.plot(frames, volumes, color='steelblue', lw=0.8, alpha=0.8, label='V(t)')
    ax.axhline(V_mean, color='black', lw=1.5, ls='-', label=f'Mean = {V_mean:.1f} Å³')
    ax.fill_between(frames, V_mean - 2 * V_std, V_mean + 2 * V_std,
                    color='steelblue', alpha=0.15, label='±2σ band')
    colors = plt.rcParams['axes.prop_cycle'].by_key()['color']
    for i in range(block_count):
        lo, hi = i * block_size, min((i + 1) * block_size, len(volumes))
        ax.axvspan(lo, hi, alpha=0.08 if i % 2 == 0 else 0,
                   color=colors[i % len(colors)])
    ax.set_xlabel('Production frame')
    ax.set_ylabel('Volume (Å³)')
    ax.set_title('NPT volume time series')
    ax.legend()
    save_fig(fig, str(graphs_dir / 'volume_fluctuations.png'))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Extract isothermal bulk modulus from an NPT LAMMPS log "
                    "using the volume fluctuation method."
    )
    parser.add_argument("--log_file", required=True,
                        help="Path to the LAMMPS log file (NPT run).")
    parser.add_argument("--output_dir", required=True,
                        help="Output directory for results.")
    parser.add_argument("--eq_fraction", type=float, default=0.5,
                        help="Fraction of rows used as production window "
                             "(0.5 = last 50%%).")
    parser.add_argument("--block_count", type=int, default=5,
                        help="Number of blocks for block-average uncertainty.")
    parser.add_argument("--vol_col", default="Volume",
                        help="Volume column name in thermo output.")
    parser.add_argument("--temp_col", default="Temp",
                        help="Temperature column name in thermo output.")
    parser.add_argument("--press_col", default="Press",
                        help="Pressure column name in thermo output.")
    parser.add_argument("--density_col", default="Density",
                        help="Density column name in thermo output.")
    parser.add_argument("--graphs_dir", default=None,
                        help="Directory for PNG figures (default: <output_dir>/figures/).")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    graphs_dir = Path(args.graphs_dir) if args.graphs_dir else output_dir / 'figures'
    graphs_dir.mkdir(parents=True, exist_ok=True)

    # -------------------------------------------------------------------
    # 1. Parse log
    # -------------------------------------------------------------------
    df = parse_lammps_log(args.log_file)

    # Auto-detect volume column: try "Volume", "Vol", "vol"
    vol_col = None
    for candidate in [args.vol_col, "Volume", "Vol", "vol"]:
        if candidate in df.columns:
            vol_col = candidate
            break
    if vol_col is None:
        print(json.dumps({
            "status": "failed",
            "error": f"No volume column found. Tried: {args.vol_col}, Volume, Vol, vol. "
                     f"Available: {list(df.columns)}"
        }))
        sys.exit(0)

    temp_col = args.temp_col
    if temp_col not in df.columns:
        # Try common alternatives
        for candidate in ["Temp", "temp", "Temperature"]:
            if candidate in df.columns:
                temp_col = candidate
                break
        if temp_col not in df.columns:
            print(json.dumps({
                "status": "failed",
                "error": f"Temperature column '{args.temp_col}' not found. "
                         f"Available: {list(df.columns)}"
            }))
            sys.exit(0)

    # -------------------------------------------------------------------
    # 2. Production window
    # -------------------------------------------------------------------
    n_total = len(df)
    n_discard = int(n_total * (1 - args.eq_fraction))
    prod = df.iloc[n_discard:].reset_index(drop=True)
    n_prod = len(prod)

    if n_prod < 50:
        print(json.dumps({
            "status": "failed",
            "error": f"Only {n_prod} production rows after discarding "
                     f"{n_discard} burn-in — need >= 50 for reliable "
                     "fluctuation statistics."
        }))
        sys.exit(0)

    volumes = prod[vol_col].values
    temperatures = prod[temp_col].values
    T_mean = float(np.mean(temperatures))

    # -------------------------------------------------------------------
    # 3. Autocorrelation time and effective sample size
    # -------------------------------------------------------------------
    tau_frames, tau_frac = compute_tau_eff(volumes)
    n_eff = int(n_prod / max(1.0, 2.0 * tau_frames))

    # -------------------------------------------------------------------
    # 4. Drift check on volume (warn if still equilibrating)
    # -------------------------------------------------------------------
    x_idx = np.arange(n_prod, dtype=float)
    slope, intercept, r_val, p_val, se = sp_stats.linregress(x_idx, volumes)
    total_drift = abs(slope * n_prod)
    drift_pct = (total_drift / abs(np.mean(volumes)) * 100
                 if abs(np.mean(volumes)) > 1e-12 else 0)
    volume_equilibrated = not (drift_pct > 1.0 and p_val < 0.01)

    # -------------------------------------------------------------------
    # 5. Compute bulk modulus B_dyn (full production window)
    # -------------------------------------------------------------------
    K_GPa, K_atm, meta = compute_bulk_modulus(volumes, T_mean)

    if K_GPa is None:
        print(json.dumps({"status": "failed", "error": meta.get("error", "Unknown")}))
        sys.exit(0)

    # -------------------------------------------------------------------
    # 6. Block-average uncertainty (τ_eff-aware block size)
    # -------------------------------------------------------------------
    block_count = args.block_count
    # Blocks must be ≥5×τ_eff frames to ensure near-independence
    min_block_size = max(20, int(5.0 * max(tau_frames, 1.0)))
    actual_block_count = max(3, min(block_count, n_prod // min_block_size))
    bs = n_prod // actual_block_count
    block_K_values = []

    for i in range(actual_block_count):
        block_vols = volumes[i * bs:(i + 1) * bs]
        block_temps = temperatures[i * bs:(i + 1) * bs]
        bK, _, _ = compute_bulk_modulus(block_vols, float(np.mean(block_temps)))
        if bK is not None:
            block_K_values.append(bK)

    if len(block_K_values) >= 3:
        K_block_mean = float(np.mean(block_K_values))
        K_block_std = float(np.std(block_K_values, ddof=1))
        K_sem = float(K_block_std / np.sqrt(len(block_K_values)))
        block_info = {
            "block_count": len(block_K_values),
            "block_size": bs,
            "block_K_GPa_values": [round(k, 4) for k in block_K_values],
            "K_block_mean_GPa": round(K_block_mean, 4),
            "K_block_std_GPa": round(K_block_std, 4),
            "K_sem_GPa": round(K_sem, 4),
        }
    else:
        K_sem = None
        block_info = {
            "block_count": len(block_K_values),
            "note": "Too few valid blocks for uncertainty estimate"
        }

    # -------------------------------------------------------------------
    # 7. Definition formula cross-check B_def (P vs ln V)
    # -------------------------------------------------------------------
    press_col = args.press_col
    density_col = args.density_col
    B_def_result = None
    if press_col in prod.columns:
        pressures = prod[press_col].values
        B_def_GPa_val, r2, bdef_meta = compute_B_def(volumes, pressures)
        agreement_pct = (abs(K_GPa - B_def_GPa_val) / abs(K_GPa) * 100
                         if abs(K_GPa) > 1e-6 else None)
        B_def_result = {
            "B_def_GPa": round(B_def_GPa_val, 4),
            "r_squared": round(r2, 4),
            "agreement_with_B_dyn_pct": round(agreement_pct, 2) if agreement_pct is not None else None,
            **bdef_meta,
        }

    # -------------------------------------------------------------------
    # 8. Additional diagnostics
    # -------------------------------------------------------------------

    diagnostics = {
        "n_total_rows": n_total,
        "n_production_rows": n_prod,
        "eq_fraction": args.eq_fraction,
        "T_mean_K": round(T_mean, 2),
        "T_std_K": round(float(np.std(temperatures)), 2),
        "tau_eff_frames": round(tau_frames, 2),
        "tau_eff_fraction": round(tau_frac, 6),
        "n_effective_samples": n_eff,
        "block_size_used": bs,
        "block_count_used": actual_block_count,
    }

    if press_col in prod.columns:
        diagnostics["P_mean_atm"] = round(float(prod[press_col].mean()), 2)
        diagnostics["P_std_atm"] = round(float(prod[press_col].std()), 2)

    if density_col in prod.columns:
        diagnostics["density_mean"] = round(float(prod[density_col].mean()), 6)
        diagnostics["density_std"] = round(float(prod[density_col].std()), 6)

    diagnostics["volume_drift_pct"] = round(drift_pct, 4)
    diagnostics["volume_drift_regression_p"] = float(p_val)
    diagnostics["volume_equilibrated"] = volume_equilibrated

    # -------------------------------------------------------------------
    # 9. Save outputs
    # -------------------------------------------------------------------

    # Volume time series CSV
    ts_df = pd.DataFrame({
        "step": prod["Step"].values if "Step" in prod.columns else np.arange(n_prod),
        "volume": volumes,
        "temperature": temperatures,
    })
    if press_col in prod.columns:
        ts_df["pressure"] = prod[press_col].values
    ts_csv = str(output_dir / "volume_timeseries.csv")
    ts_df.to_csv(ts_csv, index=False)

    result = {
        "status": "success",
        "log_file": args.log_file,
        "output_dir": str(output_dir),
        "method": "volume_fluctuation",
        "bulk_modulus_GPa": round(K_GPa, 4),
        "bulk_modulus_atm": round(K_atm, 2),
        "bulk_modulus_sem_GPa": round(K_sem, 4) if K_sem is not None else None,
        "isothermal_compressibility_per_Pa": meta["beta_T_per_Pa"],
        "V_mean_A3": round(meta["V_mean_A3"], 4),
        "V_std_A3": round(meta["V_std_A3"], 4),
        "tau_eff_frames": round(tau_frames, 2),
        "tau_eff_fraction": round(tau_frac, 6),
        "n_effective_samples": n_eff,
        "B_def": B_def_result,
        "block_averaging": block_info,
        "diagnostics": diagnostics,
        "volume_timeseries_csv": ts_csv,
        "barostat_note": (
            "B_dyn from NPT volume fluctuations is sensitive to barostat damping "
            "(P_DAMP). Nosé-Hoover (LAMMPS fix npt) gives a correct NPT ensemble; "
            "verify results are stable across P_DAMP values if reporting to high "
            "precision. B_def (P vs ln V slope) is barostat-independent and is "
            "provided as a cross-check (Wu, J. Phys. Chem. B 2020, 124, 10811). "
            "Agreement within 20% gives confidence in B_dyn."
        ),
    }

    if not volume_equilibrated:
        result["warning_drift"] = (
            f"Volume drift {drift_pct:.2f}% (p={p_val:.2e}) exceeds threshold. "
            "The simulation may not be fully equilibrated — consider using a "
            "larger eq_fraction or running longer."
        )
    if tau_frac > 0.1:
        result["warning_autocorrelation"] = (
            f"Volume autocorrelation time τ_eff ≈ {tau_frac * 100:.1f}% of "
            f"trajectory (N_eff = {n_eff}). Block sizes adjusted. "
            "Consider a longer NPT production run for improved statistics."
        )
    if n_eff < 50:
        result["warning_low_neff"] = (
            f"Only {n_eff} effectively independent volume samples. "
            "B_dyn uncertainty may be underestimated. Extend 07_npt_production."
        )
    if (B_def_result is not None
            and B_def_result.get("agreement_with_B_dyn_pct") is not None
            and B_def_result["agreement_with_B_dyn_pct"] > 20.0):
        result["warning_method_disagreement"] = (
            f"B_dyn ({K_GPa:.3f} GPa) and B_def ({B_def_result['B_def_GPa']:.3f} GPa) "
            f"disagree by {B_def_result['agreement_with_B_dyn_pct']:.1f}%. "
            "Possible barostat artefact or insufficient equilibration — see Wu 2020."
        )
    if (B_def_result is not None
            and B_def_result.get("r_squared") is not None
            and B_def_result["r_squared"] < 0.98):
        result["warning_bdef_unreliable"] = (
            f"B_def R²={B_def_result['r_squared']:.4f} < 0.98 — the P vs ln V relationship "
            "is nonlinear, indicating a large pressure derivative B0' (typical for soft melts). "
            "The B_def cross-check is unreliable here; B_dyn may also be biased by barostat "
            "damping. Use the Murnaghan multi-pressure series (run_bulk_modulus_series) for "
            "accurate K on rubbery polymers."
        )

    vol_fig_png = None
    try:
        plot_volume_fluctuations(volumes, meta["V_mean_A3"], meta["V_std_A3"],
                                 actual_block_count, bs, graphs_dir)
        vol_fig_png = str(graphs_dir / "volume_fluctuations.png")
    except Exception as _pe:
        print(f"  WARNING: volume_fluctuations plot failed: {_pe}", flush=True)
    result["volume_fluctuations_fig"] = vol_fig_png

    summary_path = str(output_dir / "bulk_modulus.json")
    with open(summary_path, "w") as jf:
        json.dump(result, jf, indent=2)
    result["summary_json"] = summary_path

    print(json.dumps(result))


if __name__ == "__main__":
    main()
