#!/usr/bin/env python3
"""
Backbone orientation order parameter P2 (nematic order).

Computes the Saupe tensor from backbone bond vectors and extracts
the largest eigenvalue P2.  P2 = 0 is isotropic; P2 = 1 is perfectly
aligned.  Values > 0.10 flag residual chain alignment (inadequate
melt mixing or crystalline precursor domains).

Backbone bonds are formed between consecutive atoms of the specified
backbone atom types within each chain (resid).

Output:
    orientation_order.csv    — frame, timestep, p2, n_bonds
    orientation_summary.json

Usage:
    python mda_orientation_order.py --data_file FILE --dump_file FILE
        --backbone_types 2 3 [options]
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
    p = argparse.ArgumentParser(description="Backbone P2 nematic order via MDAnalysis")
    p.add_argument("--data_file",       required=True)
    p.add_argument("--dump_file",       required=True)
    p.add_argument("--skip_frames",     type=int,   default=0)
    p.add_argument("--max_frames",      type=int,   default=None)
    p.add_argument("--output_dir",      type=str,   default=None)
    p.add_argument("--atom_style",      type=str,   default="id resid type charge x y z")
    p.add_argument("--backbone_types",  type=int,   nargs="+", required=True,
                   help="Atom type IDs that form the backbone (e.g. 2 3 for PVDF)")
    p.add_argument("--p2_threshold",    type=float, default=0.10,
                   help="P2 threshold above which ordered_flag fires (default 0.10)")
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


def saupe_p2(bond_vectors):
    """
    Compute P2 from the Saupe ordering tensor Q.

    bond_vectors : (N, 3) unit vectors along backbone bonds.
    Returns the largest eigenvalue of Q (= P2, range [-0.5, 1.0]).
    """
    if len(bond_vectors) == 0:
        return 0.0
    u = bond_vectors / (np.linalg.norm(bond_vectors, axis=1, keepdims=True) + 1e-12)
    Q = (3 * np.einsum("ni,nj->ij", u, u) - np.eye(3) * len(u)) / (2 * len(u))
    eigvals = np.linalg.eigvalsh(Q)
    return float(eigvals.max())


def get_backbone_bond_vectors(u, chain_ids, backbone_set, box):
    """
    Extract bond vectors for backbone atoms within each chain.

    backbone_set : set of integer atom types considered backbone.
    Returns (N, 3) array of bond vectors (not normalized).
    """
    vectors = []
    for cid in chain_ids:
        chain = u.select_atoms(f"resid {cid}")
        bb_mask = np.isin(chain.types.astype(int) if chain.types.dtype.kind in ('i', 'u')
                          else chain.atoms.indices,   # fallback
                          list(backbone_set))
        # Use atom type integers
        try:
            type_ints = np.array([int(t) for t in chain.types])
        except Exception:
            continue
        bb_indices = np.where(np.isin(type_ints, list(backbone_set)))[0]
        if len(bb_indices) < 2:
            continue
        bb_pos = chain.positions[bb_indices]
        for i in range(len(bb_pos) - 1):
            dr = bb_pos[i + 1] - bb_pos[i]
            # Minimum image convention
            dr -= box * np.round(dr / box)
            vectors.append(dr)
    return np.array(vectors) if vectors else np.zeros((0, 3))


def _plot_orientation_p2(df, p2_mean, p2_std, p2_threshold, ordered_flag, output_dir):
    apply_style()
    frames = df['frame'].values
    p2_vals = df['p2'].values
    fig, ax = plt.subplots()
    ax.plot(frames, p2_vals, color='steelblue', lw=0.8, alpha=0.8, label='P₂(t)')
    ax.axhline(p2_mean, color='k', ls='-', lw=1.5, label=f'⟨P₂⟩ = {p2_mean:.3f}')
    ax.fill_between(frames, p2_mean - p2_std, p2_mean + p2_std, alpha=0.2, color='k')
    ax.axhline(p2_threshold, color='firebrick', ls='--', lw=1.2, alpha=0.7,
               label=f'Threshold = {p2_threshold}')
    flag_str = 'ORDERED — residual alignment' if ordered_flag else 'isotropic (OK)'
    ax.set_xlabel('Frame')
    ax.set_ylabel('P₂ nematic order parameter')
    ax.set_title(f'Backbone orientation order — {flag_str}')
    ax.set_ylim(bottom=max(-0.55, min(p2_vals.min() - 0.05, -0.05)))
    ax.legend()
    save_fig(fig, str(Path(output_dir) / 'figures' / 'orientation_p2.png'))


def main():
    args = parse_args()
    backbone_set = set(args.backbone_types)

    output_dir = Path(args.output_dir) if args.output_dir else Path(args.dump_file).parent / "analysis"
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading topology: {args.data_file}", flush=True)
    print(f"Loading trajectory: {args.dump_file}", flush=True)
    u = mda.Universe(args.data_file, args.dump_file,
                     format="LAMMPSDUMP", atom_style=args.atom_style)
    print(f"  n_atoms={u.atoms.n_atoms}, n_frames={u.trajectory.n_frames}", flush=True)
    print(f"  backbone_types={args.backbone_types}, P2 threshold={args.p2_threshold}", flush=True)

    chain_ids = sorted(set(int(r) for r in u.atoms.resids))
    print(f"  {len(chain_ids)} chains detected", flush=True)

    start = args.skip_frames
    stop = (start + args.max_frames) if args.max_frames is not None else None

    rows = []
    frame_idx = 0
    for ts in u.trajectory[start:stop]:
        box = ts.dimensions[:3]
        vecs = get_backbone_bond_vectors(u, chain_ids, backbone_set, box)
        p2 = saupe_p2(vecs)
        rows.append({
            "frame": frame_idx,
            "timestep": int(ts.data.get("step", ts.frame)),
            "p2": p2,
            "n_bonds": len(vecs),
        })
        frame_idx += 1
        if frame_idx % 50 == 0:
            print(f"  P2: frame {frame_idx}, P2={p2:.4f}", flush=True)

    df = pd.DataFrame(rows)
    csv_path = str(output_dir / "orientation_order.csv")
    df.to_csv(csv_path, index=False)
    print(f"  Wrote {csv_path}", flush=True)

    p2_mean  = float(df["p2"].mean())
    p2_std   = float(df["p2"].std())
    p2_max   = float(df["p2"].max())
    p2_trend = float(np.polyfit(np.arange(len(df)), df["p2"].values, 1)[0]) if len(df) > 1 else 0.0
    ordered_flag = p2_mean > args.p2_threshold

    summary = to_native({
        "status": "success",
        "data_file": args.data_file,
        "dump_file": args.dump_file,
        "output_dir": str(output_dir),
        "csv_file": csv_path,
        "backbone_types": args.backbone_types,
        "frames_analysed": frame_idx,
        "p2_mean": p2_mean,
        "p2_std": p2_std,
        "p2_max": p2_max,
        "p2_trend_per_frame": p2_trend,
        "ordered_flag": ordered_flag,
        "diagnostics": {
            "p2_threshold": args.p2_threshold,
            "p2_flag_meaning": f"P2 > {args.p2_threshold} indicates residual chain alignment (inadequate melt mixing or crystalline precursors)",
            "p2_isotropic": "P2 ≈ 0 (random orientation, well-melted amorphous)",
            "p2_perfect": "P2 = 1 (perfectly aligned — crystalline)",
            "p2_trend_meaning": "Positive trend → alignment growing over trajectory; negative → relaxing toward isotropic",
        },
        "method": "Saupe tensor P2 from backbone bond vectors via MDAnalysis",
        "mdanalysis_version": mda.__version__,
    })

    p2_fig_png = str(output_dir / "figures" / "orientation_p2.png")
    try:
        _plot_orientation_p2(df, p2_mean, p2_std, args.p2_threshold, ordered_flag, output_dir)
    except Exception as _pe:
        print(f"  WARNING: orientation_p2 plot failed: {_pe}", flush=True)
        p2_fig_png = None
    summary["orientation_p2_png"] = p2_fig_png

    json_path = str(output_dir / "orientation_summary.json")
    with open(json_path, "w") as jf:
        json.dump(summary, jf, indent=2)
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
