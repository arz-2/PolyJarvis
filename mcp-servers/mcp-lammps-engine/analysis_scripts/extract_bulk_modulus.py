#!/usr/bin/env python3
"""
extract_bulk_modulus.py — Extract isothermal bulk modulus from an NPT
simulation log using the volume fluctuation method.

Method (volume fluctuation):
    K_T = kB * T * <V> / Var(V)

where kB is Boltzmann's constant, T is temperature, <V> is the mean
volume, and Var(V) = <V²> - <V>² is the volume variance over the
production window of an NPT trajectory at constant T and P.

This is the standard statistical-mechanical route for isothermal bulk
modulus from NPT ensembles (Allen & Tildesley, 2017; Frenkel & Smit,
Ch. 5).  The method assumes the simulation is well-equilibrated and
samples the isobaric-isothermal ensemble.

Uncertainty is estimated via block averaging (Flyvbjerg & Petersen,
JCP 1989): the production window is split into blocks, K is computed
independently for each block, and the SEM of the block estimates gives
the uncertainty.

Output contract:
  - Prints a JSON summary to stdout as the last line.
  - Writes bulk_modulus.json and volume_timeseries.csv to --output_dir.
  - Exit 0 on success, non-zero on failure (errors to stderr).

Usage:
    python extract_bulk_modulus.py --log_file /path/to/npt.log \
                                   --output_dir /path/to/bulk_analysis \
                                   --eq_fraction 0.5

References:
    Allen & Tildesley, Computer Simulation of Liquids, 2nd ed. (2017)
    Frenkel & Smit, Understanding Molecular Simulation, 2nd ed. (2002)
    Flyvbjerg & Petersen, J. Chem. Phys. 91, 461 (1989)
"""

import argparse
import json
import re
import sys
import numpy as np
import pandas as pd
from pathlib import Path
from scipy import stats as sp_stats


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
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

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
    # 3. Drift check on volume (warn if still equilibrating)
    # -------------------------------------------------------------------
    x_idx = np.arange(n_prod, dtype=float)
    slope, intercept, r_val, p_val, se = sp_stats.linregress(x_idx, volumes)
    total_drift = abs(slope * n_prod)
    drift_pct = (total_drift / abs(np.mean(volumes)) * 100
                 if abs(np.mean(volumes)) > 1e-12 else 0)
    volume_equilibrated = not (drift_pct > 1.0 and p_val < 0.01)

    # -------------------------------------------------------------------
    # 4. Compute bulk modulus (full production window)
    # -------------------------------------------------------------------
    K_GPa, K_atm, meta = compute_bulk_modulus(volumes, T_mean)

    if K_GPa is None:
        print(json.dumps({"status": "failed", "error": meta.get("error", "Unknown")}))
        sys.exit(0)

    # -------------------------------------------------------------------
    # 5. Block-average uncertainty
    # -------------------------------------------------------------------
    block_count = args.block_count
    bs = n_prod // block_count
    block_K_values = []

    if bs >= 20:
        for i in range(block_count):
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
    # 6. Additional diagnostics
    # -------------------------------------------------------------------
    press_col = args.press_col
    density_col = args.density_col

    diagnostics = {
        "n_total_rows": n_total,
        "n_production_rows": n_prod,
        "eq_fraction": args.eq_fraction,
        "T_mean_K": round(T_mean, 2),
        "T_std_K": round(float(np.std(temperatures)), 2),
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
    # 7. Save outputs
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
        "block_averaging": block_info,
        "diagnostics": diagnostics,
        "volume_timeseries_csv": ts_csv,
    }

    if not volume_equilibrated:
        result["warning"] = (
            f"Volume drift {drift_pct:.2f}% (p={p_val:.2e}) exceeds threshold. "
            "The simulation may not be fully equilibrated — consider using a "
            "larger eq_fraction or running longer."
        )

    summary_path = str(output_dir / "bulk_modulus.json")
    with open(summary_path, "w") as jf:
        json.dump(result, jf, indent=2)
    result["summary_json"] = summary_path

    print(json.dumps(result))


if __name__ == "__main__":
    main()
