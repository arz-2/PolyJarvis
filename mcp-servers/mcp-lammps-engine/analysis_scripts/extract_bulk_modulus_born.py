#!/usr/bin/env python3
"""
extract_bulk_modulus_born.py — Extract isothermal bulk modulus via the
Born + NVT stress-fluctuation method from an nvt_born simulation.

Formula (NVT ensemble):
    K_T = K_Born + NkT/V − (V/kT)·Var(P)_NVT

where:
    K_Born  — Born elastic constant (bulk diagonal):
                (⟨C11⟩+⟨C22⟩+⟨C33⟩+2⟨C12⟩+2⟨C13⟩+2⟨C23⟩)/9
              read from fix ave/time output (Voigt 6×6, atm)
    NkT/V   — kinetic (ideal-gas) contribution
    Var(P)  — variance of isotropic pressure P=(pxx+pyy+pzz)/3 in NVT

This gives the unrelaxed (high-frequency) isothermal bulk modulus,
appropriate for comparison with ultrasonic or Brillouin scattering data.
For quasi-static (PVT dilatometry) references, apply K_T ≈ K_S×(Cv/Cp)
correction (~0.96 for glassy polymers).

Requires:
  - born_matrix_file from fix ave/time output (nvt_born template)
  - LAMMPS NVT log with pxx, pyy, pzz, vol, temp columns

Output contract:
  - Prints a JSON summary to stdout as the last line.
  - Writes bulk_modulus_born.json to --output_dir.
  - Exit 0 on success, non-zero on failure (errors to stderr).

Usage:
    python extract_bulk_modulus_born.py \
        --born_matrix_file /path/to/born_matrix.dat \
        --log_file /path/to/nvt_born.log \
        --n_atoms 4800 \
        --output_dir /path/to/born_analysis

References:
    Thompson, A.P. et al., J. Chem. Phys. 131, 154107 (2009).
    Allen & Tildesley, Computer Simulation of Liquids, 2nd ed. (2017) Ch. 7.
    Flyvbjerg & Petersen, J. Chem. Phys. 91, 461 (1989).
"""

import argparse
import json
import re
import sys
import numpy as np
import pandas as pd
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from plot_style import apply_style, save_fig

from analysis_utils import compute_tau_eff


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

KB_SI      = 1.380649e-23   # Boltzmann constant [J/K]
A3_TO_M3   = 1e-30          # Å³ → m³
ATM_TO_PA  = 101325.0       # atm → Pa
PA_TO_GPA  = 1e-9           # Pa → GPa
ATM_TO_GPA = ATM_TO_PA * PA_TO_GPA


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def parse_born_matrix_file(path: str) -> pd.DataFrame:
    """
    Parse the fix ave/time output for Born matrix elements.

    Expected file format (written by nvt_born template):
        # Time-averaged data for fix born_avg
        # TimeStep v_b11 v_b22 v_b33 v_b12 v_b13 v_b23
        1000  val  val  val  val  val  val
        2000  val  ...
    """
    rows = []
    cols = None
    with open(path) as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            if line.startswith("#"):
                # Header line: "# TimeStep v_b11 v_b22 v_b33 v_b12 v_b13 v_b23"
                tokens = line.lstrip("# ").split()
                if "TimeStep" in tokens or "timestep" in tokens[0].lower():
                    cols = tokens
                continue
            tokens = line.split()
            if not tokens:
                continue
            try:
                rows.append([float(t) for t in tokens])
            except ValueError:
                continue

    if not rows:
        raise ValueError(f"No data rows found in Born matrix file: {path}")

    if cols is None or len(cols) != len(rows[0]):
        # Default column names if header was malformed
        cols = ["TimeStep", "b11", "b22", "b33", "b12", "b13", "b23"][:len(rows[0])]

    df = pd.DataFrame(rows, columns=cols)
    # Normalize column names (strip "v_" prefix from LAMMPS variable names)
    rename = {}
    for c in df.columns:
        clean = c.replace("v_", "").lower()
        rename[c] = clean
    df.rename(columns=rename, inplace=True)
    return df


def parse_lammps_log(path: str) -> pd.DataFrame:
    """Parse all thermo tables from a LAMMPS log file."""
    all_dfs = []
    header = None
    rows = []
    with open(path) as f:
        for raw in f:
            line = raw.strip()
            if re.match(r"^Step\s", line):
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
# Core computation
# ---------------------------------------------------------------------------

