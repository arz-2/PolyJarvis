#!/usr/bin/env python3
"""
extract_bulk_modulus_murnaghan.py — Extract isothermal bulk modulus via
Murnaghan equation-of-state fit to a multi-pressure NPT series.

Method:
    Run N NPT simulations at constant pressures P_1 … P_N (each at the same T).
    Measure mean equilibrium volume <V>_i at each pressure.
    Fit the Murnaghan EOS:
        P = (B0/B0') * [(V0/V)^B0' - 1]
    to the (V_i, P_i) data.  Free parameters: B0 (GPa), B0', V0 (Å³).

    Advantages over single-point volume-fluctuation (B_dyn):
      - Barostat-independent: each V_i is an equilibrium average, not a
        fluctuation-based estimate.  P_DAMP has no effect on the result.
      - Captures EOS nonlinearity (B0' ~ 7–11 for polymer melts) that makes
        the linear P-vs-ln V approximation fail (R² ~ 0.97 for soft melts).

Fallback:
    If scipy.optimize.curve_fit fails to converge, falls back to
    linear regression of P vs ln V with method="linear_fallback" and a warning.

Output:
    bulk_modulus_murnaghan.json  — B0_GPa, B0_prime, V0_A3, r_squared, …
    murnaghan_eos.png            — scatter of (V, P) with Murnaghan fit curve

Aliases for generate_run_summary.py compatibility:
    bulk_modulus_GPa  = B0_GPa
    bulk_modulus_sem_GPa = B0_sem_GPa (if available from bootstrap; else None)

Usage:
    python extract_bulk_modulus_murnaghan.py \\
        --log_files /path/P1.log /path/P2.log /path/P3.log \\
        --pressures_atm 1 100 300 600 1000 \\
        --output_dir /path/to/raw/ \\
        --graphs_dir /path/to/graphs/

References:
    Murnaghan, F.D. Proc. Natl. Acad. Sci. USA 30, 244 (1944)
    Birch, F. Phys. Rev. 71, 809 (1947)  [see also third-order Birch-Murnaghan]
    Wu, J. J. Phys. Chem. B 2020, 124, 10811 — polymer EOS context
"""

import argparse
import json
import sys
import numpy as np
from pathlib import Path
from scipy import stats as sp_stats
from scipy.optimize import curve_fit

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from plot_style import apply_style, save_fig
from analysis_utils import parse_lammps_log


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ATM_TO_PA  = 101325.0
PA_TO_GPA  = 1e-9
ATM_TO_GPA = ATM_TO_PA * PA_TO_GPA


# ---------------------------------------------------------------------------
# LAMMPS log parser (shared pattern across analysis scripts)
# ---------------------------------------------------------------------------


def extract_mean_volume(log_path, eq_fraction):
    """Parse log, discard first (1-eq_fraction) rows, return mean Volume (Å³)."""
    df = parse_lammps_log(log_path)
    vol_col = None
    for candidate in ["Volume", "Vol", "vol"]:
        if candidate in df.columns:
            vol_col = candidate
            break
    if vol_col is None:
        raise ValueError(
            f"No volume column in {log_path}. Available: {list(df.columns)}"
        )
    n = len(df)
    n_discard = int(n * (1.0 - eq_fraction))
    prod = df.iloc[n_discard:]
    if len(prod) < 10:
        raise ValueError(
            f"Only {len(prod)} production rows in {log_path} after "
            f"discarding {n_discard} burn-in rows (eq_fraction={eq_fraction})."
        )
    return float(prod[vol_col].mean()), float(prod[vol_col].std()), len(prod)


# ---------------------------------------------------------------------------
# Murnaghan EOS
# ---------------------------------------------------------------------------

def murnaghan_eos(V, B0, B0_prime, V0):
    """P [GPa] = (B0/B0') * [(V0/V)^B0' - 1]"""
    return (B0 / B0_prime) * ((V0 / V) ** B0_prime - 1.0)


