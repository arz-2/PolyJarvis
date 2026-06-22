#!/usr/bin/env python3
"""
extract_tg_multirate.py — Fit Tg vs. cooling-rate trend and attempt
Vogel-Fulcher extrapolation from multi-rate MD Tg sweeps.

Methodology:
~~~~~~~~~~~~
Given N (rate, Tg_MD) pairs, two fits are performed:

1. **Log-linear (primary)**: Tg = a + b * ln(Γ)
   - 2 parameters, always stable.
   - Reports slope b (K per unit ln(K/ns)) and R².
   - Extrapolates to a reference "slow MD rate" (default 5 K/ns):
       Tg_slow = a + b * ln(5.0)
   - This is the recommended screening-validation comparison vs. Ramos 2015
     (who report Tg vs ln(Γ) in their Fig. 3).

2. **Vogel-Fulcher (secondary)**: Tg(Γ) = Tg0 + A / (ln(Γ) + c), c = ln(B)
   - 3 parameters. As Γ → 0, Tg → Tg0.
   - NOTE: Requires ≥ 3 decades of rate coverage for a reliable Tg0.
     With < 2 decades (e.g. rates 10-640 K/ns), the VF Tg0 is poorly
     constrained and the CI can exceed 100 K. A VF result with
     tg0_K_ci95 > 50 K is flagged as CONSTRAINED_POOR.
   - Physical constraints enforced via bounds:
       0 < Tg0 < min(Tg_MD) − 1
       A < 0
       c < ln(min_rate) − 0.1   (singularity cannot be in the data range)

Quality assessment:
  VF quality tiers:
    EXCELLENT  : R² ≥ 0.99, N ≥ 4, span ≥ 2 decades, CI < 50 K
    ACCEPTABLE : R² ≥ 0.95, N ≥ 3, CI < 100 K
    POOR       : R² ≥ 0.90
    FAILED     : curve_fit did not converge / parameters unphysical
  Log-linear R² is always reliable.

Output contract:
  - Prints a JSON summary to stdout as the last line.
  - Writes JSON and optional PNG to --output_dir.
  - Exit 0 on success, non-zero on failure.

References:
  Ramos et al., Macromolecules 48 (2015) 5016–5027  (eq. 8, VF; Fig. 3, log-linear)
  Müller-Plathe, ChemPhysChem 3 (2002) 754–769

Usage:
    python extract_tg_multirate.py \\
        --rates 10 40 160 640 \\
        --tg_values 241.2 255.3 270.1 283.6 \\
        --output_dir /path/to/output
"""

import argparse
import json
import sys
import numpy as np
from pathlib import Path
from scipy.optimize import curve_fit
from scipy.stats import linregress


# ── Models ────────────────────────────────────────────────────────────────────

def vf_model(log_gamma, tg0, a, c):
    """VF: Tg(Γ) = Tg0 + A / (ln(Γ) + c)."""
    return tg0 + a / (log_gamma + c)


def _vf_init_guess(log_rates: np.ndarray, tg_vals: np.ndarray, tg0_guess: float):
    """Analytic initial guess for (tg0, a, c) given assumed tg0."""
    x1, t1 = float(log_rates[0]),  float(tg_vals[0])
    x2, t2 = float(log_rates[-1]), float(tg_vals[-1])
    d1, d2 = t1 - tg0_guess, t2 - tg0_guess
    if abs(d1 - d2) > 1e-9:
        c_guess = (x2 * d2 - x1 * d1) / (d1 - d2)
        a_guess = d1 * (x1 + c_guess)
    else:
        c_guess = x1 - 2.0
        a_guess = d1 * (x1 + c_guess)
    return tg0_guess, a_guess, c_guess


# ── Fitting ───────────────────────────────────────────────────────────────────

