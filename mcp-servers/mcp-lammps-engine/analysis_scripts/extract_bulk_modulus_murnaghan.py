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
# Credibility checks (monotonicity, leave-one-out, fluctuation cross-check)
# ---------------------------------------------------------------------------

def leave_one_out_refit(volumes_sorted, pressures_sorted, pressures_atm_sorted,
                         baseline_B0, baseline_B0_prime):
    """Drop each pressure point in turn and refit. Detects a single influential
    point carrying the fit (the failure mode a too-narrow pressure span produces)."""
    rows = []
    n = len(volumes_sorted)
    neg_idx = int(np.argmin(pressures_atm_sorted))
    for i in range(n):
        V_sub = volumes_sorted[:i] + volumes_sorted[i + 1:]
        P_sub = pressures_sorted[:i] + pressures_sorted[i + 1:]
        popt, _, r2, converged = fit_murnaghan(V_sub, P_sub)
        if converged:
            B0, B0p, _ = popt
        else:
            B0, B0p, r2 = None, None, None
        rows.append({
            "dropped_pressure_atm": pressures_atm_sorted[i],
            "is_tension_point": (i == neg_idx),
            "converged": converged,
            "B0_GPa": round(float(B0), 4) if B0 is not None else None,
            "B0_prime": round(float(B0p), 4) if B0p is not None else None,
            "r_squared": round(float(r2), 6) if r2 is not None else None,
            "dB0_GPa_vs_baseline": round(float(B0) - baseline_B0, 4) if B0 is not None else None,
            "dB0_prime_vs_baseline": round(float(B0p) - baseline_B0_prime, 4) if B0p is not None else None,
        })
    return rows


def detect_anomalous_points(volumes_sorted, pressures_atm_sorted, vol_stds_sorted):
    """Flag pressure points showing cavitation/instability signatures, using only
    data already computed for the fit (no extra simulation cost):
      (a) vol_std far above the other points' typical spread -- a cavitating or
          otherwise unsettled cell shows anomalously large volume fluctuation at
          a fixed target pressure.
      (b) an adjacent |dV/dP| interval far outside the other intervals' typical
          magnitude -- formalizes the manual kink check used by hand on this
          project's pressure series before this function existed.

    Points are indexed in the same order as the arrays passed in (the existing
    descending-volume / ascending-pressure sort `main()` already uses). Purely
    diagnostic annotation -- select_stable_window() is the actual arbiter of
    which points to keep; this only supplies human-readable exclusion reasons.

    Returns {index: [reason, ...]} for flagged points only.
    """
    n = len(volumes_sorted)
    flags = {i: [] for i in range(n)}

    if n >= 3:
        stds = np.array(vol_stds_sorted, dtype=float)
        for i in range(n):
            other_median = np.median(np.delete(stds, i))
            if other_median > 0 and stds[i] > 3.0 * other_median:
                flags[i].append(
                    f"vol_std={stds[i]:.2f} is >3x the other points' median "
                    f"({other_median:.2f}) -- signature of an unsettled/cavitating cell."
                )

    if n >= 4:
        dV = np.diff(np.asarray(volumes_sorted, dtype=float))
        dP = np.diff(np.asarray(pressures_atm_sorted, dtype=float))
        with np.errstate(divide="ignore", invalid="ignore"):
            slopes = np.abs(dV / dP)
        for k in range(len(slopes)):
            others = np.delete(slopes, k)
            finite_others = others[np.isfinite(others)]
            if len(finite_others) == 0 or not np.isfinite(slopes[k]):
                continue
            other_median = float(np.median(finite_others))
            if other_median > 0 and slopes[k] > 3.0 * other_median:
                msg = (
                    f"|dV/dP| between points {k} and {k + 1} is {slopes[k]:.4g}, "
                    f">3x the other intervals' median ({other_median:.4g}) -- "
                    "possible cavitation/discontinuity in this interval."
                )
                flags[k].append(msg)
                flags[k + 1].append(msg)

    return {i: r for i, r in flags.items() if r}