def fit_murnaghan(volumes_A3, pressures_GPa):
    """
    Fit Murnaghan EOS to (V, P) data.  Returns (popt, pcov, r_squared, converged).
    Seed: B0=1 GPa, B0'=7, V0=mean(V).
    """
    V0_seed = float(np.mean(volumes_A3))
    p0 = [1.0, 7.0, V0_seed]
    # Bounds: B0 > 0, B0' in [1, 30], V0 in [0.5*mean, 2*mean]
    bounds = ([0.01, 1.0, 0.5 * V0_seed], [500.0, 30.0, 2.0 * V0_seed])
    try:
        popt, pcov = curve_fit(
            murnaghan_eos,
            volumes_A3,
            pressures_GPa,
            p0=p0,
            bounds=bounds,
            maxfev=10000,
        )
        B0, B0_prime, V0 = popt
        P_fit = murnaghan_eos(np.array(volumes_A3), *popt)
        ss_res = np.sum((np.array(pressures_GPa) - P_fit) ** 2)
        ss_tot = np.sum((np.array(pressures_GPa) - np.mean(pressures_GPa)) ** 2)
        r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
        return popt, pcov, float(r2), True
    except Exception:
        return None, None, None, False


def fit_linear_fallback(volumes_A3, pressures_GPa):
    """Linear P vs ln V fallback when Murnaghan fails to converge."""
    lnV = np.log(volumes_A3)
    slope, intercept, r_val, p_val, _ = sp_stats.linregress(lnV, pressures_GPa)
    B0_linear = float(-slope)   # units already GPa (P in GPa, ln V dimensionless)
    return B0_linear, float(r_val ** 2)


# ---------------------------------------------------------------------------
# Plot
# ---------------------------------------------------------------------------