def fit_multirate(
    rates: list,
    tg_values: list,
    slow_rate_ref: float = 5.0,
) -> dict:
    """
    Fit log-linear and VF models to (rate, Tg) pairs.

    Returns a dict with all fit results and quality flags.
    """
    rates_arr = np.array(rates, dtype=float)
    tg_arr    = np.array(tg_values, dtype=float)
    n = len(rates_arr)

    if n < 2:
        return {"status": "failed", "error": f"Need ≥ 2 rate points; got {n}"}

    log_rates = np.log(rates_arr)
    span_decades = float(np.log10(rates_arr.max() / rates_arr.min()))

    # ── 1. Log-linear fit (primary) ────────────────────────────────────────
    slope, intercept, r_val, _, _ = linregress(log_rates, tg_arr)
    r2_lin  = float(r_val ** 2)

    # Slope gates — applied before any extrapolation
    slope_gate_pass  = bool(slope > 0)       # negative slope is physically impossible
    flat_rate_regime = bool(abs(slope) < 1.0) # < 1 K/decade → rubbery, extrapolation meaningless

    if not slope_gate_pass:
        # Negative slope: extrapolation would give absurd result (PLA1-type incident).
        # Fall back to the directly measured Tg at the slowest rate.
        tg_slow   = float(tg_arr[int(np.argmin(rates_arr))])
        tg_method = "single_rate_fallback"
    elif flat_rate_regime:
        # Rubbery regime: Tg barely changes with rate; mean is more stable than extrapolation.
        tg_slow   = float(np.mean(tg_arr))
        tg_method = "flat_rate_mean"
    else:
        tg_slow   = float(intercept + slope * np.log(slow_rate_ref))
        tg_method = "loglinear_extrapolation"

    result = {
        "status":                  "success",
        "n_points":                n,
        "rates_K_per_ns":          [float(r) for r in rates],
        "tg_values_K":             [float(t) for t in tg_values],
        "rates_span_decades":      span_decades,
        # Log-linear (primary)
        "loglinear_slope_K":       float(slope),
        "loglinear_intercept_K":   float(intercept),
        "loglinear_r_squared":     r2_lin,
        "tg_at_slow_rate_K":       tg_slow,
        "slow_rate_ref_K_per_ns":  slow_rate_ref,
        "slope_gate_pass":         slope_gate_pass,
        "is_flat_rate_regime":     flat_rate_regime,
        "tg_method":               tg_method,
        # VF fields filled below
        "vf_fit_quality":          "NOT_ATTEMPTED",
    }

    if n < 3:
        result["vf_fit_quality"] = "SKIPPED (N < 3)"
        return result

    # ── 2. VF fit (secondary) ──────────────────────────────────────────────
    tg_span   = float(tg_arr.max() - tg_arr.min())
    tg0_init  = float(tg_arr.min()) - 2.0 * tg_span
    tg0_init  = max(tg0_init, 1.0)        # keep positive
    _, a_0, c_0 = _vf_init_guess(log_rates, tg_arr, tg0_init)

    lo = [1.0,      -1e6,   -1e6]
    hi = [float(tg_arr.min()) - 1.0, 0.0, float(log_rates.min()) - 0.01]

    try:
        popt, pcov = curve_fit(
            vf_model,
            log_rates,
            tg_arr,
            p0=[tg0_init, a_0, c_0],
            bounds=(lo, hi),
            maxfev=100000,
        )
        tg0, a, c = popt
        perr = np.sqrt(np.diag(pcov))
        ci95 = float(1.96 * perr[0])

        predicted = vf_model(log_rates, *popt)
        ss_res = float(np.sum((tg_arr - predicted) ** 2))
        ss_tot = float(np.sum((tg_arr - tg_arr.mean()) ** 2))
        r2_vf  = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")

        # Quality
        if (r2_vf >= 0.99 and n >= 4 and span_decades >= 2.0 and ci95 < 50.0):
            vf_quality = "EXCELLENT"
        elif (r2_vf >= 0.95 and n >= 3 and ci95 < 100.0):
            vf_quality = "ACCEPTABLE"
        elif r2_vf >= 0.90:
            vf_quality = "POOR"
        else:
            vf_quality = "POOR"

        if ci95 > 100.0:
            vf_quality += "_POORLY_CONSTRAINED"

        result.update({
            "tg0_K":              float(tg0),
            "tg0_K_ci95":         ci95,
            "vf_A":               float(a),
            "vf_c":               float(c),
            "vf_B_ns_per_K":      float(np.exp(c)),
            "vf_r_squared":       float(r2_vf),
            "vf_predicted_tg_K":  predicted.tolist(),
            "vf_residuals_K":     (tg_arr - predicted).tolist(),
            "vf_fit_quality":     vf_quality,
        })

    except Exception as exc:
        result["vf_fit_quality"] = "FAILED"
        result["vf_fit_error"]   = str(exc)

    return result


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description="Multi-rate Tg analysis: log-linear + VF")
    p.add_argument("--rates", nargs="+", type=float, required=True,
                   help="Cooling rates in K/ns")
    p.add_argument("--tg_values", nargs="+", type=float, required=True,
                   help="Tg_MD values in K (same order as --rates)")
    p.add_argument("--slow_rate_ref", type=float, default=5.0,
                   help="Reference rate for log-linear Tg extrapolation (K/ns, default 5.0)")
    p.add_argument("--output_dir", default=".", help="Directory for output files")
    p.add_argument("--polymer_name", default="polymer", help="Label for outputs")
    p.add_argument("--no_plot", action="store_true", help="Skip matplotlib figure")
    args = p.parse_args()

    if len(args.rates) != len(args.tg_values):
        out = {"status": "failed",
               "error": f"--rates ({len(args.rates)}) and --tg_values ({len(args.tg_values)}) length mismatch"}
        print(json.dumps(out))
        sys.exit(1)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # A sub-µ reference rate is the DSC-equivalent target (10 K/min = 1.6667e-10 K/ns),
    # not a near-data "slow MD" rate. This switches labels/plot range and avoids the
    # "{:.0f}" formatter printing "0 K/ns" for the tiny DSC rate.
    is_dsc = args.slow_rate_ref < 1e-6
    ref_label = "DSC-equivalent, 10 K/min" if is_dsc else "slow MD"

    result = fit_multirate(args.rates, args.tg_values, slow_rate_ref=args.slow_rate_ref)
    result["polymer_name"] = args.polymer_name
    result["is_dsc_extrapolation"] = is_dsc

    # ── D-06 markdown block ────────────────────────────────────────────────
    if result.get("status") == "success":
        paired     = sorted(zip(args.rates, args.tg_values))
        rate_rows  = "\n".join(f"| {r:.0f} K/ns | {t:.1f} K |" for r, t in paired)
        slope      = result.get("loglinear_slope_K", float("nan"))
        r2_lin     = result.get("loglinear_r_squared", float("nan"))
        tg_slow    = result.get("tg_at_slow_rate_K", float("nan"))
        slow_rate  = result.get("slow_rate_ref_K_per_ns", 5.0)
        vf_quality = result.get("vf_fit_quality", "N/A")
        tg0        = result.get("tg0_K", float("nan"))
        ci95       = result.get("tg0_K_ci95", float("nan"))
        r2_vf      = result.get("vf_r_squared", float("nan"))

        slow_rate_str = f"{slow_rate:.2e}" if is_dsc else f"{slow_rate:.0f}"
        tg_slow_label = ("theoretical DSC-equivalent experimental Tg" if is_dsc
                         else "slow-MD Tg")
        d06_md = (
            f"### Multi-rate Tg analysis\n\n"
            f"| Rate | Tg_MD |\n|------|-------|\n{rate_rows}\n\n"
            f"**Log-linear**: Tg = {result.get('loglinear_intercept_K', 0):.1f} + {slope:.2f}·ln(Γ)  "
            f"R²={r2_lin:.4f}\n"
            f"→ Tg at {slow_rate_str} K/ns ({ref_label}) = **{tg_slow:.1f} K**  ({tg_slow_label})\n\n"
            f"**VF extrapolation** (Tg0 at Γ→0): "
        )
        if "tg0_K" in result:
            d06_md += f"Tg⁰ = {tg0:.1f} ± {ci95:.1f} K (95% CI)  R²={r2_vf:.4f}  quality={vf_quality}\n"
            if "POORLY_CONSTRAINED" in vf_quality:
                d06_md += "⚠ CI > 100 K: VF extrapolation is underconstrained with < 2 decades of rates. Use log-linear result for validation.\n"
        else:
            d06_md += f"quality={vf_quality}\n"

        result["d06_markdown"] = d06_md
        d06_path = out_dir / "d06_multirate_block.md"
        d06_path.write_text(d06_md)
        result["d06_markdown_path"] = str(d06_path)

    # ── Plot ──────────────────────────────────────────────────────────────
    if not args.no_plot and result.get("status") == "success":
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt

            rates_arr = np.array(args.rates)
            tg_arr    = np.array(args.tg_values)
            # x-axis spans from the reference rate (DSC, far left) up to the data, so the
            # extrapolated log-linear line visibly reaches the reference vline.
            x_lo = np.log(args.slow_rate_ref * 0.5) if is_dsc else np.log(rates_arr.min() * 0.5)
            x_range   = np.linspace(x_lo, np.log(rates_arr.max() * 2.0), 200)
            r_range   = np.exp(x_range)

            # Log-linear curve (extrapolated across the full range)
            a_ll = result.get("loglinear_intercept_K", 0.0)
            b_ll = result.get("loglinear_slope_K", 0.0)
            tg_ll = a_ll + b_ll * x_range

            fig, ax = plt.subplots(figsize=(6, 4))
            ax.semilogx(rates_arr, tg_arr, "o", color="#2196F3", ms=7, zorder=3, label="MD data")
            ax.semilogx(r_range, tg_ll, "--", color="#4CAF50", lw=1.5, label="log-linear")

            # VF curve (if successful) — plotted ONLY over the data range. VF has a
            # singularity at ln Γ = -c; extrapolating it ~12 decades to DSC would blow up
            # the y-axis, and VF is diagnostic-only at <2 decades anyway.
            if "tg0_K" in result:
                tg0 = result["tg0_K"]
                a   = result["vf_A"]
                c   = result["vf_c"]
                x_vf = np.linspace(np.log(rates_arr.min()), np.log(rates_arr.max()), 100)
                ax.semilogx(np.exp(x_vf), vf_model(x_vf, tg0, a, c),
                            "-", color="#F44336", lw=1.8, label="VF fit (data range)")
                ax.axhline(tg0, ls=":", color="#9C27B0", lw=1.2,
                           label=f"VF Tg⁰ = {tg0:.1f} K")

            # Reference rate + the extrapolated Tg there
            tg_slow_pt = result.get("tg_at_slow_rate_K")
            vline_lbl = (f"{ref_label} ({args.slow_rate_ref:.1e} K/ns)" if is_dsc
                         else f"slow ref = {args.slow_rate_ref:.0f} K/ns")
            ax.axvline(args.slow_rate_ref, ls=":", color="#607D8B", lw=1.0, label=vline_lbl)
            if tg_slow_pt is not None:
                ax.plot([args.slow_rate_ref], [tg_slow_pt], "*", color="#FF9800", ms=12,
                        zorder=4, label=f"Tg @ ref = {tg_slow_pt:.1f} K")
            ax.set_xlabel("Cooling rate (K/ns)")
            ax.set_ylabel("Tg (K)")
            title_suffix = " (DSC extrapolation)" if is_dsc else ""
            ax.set_title(f"{args.polymer_name} — Multi-rate Tg{title_suffix}")
            ax.legend(fontsize=7)
            fig.tight_layout()
            plot_path = out_dir / "tg_multirate.png"
            fig.savefig(plot_path, dpi=150)
            plt.close(fig)
            result["plot_path"] = str(plot_path)
        except Exception as plot_err:
            result["plot_warning"] = f"Plot skipped: {plot_err}"

    # ── Save + print ──────────────────────────────────────────────────────
    json_path = out_dir / "tg_multirate_result.json"
    json_path.write_text(json.dumps(result, indent=2))
    result["json_path"] = str(json_path)

    print(json.dumps(result))
    sys.exit(0 if result.get("status") == "success" else 1)


if __name__ == "__main__":
    main()
