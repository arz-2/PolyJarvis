#!/usr/bin/env python3
"""
Radius of gyration (Rg) and characteristic ratio (C∞) per chain.

Computes mass-weighted Rg for each chain at each trajectory frame.
Reports per-chain distribution statistics and — when backbone bond
count and length are supplied — the characteristic ratio C∞.

Output:
    rg_per_chain.csv      — frame, timestep, chain, rg, rg_sq
    rg_summary.json       — per-chain stats, distribution, C∞ (if requested)

Usage:
    python mda_radius_of_gyration.py --data_file FILE --dump_file FILE [options]
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
    p = argparse.ArgumentParser(description="Radius of gyration via MDAnalysis")
    p.add_argument("--data_file",      required=True, help="LAMMPS .data file (topology)")
    p.add_argument("--dump_file",      required=True, help="LAMMPS dump file (trajectory)")
    p.add_argument("--skip_frames",    type=int, default=0)
    p.add_argument("--max_frames",     type=int, default=None)
    p.add_argument("--output_dir",     type=str, default=None)
    p.add_argument("--atom_style",     type=str, default="id resid type charge x y z")
    p.add_argument("--n_backbone_bonds", type=int, default=None,
                   help="Number of backbone bonds per chain (for C∞ = <R²>/(N·l²))")
    p.add_argument("--bond_length_A",    type=float, default=1.54,
                   help="Backbone bond length in Angstrom (default: 1.54 C-C)")
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


def compute_rg_sq(positions, masses):
    """Mass-weighted radius of gyration squared."""
    total_mass = masses.sum()
    r_cm = (masses[:, None] * positions).sum(axis=0) / total_mass
    delta = positions - r_cm
    rg_sq = (masses * (delta ** 2).sum(axis=1)).sum() / total_mass
    return float(rg_sq)


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

    # Unwrap
    try:
        import MDAnalysis.transformations as trans
        u.trajectory.add_transformations(trans.unwrap(u.atoms))
        print("  Unwrapping coordinates", flush=True)
    except Exception as e:
        print(f"  WARNING: unwrap failed ({e})", flush=True)

    start = args.skip_frames
    stop = (start + args.max_frames) if args.max_frames is not None else None

    rows = []
    frame_idx = 0
    for ts in u.trajectory[start:stop]:
        for cid in chain_ids:
            chain = u.select_atoms(f"resid {cid}")
            try:
                masses = chain.masses
            except Exception:
                masses = np.ones(chain.n_atoms)
            rg_sq = compute_rg_sq(chain.positions, masses)
            rows.append({
                "frame": frame_idx,
                "timestep": int(ts.data.get("step", ts.frame)),
                "chain": int(cid),
                "rg": float(np.sqrt(rg_sq)),
                "rg_sq": rg_sq,
            })
        frame_idx += 1
        if frame_idx % 100 == 0:
            print(f"  Rg: frame {frame_idx}", flush=True)

    df = pd.DataFrame(rows)
    csv_path = str(output_dir / "rg_per_chain.csv")
    df.to_csv(csv_path, index=False)
    print(f"  Wrote {csv_path}", flush=True)

    per_chain = []
    for cid, grp in df.groupby("chain"):
        per_chain.append({
            "chain": int(cid),
            "mean_Rg": float(grp["rg"].mean()),
            "std_Rg":  float(grp["rg"].std()),
            "mean_Rg2": float(grp["rg_sq"].mean()),
        })

    overall_mean_Rg  = float(df["rg"].mean())
    overall_std_Rg   = float(df["rg"].std())
    overall_mean_Rg2 = float(df["rg_sq"].mean())

    chain_means = [c["mean_Rg"] for c in per_chain]
    rg_cv = float(np.std(chain_means) / np.mean(chain_means)) if len(chain_means) > 1 else 0.0
    rg_spread_flag = rg_cv > 0.30

    hist, bin_edges = np.histogram(df["rg"].values, bins=30)
    rg_hist = {"counts": hist.tolist(), "bin_edges": bin_edges.tolist()}

    char_ratio_from_rg = None
    if args.n_backbone_bonds is not None:
        N = args.n_backbone_bonds
        l = args.bond_length_A
        char_ratio_from_rg = float(6.0 * overall_mean_Rg2 / (N * l ** 2))
        print(f"  C∞ (from Rg) = {char_ratio_from_rg:.3f}", flush=True)

    summary = to_native({
        "status": "success",
        "data_file": args.data_file,
        "dump_file": args.dump_file,
        "output_dir": str(output_dir),
        "csv_file": csv_path,
        "n_chains": len(chain_ids),
        "frames_analysed": frame_idx,
        "overall_mean_Rg_A": overall_mean_Rg,
        "overall_std_Rg_A": overall_std_Rg,
        "overall_mean_Rg2_A2": overall_mean_Rg2,
        "rg_cv_across_chains": rg_cv,
        "rg_spread_flag": rg_spread_flag,
        "rg_histogram": rg_hist,
        "characteristic_ratio_from_Rg": char_ratio_from_rg,
        "n_backbone_bonds_used": args.n_backbone_bonds,
        "bond_length_A_used": args.bond_length_A,
        "per_chain": per_chain,
        "diagnostics": {
            "rg_cv_threshold": 0.30,
            "rg_cv_flag_meaning": "CV(Rg per chain) > 30% suggests unequal chain conformations — poor equilibration",
        },
        "method": "MDAnalysis mass-weighted Rg",
        "mdanalysis_version": mda.__version__,
    })

    json_path = str(output_dir / "rg_summary.json")
    with open(json_path, "w") as jf:
        json.dump(summary, jf, indent=2)
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
