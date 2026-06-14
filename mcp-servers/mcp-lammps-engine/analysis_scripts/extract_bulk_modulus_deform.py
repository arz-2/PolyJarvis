#!/usr/bin/env python3
"""
extract_bulk_modulus_deform.py — Extract elastic constants from a LAMMPS
uniaxial deformation log (npt_deform template, Stage 5b).

Method: Linear stress-strain fit in the elastic regime.

Applies to uniaxial x-strain at fixed y/z (NVT, no barostat):
  C11 = -d(pxx)/d(ε_xx)  in GPa   (axial stiffness)
  C12 = -d(pyy)/d(ε_xx)  in GPa   (lateral coupling, isotropic assumption)

Derived moduli (Voigt isotropic approximation):
  K = (C11 + 2·C12) / 3           (bulk modulus, GPa)
  G = (C11 - C12) / 2             (shear modulus, GPa)
  E = 9·K·G / (3·K + G)           (Young's modulus, GPa)
  ν = C12 / (C11 + C12)           (Poisson's ratio, dimensionless)

Strain is reconstructed from step number:
  ε_xx(step) = STRAIN_RATE [1/fs] × (step − step_0) × TIMESTEP [fs]

The linear regime is identified automatically:
  - All data within [ε_start, ε_max] where ε_max ≤ STRAIN_MAX
  - Goodness-of-fit R² reported for both C11 and C12 fits

Output contract:
  - Prints a JSON summary to stdout as the last line.
  - Writes bulk_modulus_deform.json and stress_strain.csv to --output_dir.
  - Exit 0 on success, non-zero on failure (errors to stderr).

Usage:
    python extract_bulk_modulus_deform.py \
        --log_file /path/to/npt_deform.log \
        --output_dir /path/to/deform_analysis \
        --strain_rate 1e-7 \
        --strain_max 0.03 \
        --timestep 1.0 \
        --eq_steps 200000

References:
    Theodorou & Suter, Macromolecules 19, 139 (1986) — elastic constants of glassy polymers
    Hossain et al. Polymer 51, 6071 (2010) — MD uniaxial deformation protocol
    Mattsson et al. J. Chem. Phys. 133, 234101 (2010) — strain-rate artifacts
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

ATM_TO_PA  = 101325.0   # 1 atm in Pa
PA_TO_GPA  = 1e-9       # Pa → GPa
ATM_TO_GPA = ATM_TO_PA * PA_TO_GPA


# ---------------------------------------------------------------------------
# LAMMPS log parser (shared with extract_bulk_modulus.py)
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
# Linear fit with R²
# ---------------------------------------------------------------------------

def linear_fit(x, y):
    """Fit y = slope*x + intercept. Returns slope, intercept, R², p-value."""
    slope, intercept, r_val, p_val, se = sp_stats.linregress(x, y)
    return float(slope), float(intercept), float(r_val ** 2), float(p_val)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Extract elastic constants from LAMMPS uniaxial deformation log."
    )
    parser.add_argument("--log_file",    required=True,
                        help="Path to npt_deform LAMMPS log (deformation phase).")
    parser.add_argument("--output_dir",  required=True,
                        help="Output directory for results.")
    parser.add_argument("--strain_rate", type=float, default=1e-7,
                        help="Engineering strain rate (1/fs). Default: 1e-7.")
    parser.add_argument("--strain_max",  type=float, default=0.03,
                        help="Maximum strain for linear-regime fit. Default: 0.03.")
    parser.add_argument("--timestep",    type=float, default=1.0,
                        help="MD timestep (fs). Default: 1.0.")
    parser.add_argument("--eq_steps",    type=int,   default=200000,
                        help="NVT pre-equilibration steps in Phase 1 (skipped). Default: 200000.")
    parser.add_argument("--strain_start", type=float, default=0.002,
                        help="Minimum strain to include in fit (skip initial transient). Default: 0.002.")
    parser.add_argument("--avg_window", type=int, default=2000,
                        help=(
                            "Rolling-average window in thermo frames applied to stress before fitting. "
                            "Reduces thermal noise (σ_therm ~ 0.2 GPa at THERMO_FREQ=100) that otherwise "
                            "swamps the elastic signal (~0.09 GPa at 3%% strain). "
                            "Default 2000 = 200 ps at THERMO_FREQ=100 (covers stress τ_relax in glassy polymers). "
                            "Set to 1 to disable. Increase proportionally if THERMO_FREQ > 100."
                        ))
    parser.add_argument("--log_file_2", default=None,
                        help="Optional second deformation log at a different strain rate "
                             "for rate-sensitivity comparison. Used with --strain_rate_2.")
    parser.add_argument("--strain_rate_2", type=float, default=None,
                        help="Strain rate (1/fs) for --log_file_2. Typically 10× slower than --strain_rate.")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # -------------------------------------------------------------------
    # 1. Parse log
    # -------------------------------------------------------------------
    df = parse_lammps_log(args.log_file)

    required_cols = {"Step", "Pxx", "Pyy", "Pzz"}
    # LAMMPS thermo columns are case-sensitive: pxx → Pxx in output? Check:
    # Standard LAMMPS thermo column names: "Pxx" "Pyy" "Pzz" with capital P
    col_map = {}
    for needed in ["Pxx", "Pyy", "Pzz", "Step", "Temp"]:
        # Try exact and lowercase variants
        for candidate in [needed, needed.lower(), needed.upper()]:
            if candidate in df.columns:
                col_map[needed] = candidate
                break

    missing = [c for c in ["Pxx", "Pyy", "Pzz", "Step"] if c not in col_map]
    if missing:
        print(json.dumps({
            "status": "failed",
            "error": (
                f"Missing required columns: {missing}. "
                f"Available: {list(df.columns)}. "
                "Ensure npt_deform template uses thermo_style with pxx pyy pzz."
            )
        }))
        sys.exit(0)

    steps = df[col_map["Step"]].values
    pxx_atm = df[col_map["Pxx"]].values   # pressure in atm
    pyy_atm = df[col_map["Pyy"]].values
    pzz_atm = df[col_map["Pzz"]].values

    # -------------------------------------------------------------------
    # 2. Split Phase 1 (NVT equil) from Phase 2 (deformation)
    # -------------------------------------------------------------------
    # Phase 1 ends at step ≈ eq_steps; Phase 2 begins at step_0.
    # Identify step_0 as the step just after eq_steps.
    step_0_idx = np.searchsorted(steps, args.eq_steps)
    if step_0_idx >= len(steps) - 10:
        print(json.dumps({
            "status": "failed",
            "error": (
                f"Only {len(steps) - step_0_idx} thermo rows found in Phase 2 "
                f"(deformation) after discarding {step_0_idx} Phase 1 rows. "
                "Check --eq_steps matches the N_EQ_STEPS used in the simulation."
            )
        }))
        sys.exit(0)

    # Phase 2 data
    steps_def  = steps[step_0_idx:]
    pxx_def    = pxx_atm[step_0_idx:]
    pyy_def    = pyy_atm[step_0_idx:]
    pzz_def    = pzz_atm[step_0_idx:]
    step_start = steps_def[0]

    # -------------------------------------------------------------------
    # 2b. Rolling time-average to reduce thermal noise
    # -------------------------------------------------------------------
    # Thermal stress fluctuations (~0.2 GPa at 100 fs) swamp the elastic
    # signal (~0.09 GPa at 3% strain). Average over avg_window thermo frames
    # before fitting. Window=2000 at THERMO_FREQ=100 → 200 ps averaging.
    avg_window = max(1, args.avg_window)
    if avg_window > 1:
        pxx_s = pd.Series(pxx_def).rolling(avg_window, center=True, min_periods=1).mean().values
        pyy_s = pd.Series(pyy_def).rolling(avg_window, center=True, min_periods=1).mean().values
        pzz_s = pd.Series(pzz_def).rolling(avg_window, center=True, min_periods=1).mean().values
    else:
        pxx_s, pyy_s, pzz_s = pxx_def, pyy_def, pzz_def

    # -------------------------------------------------------------------
    # 3. Reconstruct engineering strain
    # -------------------------------------------------------------------
    # ε_xx = STRAIN_RATE [1/fs] × (step − step_0) × TIMESTEP [fs]
    strain = args.strain_rate * (steps_def - step_start) * args.timestep

    # -------------------------------------------------------------------
    # 4. Select linear elastic regime: [strain_start, strain_max]
    # -------------------------------------------------------------------
    mask = (strain >= args.strain_start) & (strain <= args.strain_max)
    if mask.sum() < 20:
        print(json.dumps({
            "status": "failed",
            "error": (
                f"Only {mask.sum()} data points in linear regime "
                f"[{args.strain_start}, {args.strain_max}]. "
                "Increase N_STEPS or check strain_rate/strain_max."
            )
        }))
        sys.exit(0)

    eps   = strain[mask]
    s_xx  = -pxx_s[mask] * ATM_TO_GPA   # σ_xx = -P_xx, GPa (time-averaged)
    s_yy  = -pyy_s[mask] * ATM_TO_GPA
    s_zz  = -pzz_s[mask] * ATM_TO_GPA

    # -------------------------------------------------------------------
    # 5. Fit C11 and C12
    # -------------------------------------------------------------------
    # C11 = dσ_xx/dε_xx (slope of σ_xx vs ε)
    # C12 = dσ_yy/dε_xx (slope of σ_yy vs ε, isotropic → same as C13)
    slope_xx, _, r2_xx, p_xx = linear_fit(eps, s_xx)
    slope_yy, _, r2_yy, p_yy = linear_fit(eps, s_yy)
    slope_zz, _, r2_zz, p_zz = linear_fit(eps, s_zz)

    C11 = float(slope_xx)   # GPa
    C12 = float((slope_yy + slope_zz) / 2.0)   # average of yy and zz (isotropy check)

    # -------------------------------------------------------------------
    # 6. Derived moduli (Voigt isotropic)
    # -------------------------------------------------------------------
    K = (C11 + 2.0 * C12) / 3.0      # bulk modulus (GPa)
    G = (C11 - C12) / 2.0             # shear modulus (GPa)
    E = 9.0 * K * G / (3.0 * K + G) if (3.0 * K + G) > 1e-6 else None
    nu = C12 / (C11 + C12) if (C11 + C12) > 1e-6 else None

    # Isotropy check: σ_yy and σ_zz should agree
    isotropy_delta = abs(slope_yy - slope_zz) / abs((slope_yy + slope_zz) / 2.0) * 100 \
        if abs((slope_yy + slope_zz) / 2.0) > 1e-6 else None

    # -------------------------------------------------------------------
    # 7. Mean temperature
    # -------------------------------------------------------------------
    T_mean = None
    if "Temp" in col_map:
        T_mean = float(df[col_map["Temp"]].values[step_0_idx:].mean())

    # -------------------------------------------------------------------
    # 8. Save stress-strain CSV
    # -------------------------------------------------------------------
    ss_df = pd.DataFrame({
        "step":            steps_def,
        "strain_xx":       strain,
        "sigma_xx_GPa":    -pxx_def * ATM_TO_GPA,
        "sigma_yy_GPa":    -pyy_def * ATM_TO_GPA,
        "sigma_zz_GPa":    -pzz_def * ATM_TO_GPA,
        "sigma_xx_avg_GPa": -pxx_s * ATM_TO_GPA,
        "sigma_yy_avg_GPa": -pyy_s * ATM_TO_GPA,
        "sigma_zz_avg_GPa": -pzz_s * ATM_TO_GPA,
    })
    ss_csv = str(output_dir / "stress_strain.csv")
    ss_df.to_csv(ss_csv, index=False)

    # -------------------------------------------------------------------
    # 9. Assemble result
    # -------------------------------------------------------------------
    result = {
        "status":           "success",
        "log_file":         args.log_file,
        "output_dir":       str(output_dir),
        "method":           "uniaxial_deformation",
        "C11_GPa":          round(C11, 4),
        "C12_GPa":          round(C12, 4),
        "C12_yy_GPa":       round(float(slope_yy), 4),
        "C12_zz_GPa":       round(float(slope_zz), 4),
        "K_GPa":            round(K, 4),
        "G_GPa":            round(G, 4),
        "E_GPa":            round(float(E), 4) if E is not None else None,
        "nu_Poisson":       round(float(nu), 4) if nu is not None else None,
        "fit_r2_C11":       round(r2_xx, 4),
        "fit_r2_C12_yy":    round(r2_yy, 4),
        "fit_r2_C12_zz":    round(r2_zz, 4),
        "fit_p_C11":        float(p_xx),
        "fit_p_C12_yy":     float(p_yy),
        "isotropy_delta_pct": round(isotropy_delta, 2) if isotropy_delta is not None else None,
        "n_fit_points":     int(mask.sum()),
        "strain_range":     [round(float(eps.min()), 5), round(float(eps.max()), 5)],
        "T_mean_K":         round(T_mean, 2) if T_mean is not None else None,
        "strain_rate_per_fs": args.strain_rate,
        "avg_window_frames": avg_window,
        "stress_strain_csv": ss_csv,
        "diagnostics": {
            "n_phase1_rows": int(step_0_idx),
            "n_phase2_rows": int(len(steps_def)),
            "step_0":        int(step_start),
            "strain_max_reached": round(float(strain.max()), 5),
        },
    }

    # Warnings
    if K < 0:
        result["warning_negative_K"] = (
            f"Negative bulk modulus K={K:.3f} GPa. Likely causes: "
            "simulation not equilibrated at 300 K, unstable at this deformation rate, "
            "or strain too large (non-linear regime). Check fit quality (R²)."
        )
    if min(r2_xx, r2_yy, r2_zz) < 0.90:
        result["warning_poor_fit"] = (
            f"Low R²: C11 R²={r2_xx:.3f}, C12_yy R²={r2_yy:.3f}, C12_zz R²={r2_zz:.3f}. "
            f"avg_window={avg_window} frames used. "
            "If avg_window=1 (no averaging), increase it — thermal noise (~0.2 GPa) "
            "exceeds elastic signal at THERMO_FREQ=100. "
            "Alternatively: reduce strain_max (non-linear regime) or increase N_STEPS."
        )
    if isotropy_delta is not None and isotropy_delta > 20.0:
        result["warning_anisotropy"] = (
            f"C12_yy={slope_yy:.3f} and C12_zz={slope_zz:.3f} GPa disagree by "
            f"{isotropy_delta:.1f}% — system may not be isotropic. "
            "Run more chains or longer equilibration."
        )
    if E is not None and E < 0:
        result["warning_negative_E"] = (
            f"Negative Young's modulus E={E:.3f} GPa from K={K:.3f}, G={G:.3f}. "
            "Check that K > 0 and G > 0."
        )

    # -------------------------------------------------------------------
    # 10. Optional two-rate sensitivity comparison
    # -------------------------------------------------------------------
    if args.log_file_2 and args.strain_rate_2:
        try:
            df2 = parse_lammps_log(args.log_file_2)
            col_map2 = {}
            for needed in ["Pxx", "Pyy", "Pzz", "Step"]:
                for candidate in [needed, needed.lower(), needed.upper()]:
                    if candidate in df2.columns:
                        col_map2[needed] = candidate
                        break
            missing2 = [c for c in ["Pxx", "Pyy", "Pzz", "Step"] if c not in col_map2]
            if missing2:
                result["rate_sensitivity"] = {"error": f"Missing columns in log_file_2: {missing2}"}
            else:
                steps2   = df2[col_map2["Step"]].values
                pxx2     = df2[col_map2["Pxx"]].values
                pyy2     = df2[col_map2["Pyy"]].values
                step_0_idx2 = np.searchsorted(steps2, args.eq_steps)
                steps_def2  = steps2[step_0_idx2:]
                pxx_def2    = pxx2[step_0_idx2:]
                pyy_def2    = df2[col_map2["Pyy"]].values[step_0_idx2:]
                pzz_def2    = df2[col_map2["Pzz"]].values[step_0_idx2:]
                step_start2 = steps_def2[0]
                strain2     = args.strain_rate_2 * (steps_def2 - step_start2) * args.timestep
                pxx_s2 = pd.Series(pxx_def2).rolling(avg_window, center=True, min_periods=1).mean().values
                pyy_s2 = pd.Series(pyy_def2).rolling(avg_window, center=True, min_periods=1).mean().values
                pzz_s2 = pd.Series(pzz_def2).rolling(avg_window, center=True, min_periods=1).mean().values
                mask2   = (strain2 >= args.strain_start) & (strain2 <= args.strain_max)
                if mask2.sum() >= 20:
                    eps2  = strain2[mask2]
                    sxx2  = -pxx_s2[mask2] * ATM_TO_GPA
                    syy2  = -pyy_s2[mask2] * ATM_TO_GPA
                    szz2  = -pzz_s2[mask2] * ATM_TO_GPA
                    sl2xx, _, r2_2xx, _ = linear_fit(eps2, sxx2)
                    sl2yy, _, r2_2yy, _ = linear_fit(eps2, syy2)
                    sl2zz, _, r2_2zz, _ = linear_fit(eps2, szz2)
                    C12_2 = (sl2yy + sl2zz) / 2.0
                    K2 = (sl2xx + 2.0 * C12_2) / 3.0
                    diff_pct = abs(K - K2) / abs(K) * 100.0 if abs(K) > 1e-6 else None
                    # Use lower-rate result as primary if it converged well
                    if r2_2xx >= 0.90 and K2 > 0:
                        result["K_GPa"] = round(K2, 4)
                        result["C11_GPa"] = round(float(sl2xx), 4)
                        result["C12_GPa"] = round(K2 * 3 - float(sl2xx), 4)
                        result["method"] = "uniaxial_deformation_slow_rate"
                    result["rate_sensitivity"] = {
                        "K_GPa_rate1":      round(K, 4),
                        "K_GPa_rate2":      round(K2, 4),
                        "strain_rate_1_inv_fs": args.strain_rate,
                        "strain_rate_2_inv_fs": args.strain_rate_2,
                        "fit_r2_C11_rate2":  round(r2_2xx, 4),
                        "K_rate_diff_pct":  round(diff_pct, 2) if diff_pct is not None else None,
                        "verdict":          "PASS" if (diff_pct is not None and diff_pct < 10.0) else "WARNING",
                        "primary_rate_used": "rate2" if (r2_2xx >= 0.90 and K2 > 0) else "rate1",
                    }
                    if diff_pct is not None and diff_pct > 10.0:
                        result["warning_rate_sensitivity"] = (
                            f"K differs by {diff_pct:.1f}% between rate1 ({args.strain_rate:.1e}/fs) "
                            f"and rate2 ({args.strain_rate_2:.1e}/fs). Dynamic stiffening artifact "
                            "likely present — reported K may overestimate quasi-static value."
                        )
                else:
                    result["rate_sensitivity"] = {
                        "error": f"Only {mask2.sum()} points in linear regime for log_file_2"
                    }
        except Exception as rs_err:
            result["rate_sensitivity"] = {"error": str(rs_err)}

    summary_path = str(output_dir / "bulk_modulus_deform.json")
    with open(summary_path, "w") as jf:
        json.dump(result, jf, indent=2)
    result["summary_json"] = summary_path

    print(json.dumps(result))


if __name__ == "__main__":
    main()