def plot_murnaghan(volumes_A3, pressures_GPa, popt, fit_converged, r2, graphs_dir):
    apply_style()
    fig, ax = plt.subplots()
    ax.scatter(volumes_A3, pressures_GPa, color='steelblue', zorder=5,
               label='NPT mean volumes')
    V_fit = np.linspace(min(volumes_A3) * 0.98, max(volumes_A3) * 1.02, 300)
    if fit_converged and popt is not None:
        P_fit = murnaghan_eos(V_fit, *popt)
        B0, B0_prime, V0 = popt
        ax.plot(V_fit, P_fit, color='tomato', lw=1.5,
                label=f'Murnaghan fit  B0={B0:.3f} GPa  B0\'={B0_prime:.2f}  R²={r2:.5f}')
    ax.set_xlabel('Volume (Å³)')
    ax.set_ylabel('Pressure (GPa)')
    ax.set_title('Murnaghan EOS fit')
    ax.legend()
    save_fig(fig, str(graphs_dir / 'murnaghan_eos.png'))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Extract isothermal bulk modulus via Murnaghan EOS fit "
                    "to a multi-pressure NPT series."
    )
    parser.add_argument("--log_files", nargs="+", required=True,
                        help="LAMMPS log files, one per pressure point (space-separated).")
    parser.add_argument("--pressures_atm", nargs="+", type=float, required=True,
                        help="Target pressures in atm, same order as --log_files.")
    parser.add_argument("--output_dir", required=True,
                        help="Output directory for JSON and CSV.")
    parser.add_argument("--graphs_dir", default=None,
                        help="Directory for PNG figures (default: <output_dir>/figures).")
    parser.add_argument("--eq_fraction", type=float, default=0.5,
                        help="Fraction of each log used as production window. Default 0.5.")
    args = parser.parse_args()

    if len(args.log_files) != len(args.pressures_atm):
        print(json.dumps({
            "status": "failed",
            "error": f"--log_files ({len(args.log_files)}) and --pressures_atm "
                     f"({len(args.pressures_atm)}) must have the same length."
        }))
        sys.exit(0)

    if len(args.log_files) < 3:
        print(json.dumps({
            "status": "failed",
            "error": f"At least 3 pressure points required for Murnaghan fit "
                     f"(got {len(args.log_files)})."
        }))
        sys.exit(0)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    graphs_dir = Path(args.graphs_dir) if args.graphs_dir else output_dir / "figures"
    graphs_dir.mkdir(parents=True, exist_ok=True)

    # -------------------------------------------------------------------
    # 1. Extract mean volume at each pressure
    # -------------------------------------------------------------------
    volumes_A3 = []
    vol_stds = []
    n_prod_list = []
    errors = []
    for log_path, p_atm in zip(args.log_files, args.pressures_atm):
        try:
            v_mean, v_std, n_prod = extract_mean_volume(log_path, args.eq_fraction)
            volumes_A3.append(v_mean)
            vol_stds.append(v_std)
            n_prod_list.append(n_prod)
        except Exception as e:
            errors.append(f"{log_path} @ {p_atm} atm: {e}")

    if errors:
        print(json.dumps({
            "status": "failed",
            "error": "Failed to extract volume from one or more logs:\n" + "\n".join(errors)
        }))
        sys.exit(0)

    pressures_GPa = [p * ATM_TO_GPA for p in args.pressures_atm]

    # Sort by ascending volume (descending pressure) for stable fitting
    order = np.argsort(volumes_A3)[::-1]
    volumes_sorted = [volumes_A3[i] for i in order]
    pressures_sorted = [pressures_GPa[i] for i in order]
    pressures_atm_sorted = [args.pressures_atm[i] for i in order]
    log_files_sorted = [args.log_files[i] for i in order]
    n_prod_sorted = [n_prod_list[i] for i in order]
    vol_stds_sorted = [vol_stds[i] for i in order]

    # -------------------------------------------------------------------
    # 2. Fit Murnaghan EOS
    # -------------------------------------------------------------------
    popt, pcov, r2, converged = fit_murnaghan(volumes_sorted, pressures_sorted)

    warnings = []
    if not converged:
        warnings.append(
            "Murnaghan EOS fit did not converge — falling back to linear P vs ln V. "
            "Results are approximate; consider extending NPT runs or checking pressure range."
        )

    if converged:
        B0_GPa, B0_prime, V0_A3 = popt
        method = "murnaghan"
        if r2 < 0.999:
            warnings.append(
                f"Murnaghan fit R²={r2:.5f} < 0.999. Check that NPT runs are fully "
                "equilibrated (increase --eq_fraction or NPT steps) and that the "
                "pressure range is appropriate for this polymer."
            )
        if B0_prime < 4.0 or B0_prime > 20.0:
            warnings.append(
                f"B0'={B0_prime:.2f} is outside the expected range [4, 20] for polymers. "
                "Verify pressure range and equilibration quality."
            )
        # Parameter uncertainties from covariance matrix
        try:
            perr = np.sqrt(np.diag(pcov))
            B0_sem_GPa = float(perr[0])
        except Exception:
            B0_sem_GPa = None
    else:
        # Linear fallback
        B0_GPa, r2 = fit_linear_fallback(volumes_sorted, pressures_sorted)
        B0_prime = None
        V0_A3 = None
        B0_sem_GPa = None
        method = "linear_fallback"

    # -------------------------------------------------------------------
    # 3. Assemble result
    # -------------------------------------------------------------------
    result = {
        "status": "success",
        "method": method,
        "fit_converged": converged,
        "B0_GPa": round(float(B0_GPa), 4),
        "bulk_modulus_GPa": round(float(B0_GPa), 4),   # alias for generate_run_summary
        "B0_sem_GPa": round(B0_sem_GPa, 4) if B0_sem_GPa is not None else None,
        "bulk_modulus_sem_GPa": round(B0_sem_GPa, 4) if B0_sem_GPa is not None else None,
        "B0_prime": round(float(B0_prime), 4) if B0_prime is not None else None,
        "V0_A3": round(float(V0_A3), 2) if V0_A3 is not None else None,
        "r_squared": round(float(r2), 6),
        "n_points": len(volumes_sorted),
        "pressures_atm": pressures_atm_sorted,
        "pressures_GPa": [round(p, 6) for p in pressures_sorted],
        "volumes_A3": [round(v, 2) for v in volumes_sorted],
        "vol_stds_A3": [round(s, 2) for s in vol_stds_sorted],
        "n_prod_rows": n_prod_sorted,
        "log_files": log_files_sorted,
        "eq_fraction": args.eq_fraction,
        "output_dir": str(output_dir),
        "warnings": warnings,
    }

    # -------------------------------------------------------------------
    # 4. Plot
    # -------------------------------------------------------------------
    fig_path = None
    try:
        plot_murnaghan(volumes_sorted, pressures_sorted, popt, converged, r2, graphs_dir)
        fig_path = str(graphs_dir / "murnaghan_eos.png")
    except Exception as pe:
        print(f"  WARNING: murnaghan_eos plot failed: {pe}", flush=True)
    result["murnaghan_eos_fig"] = fig_path

    # -------------------------------------------------------------------
    # 5. Save JSON
    # -------------------------------------------------------------------
    summary_path = str(output_dir / "bulk_modulus_murnaghan.json")
    with open(summary_path, "w") as jf:
        json.dump(result, jf, indent=2)
    result["summary_json"] = summary_path

    print(json.dumps(result))


if __name__ == "__main__":
    main()
