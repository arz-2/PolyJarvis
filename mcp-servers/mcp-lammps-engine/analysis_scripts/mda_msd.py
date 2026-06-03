#!/usr/bin/env python3
"""
Chain center-of-mass MSD and diffusion analysis.

Computes the mean-squared displacement of chain centers of mass using
overlapping windows.  Fits MSD(τ) = A·τ^α to determine the diffusion
regime.  Flags kinetic traps when the maximum MSD is smaller than
the mean Rg² (chains haven't moved their own size).

Output:
    msd_chain_com.csv     — lag_frames, lag_time_ps, msd_A2, n_samples
    msd_summary.json

Usage:
    python mda_msd.py --data_file FILE --dump_file FILE [options]
"""

import argparse
import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import MDAnalysis as mda

sys.path.insert(0, str(Path(__file__).parent))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from plot_style import apply_style, save_fig

warnings.filterwarnings("ignore", message="Reader has no dt information")


def parse_args():
    p = argparse.ArgumentParser(description="Chain CoM MSD via MDAnalysis")
    p.add_argument("--data_file",       required=True)
    p.add_argument("--dump_file",       required=True)
    p.add_argument("--skip_frames",     type=int,   default=0)
    p.add_argument("--max_frames",      type=int,   default=None)
    p.add_argument("--output_dir",      type=str,   default=None)
    p.add_argument("--atom_style",      type=str,   default="id resid type charge x y z")
    p.add_argument("--timestep_fs",     type=float, default=1.0,
                   help="MD timestep in fs (used to convert frames → ps)")
    p.add_argument("--dump_every",      type=int,   default=1000,
                   help="Frames saved every N timesteps (for lag-time axis)")
    p.add_argument("--max_lag_frac",    type=float, default=0.5,
                   help="Maximum lag as fraction of trajectory length (default 0.5)")
    p.add_argument("--n_lag_points",    type=int,   default=None,
                   help="Number of log-spaced lag points to evaluate (default: all integer lags up to max_lag_frac)")
    p.add_argument("--mean_rg2_A2",     type=float, default=None,
                   help="Mean Rg² in Å² for kinetic-trap check")
    p.add_argument("--rg_sq_A2",        type=float, default=None,
                   help="Alias for --mean_rg2_A2 (server compatibility)")
    return p.parse_args()