def select_stable_window(volumes_sorted, pressures_sorted_GPa, pressures_atm_sorted,
                          anomalous_flags, min_points=5, b0_plateau_pct=5.0,
                          r2_acceptable=0.999, r2_improvement_eps=1e-4):
    """Search trimmed sub-windows of the full sorted ladder (dropping points from
    the tension/low-pressure end first, then the compression/high-pressure end --
    tension is the flagged risk side) for a window that fits meaningfully BETTER
    than the untrimmed ladder.

    Selection is driven by fit quality (r_squared), not a hard "must exclude every
    flagged point" gate -- a plain converged+monotonic check is too weak on its
    own: curve_fit will happily converge on a ladder with one contaminated point,
    it just produces a biased B0 rather than failing outright, so a gate that only
    checks convergence never has a reason to trim. Concretely:
      - If the untrimmed fit already has r_squared >= r2_acceptable (this
        project's existing acceptance bar, per guides/BM_ANALYSIS.md), keep it
        untrimmed even if a point got flagged -- a well-fit, genuinely curved EOS
        naturally shows a bigger dV/dP over its widest interval, which can trip
        the interval heuristic in detect_anomalous_points() without anything
        actually being wrong (confirmed against the real POXI/PEG1-4 archive,
        where all four already-clean 5-point wide ladders trip that heuristic on
        their tension-to-zero interval).
      - Otherwise, search trims for whichever most improves r_squared over the
        untrimmed fit (by more than r2_improvement_eps); among meaningfully
        improved trims, prefer ones that exclude every flagged point, then the
        smallest trim, then the best r_squared.
      - If no trim converges+is volume-monotonic at all, fall back to the
        untrimmed fit's own (possibly poor) result -- existing
        fit_converged/volume_monotonic warnings carry the signal instead.

    `plateau_confirmed` additionally checks that the NEXT larger trim doesn't
    move B0 by more than b0_plateau_pct -- the standard stable-fit-window
    signature (once the contaminating point(s) are excluded, further trimming of
    genuinely good points should barely move the answer).
    """
    n = len(volumes_sorted)
    # Never require more points than exist -- with only 3-4 points to begin with
    # (the script's own minimum), the full window is the only option and must
    # still be evaluated on its own already-known fit, not marked unconverged.
    min_points = min(min_points, n)
    flagged_idx = set(anomalous_flags.keys())

    def _fit_window(lo, hi):
        V, P = volumes_sorted[lo:hi], pressures_sorted_GPa[lo:hi]
        if len(V) < min_points:
            return None
        mono = all(P[i + 1] > P[i] for i in range(len(P) - 1))
        popt, pcov, r2, converged = fit_murnaghan(V, P)
        B0_sem = None
        if converged and pcov is not None:
            try:
                B0_sem = float(np.sqrt(np.diag(pcov))[0])
            except Exception:
                B0_sem = None
        return {
            "lo": lo, "hi": hi, "n_points": len(V),
            "converged": converged,
            "B0_GPa": float(popt[0]) if converged else None,
            "B0_prime": float(popt[1]) if converged else None,
            "V0_A3": float(popt[2]) if converged else None,
            "B0_sem_GPa": B0_sem,
            "r_squared": float(r2) if r2 is not None else None,
            "volume_monotonic": mono,
            "excluded_idx": set(range(0, lo)) | set(range(hi, n)),
            "trim_total": lo + (n - hi),
        }

    candidates = []
    max_trim = max(0, n - min_points)
    for t_lo in range(0, max_trim + 1):
        for t_hi in range(0, max_trim - t_lo + 1):
            fit = _fit_window(t_lo, n - t_hi)
            if fit is not None:
                candidates.append(fit)

    good = [c for c in candidates if c["converged"] and c["volume_monotonic"]]

    if not good:
        full = _fit_window(0, n) or {
            "lo": 0, "hi": n, "n_points": n, "converged": False, "B0_GPa": None,
            "B0_prime": None, "V0_A3": None, "B0_sem_GPa": None, "r_squared": None,
            "volume_monotonic": False, "excluded_idx": set(), "trim_total": 0,
        }
        full["plateau_confirmed"] = None
        full["selection_note"] = (
            "No window (trimmed or full) converged with volume_monotonic=True -- "
            "falling back to the full ladder's own fit; existing "
            "fit_converged/volume_monotonic warnings carry the signal instead."
        )
        return full

    full_window = next((c for c in good if c["trim_total"] == 0), None)
    baseline_r2 = full_window["r_squared"] if full_window and full_window["r_squared"] is not None else -1.0

    if full_window is not None and baseline_r2 >= r2_acceptable:
        selected = dict(full_window)
        selected["plateau_confirmed"] = True
        flag_note = (f"point(s) {sorted(flagged_idx)} were flagged"
                     if flagged_idx else "no points were flagged")
        selected["selection_note"] = (
            f"Untrimmed fit already has r_squared={baseline_r2:.5f} >= {r2_acceptable} "
            f"-- no trimming applied even though {flag_note} (a genuinely curved EOS "
            "can trip the interval heuristic without a real problem)."
        )
        return selected

    improved = [c for c in good if c["trim_total"] > 0
                and c["r_squared"] is not None
                and c["r_squared"] > baseline_r2 + r2_improvement_eps]

    if not improved:
        selected = dict(full_window) if full_window is not None else dict(
            sorted(good, key=lambda c: -(c["r_squared"] if c["r_squared"] is not None else -1))[0])
        selected["plateau_confirmed"] = True
        selected["selection_note"] = (
            f"No trim improved r_squared over the untrimmed fit (r_squared={baseline_r2:.5f}) "
            "-- keeping all points."
        )
        return selected

    improved_excluding_flags = [c for c in improved if flagged_idx <= c["excluded_idx"]]
    pool = improved_excluding_flags or improved
    pool.sort(key=lambda c: (c["trim_total"], -(c["r_squared"] if c["r_squared"] is not None else -1)))
    selected = dict(pool[0])

    larger = [c for c in good if c["trim_total"] > selected["trim_total"]]
    plateau_confirmed = True
    if larger:
        nxt = min(larger, key=lambda c: c["trim_total"])
        if selected["B0_GPa"] and nxt["B0_GPa"] is not None:
            pct = abs(nxt["B0_GPa"] - selected["B0_GPa"]) / abs(selected["B0_GPa"]) * 100
            if pct > b0_plateau_pct:
                plateau_confirmed = False
    selected["plateau_confirmed"] = plateau_confirmed
    excludes_all_flags = flagged_idx <= selected["excluded_idx"]
    selected["selection_note"] = (
        f"Trim={selected['trim_total']}: r_squared improved from {baseline_r2:.5f} "
        f"(untrimmed) to {selected['r_squared']:.5f}"
        + (" and excludes every flagged point." if excludes_all_flags else
           " (could not exclude every flagged point at this ladder length).")
    )
    return selected


