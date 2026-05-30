#!/usr/bin/env python3
"""
Spatial density homogeneity check.

Divides the simulation box into an n×n×n grid and computes mass density
per voxel per frame.  Reports the coefficient of variation (CV = σ/μ)
across occupied voxels — a concise scalar measure of spatial uniformity.

Interpretation:
  CV < 0.15  → homogeneous amorphous (expected for well-equilibrated melt)
  CV 0.15-0.25 → mild density fluctuations (acceptable near Tg)
  CV > 0.25  → density heterogeneity flag fires
               (voids, chain droplets, or crystalline domains)

Output:
    density_homogeneity.csv    — frame, timestep, cv, mean_density, std_density, n_occupied
    density_summary.json

Usage:
    python mda_density_homogeneity.py --data_file FILE --dump_file FILE
        [--grid_n 10] [options]
"""

import argparse
import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import MDAnalysis as mda

warnings.filterwarnings("ignore", message="Reader has no dt information")


def parse_args():
    p = argparse.ArgumentParser(description="Spatial density homogeneity via MDAnalysis")
    p.add_argument("--data_file",    required=True)
    p.add_argument("--dump_file",    required=True)
    p.add_argument("--skip_frames",  type=int, default=0)
    p.add_argument("--max_frames",   type=int, default=None)
    p.add_argument("--output_dir",   type=str, default=None)
    p.add_argument("--atom_style",   type=str, default="id resid type charge x y z")
    p.add_argument("--grid_n",       type=int, default=10,
                   help="Number of voxels per axis (default 10 → 1000 voxels total)")
    p.add_argument("--cv_threshold", type=float, default=0.25,
                   help="CV threshold above which heterogeneity flag fires (default 0.25)")
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


def compute_density_cv(positions, masses, box_lengths, grid_n):
    """Bin atoms into a grid_n³ voxel grid and compute CV of voxel mass densities."""
    pos = positions % box_lengths[np.newaxis, :]
    voxel_vol = np.prod(box_lengths) / grid_n ** 3
    idx = np.floor(pos / box_lengths[np.newaxis, :] * grid_n).astype(int)
    idx = np.clip(idx, 0, grid_n - 1)
    flat_idx = idx[:, 0] * grid_n * grid_n + idx[:, 1] * grid_n + idx[:, 2]
    n_vox = grid_n ** 3
    voxel_mass = np.bincount(flat_idx, weights=masses, minlength=n_vox)
    voxel_density = voxel_mass / voxel_vol
    occupied = voxel_density > 0
    n_occupied = int(occupied.sum())
    if n_occupied == 0:
        return 0.0, 0.0, 0.0, 0
    occ_dens = voxel_density[occupied]
    mean_d = float(occ_dens.mean())
    std_d  = float(occ_dens.std())
    cv = std_d / mean_d if mean_d > 0 else 0.0
    return cv, mean_d, std_d, n_occupied


def main():
    args = parse_args()

    output_dir = Path(args.output_dir) if args.output_dir else Path(args.dump_file).parent / "analysis"
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading topology: {args.data_file}", flush=True)
    print(f"Loading trajectory: {args.dump_file}", flush=True)
    u = mda.Universe(args.data_file, args.dump_file,
                     format="LAMMPSDUMP", atom_style=args.atom_style)
    print(f"  n_atoms={u.atoms.n_atoms}, n_frames={u.trajectory.n_frames}", flush=True)
    print(f"  grid={args.grid_n}³={args.grid_n**3} voxels, CV threshold={args.cv_threshold}", flush=True)

    try:
        masses = u.atoms.masses.copy()
    except Exception:
        masses = np.ones(u.atoms.n_atoms)
        print("  WARNING: masses not available, using unit masses", flush=True)

    start = args.skip_frames
    stop = (start + args.max_frames) if args.max_frames is not None else None

    rows = []
    frame_idx = 0
    for ts in u.trajectory[start:stop]:
        box = ts.dimensions[:3]
        cv, mean_d, std_d, n_occ = compute_density_cv(
            u.atoms.positions.copy(), masses, box, args.grid_n
        )
        rows.append({
            "frame": frame_idx,
            "timestep": int(ts.data.get("step", ts.frame)),
            "cv": cv,
            "mean_density_amu_A3": mean_d,
            "std_density_amu_A3": std_d,
            "n_occupied_voxels": n_occ,
        })
        frame_idx += 1
        if frame_idx % 50 == 0:
            print(f"  Density: frame {frame_idx}, CV={cv:.4f}", flush=True)

    df = pd.DataFrame(rows)
    csv_path = str(output_dir / "density_homogeneity.csv")
    df.to_csv(csv_path, index=False)
    print(f"  Wrote {csv_path}", flush=True)

    cv_mean  = float(df["cv"].mean())
    cv_std   = float(df["cv"].std())
    cv_max   = float(df["cv"].max())
    cv_trend = float(np.polyfit(np.arange(len(df)), df["cv"].values, 1)[0])

    # Poisson limit: expected CV from atom count statistics alone = 1/sqrt(atoms_per_voxel)
    n_vox = args.grid_n ** 3
    atoms_per_voxel = u.atoms.n_atoms / n_vox
    poisson_cv = float(1.0 / np.sqrt(atoms_per_voxel)) if atoms_per_voxel > 0 else 1.0
    poisson_limited = poisson_cv > 0.30    # < ~11 atoms/voxel; result unreliable

    heterogeneous_flag = cv_mean > args.cv_threshold and not poisson_limited

    if poisson_limited:
        print(f"  WARNING: only {atoms_per_voxel:.1f} atoms/voxel (Poisson CV={poisson_cv:.2f} > 0.30); "
              f"grid_n={args.grid_n} is too fine for {u.atoms.n_atoms} atoms. "
              f"Recommend grid_n <= {int(u.atoms.n_atoms ** (1/3) / np.sqrt(10))}", flush=True)

    summary = to_native({
        "status": "success",
        "data_file": args.data_file,
        "dump_file": args.dump_file,
        "output_dir": str(output_dir),
        "csv_file": csv_path,
        "grid_n": args.grid_n,
        "n_voxels_total": n_vox,
        "atoms_per_voxel": atoms_per_voxel,
        "poisson_cv_limit": poisson_cv,
        "poisson_limited": poisson_limited,
        "frames_analysed": frame_idx,
        "cv_mean": cv_mean,
        "cv_std": cv_std,
        "cv_max": cv_max,
        "cv_trend_per_frame": cv_trend,
        "heterogeneous_flag": heterogeneous_flag,
        "diagnostics": {
            "cv_threshold": args.cv_threshold,
            "cv_flag_meaning": f"CV > {args.cv_threshold} indicates density heterogeneity (voids, droplets, or crystalline domains)",
            "cv_trend_meaning": "Positive trend → heterogeneity growing; negative → system becoming more uniform",
            "typical_amorphous_cv": "< 0.15",
            "acceptable_near_Tg_cv": "0.15–0.25",
            "poisson_limited_meaning": "If poisson_limited=true, grid_n is too fine; CV is dominated by atom-count noise, not physical density variation. heterogeneous_flag is suppressed. Reduce grid_n.",
        },
        "method": f"Voxel mass density CV on {args.grid_n}³ grid",
        "mdanalysis_version": mda.__version__,
    })

    json_path = str(output_dir / "density_summary.json")
    with open(json_path, "w") as jf:
        json.dump(summary, jf, indent=2)
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