def compute_k_born(b11, b22, b33, b12, b13, b23) -> float:
    """Bulk modulus Born term from Voigt elastic constant averages [atm]."""
    return (b11 + b22 + b33 + 2.0 * b12 + 2.0 * b13 + 2.0 * b23) / 9.0


def compute_kinetic_term_atm(n_atoms: int, T_mean: float, V_mean: float) -> float:
    """NkT/V kinetic contribution [atm]."""
    nkt_v_pa = n_atoms * KB_SI * T_mean / (V_mean * A3_TO_M3)
    return nkt_v_pa / ATM_TO_PA


def compute_fluctuation_term_atm(V_mean: float, T_mean: float, var_p: float) -> float:
    """(V/kT)·Var(P) stress-fluctuation correction [atm]. Input Var(P) in atm²."""
    # (V[m³] / kT[J]) × Var(P)[Pa²] → [Pa] → [atm]
    v_m3 = V_mean * A3_TO_M3
    kt_j = KB_SI * T_mean
    fluct_pa = (v_m3 / kt_j) * (var_p * ATM_TO_PA ** 2)
    return fluct_pa / ATM_TO_PA


def compute_k_t_block(b11, b22, b33, b12, b13, b23, p_arr, v_mean, t_mean, n_atoms) -> float:
    """Compute K_T from one production block (all units atm/Å³/K)."""
    k_born = compute_k_born(b11, b22, b33, b12, b13, b23)
    kinetic = compute_kinetic_term_atm(n_atoms, t_mean, v_mean)
    var_p = float(np.var(p_arr, ddof=1))
    fluct = compute_fluctuation_term_atm(v_mean, t_mean, var_p)
    return k_born + kinetic - fluct


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Extract isothermal bulk modulus from Born + NVT stress-fluctuation."
    )
    parser.add_argument("--born_matrix_file", required=True,
                        help="Path to fix ave/time Born matrix output file.")
    parser.add_argument("--log_file", required=True,
                        help="Path to nvt_born LAMMPS log (with pxx pyy pzz vol temp).")
    parser.add_argument("--n_atoms", type=int, required=True,
                        help="Total number of atoms in the simulation cell.")
    parser.add_argument("--output_dir", required=True,
                        help="Output directory for results.")
    parser.add_argument("--eq_fraction", type=float, default=0.5,
                        help="Fraction of rows used as production window (last eq_fraction).")
    parser.add_argument("--block_count", type=int, default=5,
                        help="Number of blocks for block-average uncertainty.")
    parser.add_argument("--graphs_dir", default=None,
                        help="Directory for PNG figures (default: <output_dir>/figures/).")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    graphs_dir = Path(args.graphs_dir) if args.graphs_dir else output_dir / "figures"
    graphs_dir.mkdir(parents=True, exist_ok=True)

    # -------------------------------------------------------------------
    # 1. Parse Born matrix file
    # -------------------------------------------------------------------
    try:
        born_df = parse_born_matrix_file(args.born_matrix_file)
    except Exception as e:
        print(json.dumps({"status": "failed", "error": f"Born matrix parse error: {e}"}))
        sys.exit(0)

    required_born_cols = {"b11", "b22", "b33", "b12", "b13", "b23"}
    missing = required_born_cols - set(born_df.columns)
    if missing:
        print(json.dumps({"status": "failed",
                          "error": f"Born matrix file missing columns: {missing}. "
                                   f"Found: {list(born_df.columns)}"}))
        sys.exit(0)

    # -------------------------------------------------------------------
    # 2. Parse NVT log
    # -------------------------------------------------------------------
    try:
        log_df = parse_lammps_log(args.log_file)
    except Exception as e:
        print(json.dumps({"status": "failed", "error": f"LAMMPS log parse error: {e}"}))
        sys.exit(0)

    needed_log = {"pxx", "pyy", "pzz", "vol", "temp"}
    # Try case-insensitive column matching (LAMMPS uses capitalized names: Pxx, Vol, Temp)
    col_map = {}
    for need in needed_log:
        for c in log_df.columns:
            if c.lower() == need:
                col_map[need] = c
                break
    missing_log = needed_log - set(col_map)
    if missing_log:
        # Try "Volume" for "vol", "Temp" for "temp"
        alias = {"vol": ["Volume", "Vol", "vol"],
                 "temp": ["Temp", "Temperature", "temp"]}
        for k, alts in alias.items():
            if k in missing_log:
                for a in alts:
                    if a in log_df.columns:
                        col_map[k] = a
                        missing_log.discard(k)
                        break

    if missing_log:
        print(json.dumps({"status": "failed",
                          "error": f"NVT log missing columns: {missing_log}. "
                                   f"Available: {list(log_df.columns)}"}))
        sys.exit(0)

    # -------------------------------------------------------------------
    # 3. Production windows
    # -------------------------------------------------------------------
    n_born_total = len(born_df)
    n_born_discard = int(n_born_total * (1.0 - args.eq_fraction))
    born_prod = born_df.iloc[n_born_discard:].reset_index(drop=True)

    n_log_total = len(log_df)
    n_log_discard = int(n_log_total * (1.0 - args.eq_fraction))
    log_prod = log_df.iloc[n_log_discard:].reset_index(drop=True)

    if len(born_prod) < 10:
        print(json.dumps({"status": "failed",
                          "error": f"Only {len(born_prod)} Born matrix rows in production window "
                                   f"(need ≥ 10). Run longer or reduce eq_fraction."}))
        sys.exit(0)

    if len(log_prod) < 50:
        print(json.dumps({"status": "failed",
                          "error": f"Only {len(log_prod)} NVT log rows in production window "
                                   f"(need ≥ 50)."}))
        sys.exit(0)

    # -------------------------------------------------------------------
    # 4. Full-production mean Born elements
    # -------------------------------------------------------------------
    b11_m = float(born_prod["b11"].mean())
    b22_m = float(born_prod["b22"].mean())
    b33_m = float(born_prod["b33"].mean())
    b12_m = float(born_prod["b12"].mean())
    b13_m = float(born_prod["b13"].mean())
    b23_m = float(born_prod["b23"].mean())

    K_Born_atm = compute_k_born(b11_m, b22_m, b33_m, b12_m, b13_m, b23_m)
    K_Born_GPa = K_Born_atm * ATM_TO_GPA

    # -------------------------------------------------------------------
    # 5. Pressure time series → Var(P), V_mean, T_mean
    # -------------------------------------------------------------------
    pxx = log_prod[col_map["pxx"]].values
    pyy = log_prod[col_map["pyy"]].values
    pzz = log_prod[col_map["pzz"]].values
    vol = log_prod[col_map["vol"]].values
    temp = log_prod[col_map["temp"]].values

    P_iso = (pxx + pyy + pzz) / 3.0  # isotropic pressure [atm]
    Var_P = float(np.var(P_iso, ddof=1))
    V_mean = float(np.mean(vol))
    T_mean = float(np.mean(temp))

    # -------------------------------------------------------------------
    # 6. Autocorrelation time on P for effective sample size
    # -------------------------------------------------------------------
    tau_frames, tau_frac = compute_tau_eff(P_iso)
    n_eff = int(len(P_iso) / max(1.0, 2.0 * tau_frames))

    # -------------------------------------------------------------------
    # 7. Kinetic and fluctuation terms
    # -------------------------------------------------------------------
    NkT_V_atm = compute_kinetic_term_atm(args.n_atoms, T_mean, V_mean)
    fluct_atm  = compute_fluctuation_term_atm(V_mean, T_mean, Var_P)

    K_T_atm = K_Born_atm + NkT_V_atm - fluct_atm
    K_T_GPa = K_T_atm * ATM_TO_GPA

    NkT_V_GPa = NkT_V_atm * ATM_TO_GPA
    fluct_GPa  = fluct_atm  * ATM_TO_GPA

    # -------------------------------------------------------------------
    # 8. Block-average uncertainty (split both born_prod and log_prod)
    # -------------------------------------------------------------------
    min_block_size = max(5, int(5.0 * max(tau_frames, 1.0)))
    actual_block_count = max(3, min(args.block_count,
                                    min(len(born_prod), len(log_prod)) // min_block_size))
    bs_born = len(born_prod) // actual_block_count
    bs_log  = len(log_prod)  // actual_block_count

    block_K_values = []
    for i in range(actual_block_count):
        b_chunk = born_prod.iloc[i * bs_born:(i + 1) * bs_born]
        l_chunk = log_prod.iloc[i * bs_log:(i + 1) * bs_log]
        if len(b_chunk) < 2 or len(l_chunk) < 2:
            continue
        bv_mean = float(l_chunk[col_map["vol"]].mean())
        bt_mean = float(l_chunk[col_map["temp"]].mean())
        bp_iso  = ((l_chunk[col_map["pxx"]] + l_chunk[col_map["pyy"]] +
                    l_chunk[col_map["pzz"]]) / 3.0).values
        bk = compute_k_t_block(
            float(b_chunk["b11"].mean()), float(b_chunk["b22"].mean()),
            float(b_chunk["b33"].mean()), float(b_chunk["b12"].mean()),
            float(b_chunk["b13"].mean()), float(b_chunk["b23"].mean()),
            bp_iso, bv_mean, bt_mean, args.n_atoms,
        )
        block_K_values.append(bk * ATM_TO_GPA)

    if len(block_K_values) >= 3:
        K_sem_GPa = float(np.std(block_K_values, ddof=1) / np.sqrt(len(block_K_values)))
        block_info = {
            "block_count": len(block_K_values),
            "block_K_GPa_values": [round(k, 4) for k in block_K_values],
            "K_block_mean_GPa": round(float(np.mean(block_K_values)), 4),
            "K_block_std_GPa":  round(float(np.std(block_K_values, ddof=1)), 4),
            "K_sem_GPa":        round(K_sem_GPa, 4),
        }
    else:
        K_sem_GPa = None
        block_info = {"block_count": len(block_K_values),
                      "note": "Too few valid blocks for uncertainty estimate"}

    # -------------------------------------------------------------------
    # 9. Diagnostics
    # -------------------------------------------------------------------
    diagnostics = {
        "n_born_total":       n_born_total,
        "n_born_production":  len(born_prod),
        "n_log_total":        n_log_total,
        "n_log_production":   len(log_prod),
        "eq_fraction":        args.eq_fraction,
        "T_mean_K":           round(T_mean, 2),
        "T_std_K":            round(float(np.std(temp)), 2),
        "V_mean_A3":          round(V_mean, 2),
        "V_std_A3":           round(float(np.std(vol)), 2),
        "P_mean_atm":         round(float(np.mean(P_iso)), 2),
        "P_std_atm":          round(float(np.std(P_iso)), 2),
        "Var_P_atm2":         round(Var_P, 4),
        "tau_eff_frames":     round(tau_frames, 2),
        "tau_eff_fraction":   round(tau_frac, 6),
        "n_effective_samples": n_eff,
        "K_Born_atm":         round(K_Born_atm, 2),
        "NkT_V_atm":          round(NkT_V_atm, 2),
        "fluct_correction_atm": round(fluct_atm, 2),
        "born_elements_mean_atm": {
            "b11": round(b11_m, 2), "b22": round(b22_m, 2), "b33": round(b33_m, 2),
            "b12": round(b12_m, 2), "b13": round(b13_m, 2), "b23": round(b23_m, 2),
        },
    }

    # -------------------------------------------------------------------
    # 10. Warnings
    # -------------------------------------------------------------------
    warnings_list = []
    if K_T_GPa < 0:
        warnings_list.append(
            f"K_T = {K_T_GPa:.3f} GPa < 0 — stress-fluctuation term dominates. "
            "Check that simulation is at constant volume (NVT) and has converged. "
            "Possible causes: too-short run, non-equilibrium drift, wrong n_atoms."
        )
    if K_Born_GPa < 0.5:
        warnings_list.append(
            f"K_Born = {K_Born_GPa:.3f} GPa is very low. "
            "Verify that EXTRA-COMPUTE is compiled and born/matrix output is valid."
        )
    if n_eff < 50:
        warnings_list.append(
            f"Only {n_eff} effectively independent pressure samples "
            f"(τ_eff ≈ {tau_frac*100:.1f}% of trajectory). "
            "Extend NVT-Born run for better statistics."
        )
    if tau_frac > 0.1:
        warnings_list.append(
            f"Pressure autocorrelation τ_eff ≈ {tau_frac*100:.1f}% of trajectory. "
            "Block sizes adjusted accordingly."
        )
    if abs(fluct_GPa) > 0.5 * abs(K_Born_GPa):
        warnings_list.append(
            f"Fluctuation correction ({fluct_GPa:.3f} GPa) is >50% of K_Born "
            f"({K_Born_GPa:.3f} GPa). This is unexpected for a glassy polymer — "
            "verify the system is in the glassy state at 300 K."
        )

    # -------------------------------------------------------------------
    # 11. Plot: Born diagonal elements time series
    # -------------------------------------------------------------------
    fig_path = None
    try:
        apply_style()
        fig, axes = plt.subplots(2, 1, figsize=(8, 6))
        ax1, ax2 = axes

        steps = born_df["timestep"].values if "timestep" in born_df.columns else np.arange(len(born_df))
        prod_steps = steps[n_born_discard:]
        ax1.plot(prod_steps, born_prod["b11"].values, lw=0.8, label="C11 (b11)")
        ax1.plot(prod_steps, born_prod["b22"].values, lw=0.8, label="C22 (b22)")
        ax1.plot(prod_steps, born_prod["b33"].values, lw=0.8, label="C33 (b33)")
        ax1.axhline(b11_m, color="C0", ls="--", lw=1.2)
        ax1.axhline(b22_m, color="C1", ls="--", lw=1.2)
        ax1.axhline(b33_m, color="C2", ls="--", lw=1.2)
        ax1.set_xlabel("LAMMPS step")
        ax1.set_ylabel("Born element (atm)")
        ax1.set_title("Born diagonal elements (production window)")
        ax1.legend(fontsize=8)

        prod_log_steps = (log_prod["Step"].values if "Step" in log_prod.columns
                          else np.arange(len(log_prod)))
        ax2.plot(prod_log_steps, P_iso, color="steelblue", lw=0.6, alpha=0.7, label="P(t)")
        ax2.axhline(float(np.mean(P_iso)), color="black", lw=1.5, ls="-", label="⟨P⟩")
        ax2.set_xlabel("LAMMPS step")
        ax2.set_ylabel("Isotropic pressure (atm)")
        ax2.set_title("Pressure time series (production window)")
        ax2.legend(fontsize=8)

        fig.tight_layout()
        fig_path = str(graphs_dir / "born_matrix_timeseries.png")
        save_fig(fig, fig_path)
    except Exception as _pe:
        print(f"  WARNING: Born matrix plot failed: {_pe}", flush=True)

    # -------------------------------------------------------------------
    # 12. Build result and save
    # -------------------------------------------------------------------
    result = {
        "status":                    "success",
        "born_matrix_file":          args.born_matrix_file,
        "log_file":                  args.log_file,
        "output_dir":                str(output_dir),
        "method":                    "born_nvt",
        "n_atoms":                   args.n_atoms,
        "bulk_modulus_GPa":          round(K_T_GPa, 4),
        "bulk_modulus_atm":          round(K_T_atm, 2),
        "bulk_modulus_sem_GPa":      round(K_sem_GPa, 4) if K_sem_GPa is not None else None,
        "K_Born_GPa":                round(K_Born_GPa, 4),
        "kinetic_term_GPa":          round(NkT_V_GPa, 4),
        "fluctuation_correction_GPa": round(fluct_GPa, 4),
        "V_mean_A3":                 round(V_mean, 2),
        "T_mean_K":                  round(T_mean, 2),
        "Var_P_atm2":                round(Var_P, 4),
        "n_effective_samples":       n_eff,
        "block_averaging":           block_info,
        "diagnostics":               diagnostics,
        "warnings":                  warnings_list,
        "born_timeseries_fig":       fig_path,
        "note_technique": (
            "Born+NVT gives unrelaxed (high-frequency) isothermal K_T. "
            "Comparable to ultrasonic/Brillouin K_S via K_T ≈ K_S×(Cv/Cp) (~0.96 for glassy). "
            "For quasi-static PVT references expect K_T 5–10% lower than this value."
        ),
    }

    summary_path = str(output_dir / "bulk_modulus_born.json")
    with open(summary_path, "w") as jf:
        json.dump(result, jf, indent=2)
    result["summary_json"] = summary_path

    print(json.dumps(result))


if __name__ == "__main__":
    main()