def to_native(obj):
    if isinstance(obj, dict):
        return {to_native(k): to_native(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [to_native(x) for x in obj]
    elif isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    return obj


def compute_chain_coms(u, chain_ids):
    """Return (n_chains, 3) array of chain CoMs for current frame."""
    coms = []
    for cid in chain_ids:
        chain = u.select_atoms(f"resid {cid}")
        try:
            masses = chain.masses
        except Exception:
            masses = np.ones(chain.n_atoms)
        total = masses.sum()
        com = (masses[:, None] * chain.positions).sum(axis=0) / total
        coms.append(com)
    return np.array(coms)


def overlapping_msd(coms_all, max_lag, lag_subset=None):
    """
    Compute MSD via overlapping windows.

    coms_all  : (n_frames, n_chains, 3)
    lag_subset: optional array of specific lags to evaluate (default: 1..max_lag)
    Returns arrays: lags (frames), msd (Å²), n_samples per lag.
    """
    lags = lag_subset if lag_subset is not None else np.arange(1, max_lag + 1)
    msd_vals = np.zeros(len(lags))
    counts = np.zeros(len(lags), dtype=int)
    for i, lag in enumerate(lags):
        dr = coms_all[lag:] - coms_all[:-lag]          # (n_origins, n_chains, 3)
        msd_vals[i] = float((dr ** 2).sum(axis=-1).mean())
        counts[i] = dr.shape[0]
    return lags, msd_vals, counts


def fit_power_law(lags, msd, min_points=5):
    """Fit log(MSD) = log(A) + alpha*log(lag). Returns A, alpha, R²."""
    mask = (lags > 0) & (msd > 0)
    if mask.sum() < min_points:
        return None, None, None
    x = np.log(lags[mask].astype(float))
    y = np.log(msd[mask])
    coeffs = np.polyfit(x, y, 1)
    alpha = float(coeffs[0])
    A = float(np.exp(coeffs[1]))
    y_pred = np.polyval(coeffs, x)
    ss_res = float(((y - y_pred) ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = float(1 - ss_res / ss_tot) if ss_tot > 0 else 0.0
    return A, alpha, r2


def _plot_msd_log(lag_times_ps, msd_vals, alpha, A, r2_fit, output_dir):
    apply_style()
    mask = (lag_times_ps > 0) & (msd_vals > 0)
    fig, ax = plt.subplots()
    ax.loglog(lag_times_ps[mask], msd_vals[mask], 'o', color='steelblue',
              ms=4, alpha=0.8, label='MSD')
    if alpha is not None and A is not None:
        t_fit = lag_times_ps[mask]
        label = f'α = {alpha:.2f}' + (f'  (R² = {r2_fit:.3f})' if r2_fit is not None else '')
        ax.loglog(t_fit, A * t_fit ** alpha, '--', color='firebrick', lw=2, label=label)
    ax.set_xlabel('Lag time (ps)')
    ax.set_ylabel('MSD (Å²)')
    ax.set_title('Chain center-of-mass MSD')
    ax.legend()
    save_fig(fig, str(Path(output_dir) / 'figures' / 'msd_log.png'))


def main():
    args = parse_args()

    output_dir = Path(args.output_dir) if args.output_dir else Path(args.dump_file).parent / "analysis"
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading topology: {args.data_file}", flush=True)
    print(f"Loading trajectory: {args.dump_file}", flush=True)
    u = mda.Universe(args.data_file, args.dump_file,
                     format="LAMMPSDUMP", atom_style=args.atom_style)
    print(f"  n_atoms={u.atoms.n_atoms}, n_frames={u.trajectory.n_frames}", flush=True)

    chain_ids = sorted(set(int(r) for r in u.atoms.resids))
    print(f"  {len(chain_ids)} chains detected", flush=True)

    # Unwrap before CoM calculation
    try:
        import MDAnalysis.transformations as trans
        u.trajectory.add_transformations(trans.unwrap(u.atoms))
        print("  Unwrapping coordinates", flush=True)
    except Exception as e:
        print(f"  WARNING: unwrap failed ({e})", flush=True)

    start = args.skip_frames
    stop = (start + args.max_frames) if args.max_frames is not None else None

    coms_list = []
    timesteps = []
    for ts in u.trajectory[start:stop]:
        coms_list.append(compute_chain_coms(u, chain_ids))
        timesteps.append(int(ts.data.get("step", ts.frame)))
        if len(coms_list) % 100 == 0:
            print(f"  MSD: loaded frame {len(coms_list)}", flush=True)

    coms_all = np.array(coms_list)     # (n_frames, n_chains, 3)
    n_frames = coms_all.shape[0]
    print(f"  Total frames loaded: {n_frames}", flush=True)

    # Resolve rg_sq_A2 alias
    rg2 = args.rg_sq_A2 if args.rg_sq_A2 is not None else args.mean_rg2_A2

    max_lag = max(1, int(n_frames * args.max_lag_frac))
    all_lags = np.arange(1, max_lag + 1)
    # Subsample to n_lag_points log-spaced lags if requested
    if args.n_lag_points is not None and args.n_lag_points < max_lag:
        sampled = np.unique(np.round(np.logspace(0, np.log10(max_lag), args.n_lag_points)).astype(int))
        sampled = sampled[sampled <= max_lag]
        all_lags = sampled
    lags, msd_vals, counts = overlapping_msd(coms_all, max_lag, lag_subset=all_lags)

    # Convert lag frames → ps
    dt_ps = args.timestep_fs * args.dump_every / 1000.0
    lag_times_ps = lags * dt_ps

    rows = [
        {"lag_frames": int(l), "lag_time_ps": float(t), "msd_A2": float(m), "n_samples": int(c)}
        for l, t, m, c in zip(lags, lag_times_ps, msd_vals, counts)
    ]
    df = pd.DataFrame(rows)
    csv_path = str(output_dir / "msd_chain_com.csv")
    df.to_csv(csv_path, index=False)
    print(f"  Wrote {csv_path}", flush=True)

    A, alpha, r2 = fit_power_law(lags, msd_vals)
    msd_max = float(msd_vals.max()) if len(msd_vals) > 0 else 0.0

    # Kinetic trap: chains haven't displaced their own size
    kinetic_trap_flag = False
    if rg2 is not None and rg2 > 0:
        kinetic_trap_flag = msd_max < rg2

    # Diffusion regime interpretation
    if alpha is not None:
        if alpha < 0.4:
            regime = "sub-diffusive / kinetically trapped"
        elif alpha < 0.85:
            regime = "sub-diffusive (Rouse/reptation)"
        elif alpha < 1.15:
            regime = "Fickian diffusion"
        else:
            regime = "super-diffusive (non-equilibrated)"
    else:
        regime = "insufficient data"

    summary = to_native({
        "status": "success",
        "data_file": args.data_file,
        "dump_file": args.dump_file,
        "output_dir": str(output_dir),
        "csv_file": csv_path,
        "n_chains": len(chain_ids),
        "frames_analysed": n_frames,
        "max_lag_frames": max_lag,
        "dt_ps_per_frame": dt_ps,
        "msd_max_A2": msd_max,
        "alpha_exponent": alpha,
        "alpha_prefactor_A": A,
        "alpha_r2": r2,
        "diffusion_regime": regime,
        "kinetic_trap_flag": kinetic_trap_flag,
        "rg_sq_A2_used": rg2,
        "diagnostics": {
            "kinetic_trap_meaning": "MSD_max < Rg² — chains have not displaced their own size; system likely kinetically trapped",
            "alpha_interpretation": {
                "< 0.4": "kinetically trapped / glassy",
                "0.4–0.85": "sub-diffusive Rouse/reptation",
                "0.85–1.15": "Fickian diffusion (liquid-like)",
                "> 1.15": "super-diffusive (non-equilibrated)",
            },
        },
        "method": "Overlapping-window chain CoM MSD via MDAnalysis",
        "mdanalysis_version": mda.__version__,
    })

    msd_fig_png = str(output_dir / "figures" / "msd_log.png")
    try:
        _plot_msd_log(lag_times_ps, msd_vals, alpha, A, r2, output_dir)
    except Exception as _pe:
        print(f"  WARNING: msd_log plot failed: {_pe}", flush=True)
        msd_fig_png = None
    summary["msd_log_png"] = msd_fig_png

    json_path = str(output_dir / "msd_summary.json")
    with open(json_path, "w") as jf:
        json.dump(summary, jf, indent=2)
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