def compute_fluctuation_cross_check(npt_prod_log, eq_fraction):
    """Independent K estimate (NPT volume fluctuation, Wu 2020 B_dyn) from a
    separate equilibration log, for cross-checking the Murnaghan fit. Never
    raises — returns None on any missing/short/unreadable log."""
    try:
        from extract_bulk_modulus import compute_bulk_modulus as _compute_K_fluct
        df = parse_lammps_log(npt_prod_log)
        vol_col = next((c for c in ["Volume", "Vol", "vol"] if c in df.columns), None)
        temp_col = next((c for c in ["Temp", "temp", "Temperature"] if c in df.columns), None)
        if vol_col is None or temp_col is None:
            return None
        n = len(df)
        prod = df.iloc[int(n * (1.0 - eq_fraction)):]
        if len(prod) < 50:
            return None
        K_GPa, _, _ = _compute_K_fluct(prod[vol_col].values, float(prod[temp_col].mean()))
        return K_GPa
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Plot
# ---------------------------------------------------------------------------

def plot_murnaghan(volumes_A3, pressures_GPa, popt, fit_converged, r2, graphs_dir,
                    excluded_idx=None, selected_popt=None, selected_r2=None):
    apply_style()
    fig, ax = plt.subplots()
    excluded_idx = excluded_idx or set()
    kept = [i for i in range(len(volumes_A3)) if i not in excluded_idx]
    excl = sorted(excluded_idx)
    if kept:
        ax.scatter([volumes_A3[i] for i in kept], [pressures_GPa[i] for i in kept],
                   color='steelblue', zorder=5, label='NPT mean volumes (kept)')
    if excl:
        ax.scatter([volumes_A3[i] for i in excl], [pressures_GPa[i] for i in excl],
                   color='gray', marker='x', zorder=5, label='excluded (screened)')
    V_fit = np.linspace(min(volumes_A3) * 0.98, max(volumes_A3) * 1.02, 300)
    if selected_popt is not None:
        P_fit = murnaghan_eos(V_fit, *selected_popt)
        B0, B0_prime, V0 = selected_popt
        label = f'Selected-window fit  B0={B0:.3f} GPa  B0\'={B0_prime:.2f}'
        if selected_r2 is not None:
            label += f'  R²={selected_r2:.5f}'
        ax.plot(V_fit, P_fit, color='tomato', lw=1.5, label=label)
    elif fit_converged and popt is not None:
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
    parser.add_argument("--npt_prod_log", default=None,
                        help="Optional separate NPT production log for a fluctuation-based "
                             "K cross-check, embedded in this same result (no separate tool call).")
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

    volume_monotonic = all(
        pressures_sorted[i + 1] > pressures_sorted[i]
        for i in range(len(pressures_sorted) - 1)
    )

    # -------------------------------------------------------------------
    # 2. Fit Murnaghan EOS
    # -------------------------------------------------------------------
    popt, pcov, r2, converged = fit_murnaghan(volumes_sorted, pressures_sorted)

    warnings = []
    if not volume_monotonic:
        warnings.append(
            "Pressure series is not monotonic in volume — sorting by mean volume did not "
            "reproduce ascending pressure order, meaning at least one point's mean volume is "
            "out of sequence (likely inadequate equilibration at that pressure)."
        )
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
    # 2b. Leave-one-out refit (converged fits only)
    # -------------------------------------------------------------------
    loo_results = None
    loo_n_converged = None
    if converged:
        loo_results = leave_one_out_refit(
            volumes_sorted, pressures_sorted, pressures_atm_sorted, B0_GPa, B0_prime
        )
        loo_n_converged = sum(1 for r in loo_results if r["converged"])
        deltas = [abs(r["dB0_GPa_vs_baseline"]) for r in loo_results
                  if r["dB0_GPa_vs_baseline"] is not None]
        if deltas and B0_GPa:
            max_dB0_pct = max(deltas) / abs(B0_GPa) * 100
            if max_dB0_pct > 10.0:
                warnings.append(
                    f"Leave-one-out refit: dropping one pressure point shifts B0 by up to "
                    f"{max_dB0_pct:.1f}% (>10%) — the fit is not robust to a single point; "
                    "consider widening the pressure range."
                )

    # -------------------------------------------------------------------
    # 2c. Anomaly detection + automated stable-window selection
    # -------------------------------------------------------------------
    anomalous_flags = detect_anomalous_points(volumes_sorted, pressures_atm_sorted, vol_stds_sorted)
    window = select_stable_window(volumes_sorted, pressures_sorted, pressures_atm_sorted,
                                   anomalous_flags)
    excluded_idx = window["excluded_idx"]
    excluded_points = [
        {
            "pressure_atm": pressures_atm_sorted[i],
            "reasons": anomalous_flags.get(i, ["excluded to reach a converged, "
                                                "volume-monotonic window"]),
        }
        for i in sorted(excluded_idx)
    ]
    if excluded_points:
        warnings.append(
            f"Automated screening excluded {len(excluded_points)} of "
            f"{len(volumes_sorted)} pressure point(s) from the primary fit "
            f"(see excluded_points/selected_window) -- see all_points_fit for "
            "the unscreened comparison."
        )
    if window.get("plateau_confirmed") is False:
        warnings.append(
            "Stable-window selection: the next-larger trim still moves B0 by "
            ">5% -- the selected window may not be fully stable; inspect "
            "excluded_points and the murnaghan_eos.png plot."
        )

    # Primary (screened) fit values -- these become the top-level result.
    primary_converged = window["converged"]
    primary_B0_GPa = window["B0_GPa"]
    primary_B0_prime = window["B0_prime"]
    primary_V0_A3 = window["V0_A3"]
    primary_r2 = window["r_squared"]
    primary_B0_sem_GPa = window.get("B0_sem_GPa")
    primary_method = "murnaghan" if primary_converged else method

    # -------------------------------------------------------------------
    # 2d. Fluctuation cross-check (optional) -- compares against the SELECTED
    # WINDOW's B0, not the raw all-points B0, per this session's screening fix.
    # -------------------------------------------------------------------
    fluctuation_bulk_modulus_GPa = None
    fluctuation_divergence_pct = None
    if args.npt_prod_log:
        fluctuation_bulk_modulus_GPa = compute_fluctuation_cross_check(
            args.npt_prod_log, args.eq_fraction
        )
        compare_B0 = primary_B0_GPa if primary_B0_GPa is not None else B0_GPa
        if fluctuation_bulk_modulus_GPa is not None and compare_B0:
            fluctuation_divergence_pct = (
                abs(compare_B0 - fluctuation_bulk_modulus_GPa) / abs(compare_B0) * 100
            )
            if fluctuation_divergence_pct > 15.0:
                warnings.append(
                    f"Murnaghan B0={compare_B0:.3f} GPa (selected window) vs fluctuation K="
                    f"{fluctuation_bulk_modulus_GPa:.3f} GPa diverge by "
                    f"{fluctuation_divergence_pct:.1f}% (>15%). Expected/benign for rubbery "
                    "classes (fluctuation overestimates rubbery K); investigate for glassy classes."
                )

    # -------------------------------------------------------------------
    # 3. Assemble result -- top-level fields reflect the SELECTED WINDOW
    # (the screened, primary answer); all_points_fit preserves the original
    # unscreened fit for continuity/comparison/audit.
    # -------------------------------------------------------------------
    result = {
        "status": "success",
        "method": primary_method,
        "fit_converged": primary_converged,
        "B0_GPa": round(float(primary_B0_GPa), 4) if primary_B0_GPa is not None else None,
        "bulk_modulus_GPa": round(float(primary_B0_GPa), 4)
            if primary_B0_GPa is not None else None,   # alias for generate_run_summary
        "B0_sem_GPa": round(primary_B0_sem_GPa, 4) if primary_B0_sem_GPa is not None else None,
        "bulk_modulus_sem_GPa": round(primary_B0_sem_GPa, 4) if primary_B0_sem_GPa is not None else None,
        "B0_prime": round(float(primary_B0_prime), 4) if primary_B0_prime is not None else None,
        "V0_A3": round(float(primary_V0_A3), 2) if primary_V0_A3 is not None else None,
        "r_squared": round(float(primary_r2), 6) if primary_r2 is not None else None,
        "n_points": window["n_points"],
        "pressures_atm": [pressures_atm_sorted[i] for i in range(len(volumes_sorted)) if i not in excluded_idx],
        "pressures_GPa": [round(pressures_sorted[i], 6) for i in range(len(volumes_sorted)) if i not in excluded_idx],
        "volumes_A3": [round(volumes_sorted[i], 2) for i in range(len(volumes_sorted)) if i not in excluded_idx],
        "vol_stds_A3": [round(vol_stds_sorted[i], 2) for i in range(len(volumes_sorted)) if i not in excluded_idx],
        "n_prod_rows": n_prod_sorted,
        "log_files": log_files_sorted,
        "eq_fraction": args.eq_fraction,
        "output_dir": str(output_dir),
        "volume_monotonic": window["volume_monotonic"],
        "loo_results": loo_results,
        "loo_n_converged": loo_n_converged,
        "fluctuation_bulk_modulus_GPa": round(fluctuation_bulk_modulus_GPa, 4)
            if fluctuation_bulk_modulus_GPa is not None else None,
        "fluctuation_divergence_pct": round(fluctuation_divergence_pct, 2)
            if fluctuation_divergence_pct is not None else None,
        "anomalous_points": anomalous_flags,
        "excluded_points": excluded_points,
        "selected_window": {
            "trim_total": window["trim_total"],
            "n_points": window["n_points"],
            "plateau_confirmed": window.get("plateau_confirmed"),
            "selection_note": window.get("selection_note"),
        },
        "all_points_fit": {
            "method": method,
            "fit_converged": converged,
            "B0_GPa": round(float(B0_GPa), 4) if B0_GPa is not None else None,
            "B0_prime": round(float(B0_prime), 4) if B0_prime is not None else None,
            "V0_A3": round(float(V0_A3), 2) if V0_A3 is not None else None,
            "r_squared": round(float(r2), 6) if r2 is not None else None,
            "volume_monotonic": volume_monotonic,
            "n_points": len(volumes_sorted),
            "pressures_atm": pressures_atm_sorted,
        },
        "warnings": warnings,
    }

    # -------------------------------------------------------------------
    # 4. Plot -- scatter shows kept vs. screened-out points; fit curve is the
    # selected window's (falls back to the all-points fit if nothing converged).
    # -------------------------------------------------------------------
    fig_path = None
    try:
        plot_popt = (primary_B0_GPa, primary_B0_prime, primary_V0_A3) if primary_converged else popt
        plot_murnaghan(volumes_sorted, pressures_sorted, popt, converged, r2, graphs_dir,
                       excluded_idx=excluded_idx, selected_popt=plot_popt if primary_converged else None,
                       selected_r2=primary_r2 if primary_converged else None)
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
