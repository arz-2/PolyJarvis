#!/usr/bin/env python3
"""
End-to-end vector extraction using MDAnalysis.

Computes per-chain end-to-end distance R and vector (rx, ry, rz)
for every frame, using MDAnalysis topology and sort_backbone for
robust terminal atom identification.

Output:
    end_to_end_vectors.csv   — columns: frame, timestep, chain, rx, ry, rz, distance
    end_to_end_summary.json  — per-chain stats, overall averages, terminal atom IDs

Usage:
    python mda_end_to_end.py --data_file FILE --dump_file FILE --backbone_types 2 3 [options]
"""

import argparse
import json
import sys
import warnings
from pathlib import Path
from collections import defaultdict

import numpy as np
import pandas as pd
import MDAnalysis as mda
from MDAnalysis.analysis.polymer import sort_backbone

sys.path.insert(0, str(Path(__file__).parent))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from plot_style import apply_style, save_fig

warnings.filterwarnings("ignore", message="Reader has no dt information")


def parse_args():
    p = argparse.ArgumentParser(description="End-to-end vectors via MDAnalysis")
    p.add_argument("--data_file", required=True, help="LAMMPS .data file (topology + bonds)")
    p.add_argument("--dump_file", required=True, help="LAMMPS dump file (trajectory)")
    p.add_argument("--backbone_types", type=int, nargs='+', required=True,
                   help="LAMMPS atom type IDs forming the backbone (e.g. 2 3)")
    p.add_argument("--num_chains", type=int, default=None,
                   help="Number of chains (auto-detected from resids if omitted)")
    p.add_argument("--chain_ids", type=int, nargs='*', default=None,
                   help="Subset of chain IDs (resids) to analyse. All if omitted.")
    p.add_argument("--skip_frames", type=int, default=0, help="Frames to skip at start")
    p.add_argument("--max_frames", type=int, default=None, help="Max frames to analyse")
    p.add_argument("--output_dir", type=str, default=None,
                   help="Output directory (default: <dump_dir>/analysis)")
    p.add_argument("--graphs_dir", type=str, default=None,
                   help="Directory for PNG figures (default: <output_dir>/figures/)")
    p.add_argument("--atom_style", type=str, default="id resid type charge x y z",
                   help="LAMMPS atom_style column order for the data file")
    p.add_argument("--unwrap", action="store_true", default=True,
                   help="Unwrap coordinates using MDA (default: True)")
    return p.parse_args()


def to_native(obj):
    """Recursively convert numpy types to native Python for JSON serialization."""
    if isinstance(obj, dict):
        return {to_native(k): to_native(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [to_native(x) for x in obj]
    elif isinstance(obj, (np.integer,)):
        return int(obj)
    elif isinstance(obj, (np.floating,)):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    return obj


def _plot_end_to_end_distribution(df_out, per_chain, overall_mean_R, graphs_dir):
    apply_style()
    fig, ax = plt.subplots()
    distances = df_out['distance'].values
    ax.hist(distances, bins=40, color='steelblue', alpha=0.7, density=True, label='All frames/chains')
    for c in per_chain:
        ax.axvline(c['mean_R'], color='firebrick', alpha=0.35, lw=0.8)
    ax.axvline(overall_mean_R, color='k', lw=2, ls='--', label=f'⟨R⟩ = {overall_mean_R:.1f} Å')
    ax.set_xlabel('End-to-end distance |R| (Å)')
    ax.set_ylabel('Probability density')
    ax.set_title('End-to-end vector distribution')
    ax.legend()
    save_fig(fig, str(graphs_dir / 'end_to_end_distribution.png'))


def main():
    args = parse_args()

    # Output directory
    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        output_dir = Path(args.dump_file).parent / "analysis"
    output_dir.mkdir(parents=True, exist_ok=True)
    graphs_dir = Path(args.graphs_dir) if args.graphs_dir else output_dir / 'figures'
    graphs_dir.mkdir(parents=True, exist_ok=True)

    # Load universe
    print(f"Loading topology: {args.data_file}", flush=True)
    print(f"Loading trajectory: {args.dump_file}", flush=True)
    u = mda.Universe(args.data_file, args.dump_file,
                     format='LAMMPSDUMP',
                     atom_style=args.atom_style)
    print(f"  n_atoms={u.atoms.n_atoms}, n_frames={u.trajectory.n_frames}", flush=True)
    print(f"  n_bonds={len(u.atoms.bonds)}", flush=True)

    # Determine chains
    all_resids = sorted(set(int(r) for r in u.atoms.resids))
    if args.chain_ids is not None:
        chain_list = args.chain_ids
    elif args.num_chains is not None:
        chain_list = list(range(1, args.num_chains + 1))
    else:
        chain_list = all_resids
    print(f"  Analysing {len(chain_list)} chains: {chain_list[:10]}{'...' if len(chain_list)>10 else ''}", flush=True)

    # Build backbone type selection string
    type_sel = ' or '.join(f'type {t}' for t in args.backbone_types)

    # Pre-compute sorted backbone terminal atoms for each chain
    chain_termini = {}  # resid -> (first_atom_id, last_atom_id)
    chain_sorted_bb = {}  # resid -> sorted AtomGroup

    print(f"  Identifying backbone termini (types: {args.backbone_types})...", flush=True)
    for cid in chain_list:
        bb = u.select_atoms(f'resid {cid} and ({type_sel})')
        if len(bb) < 2:
            print(f"    Chain {cid}: only {len(bb)} backbone atoms, skipping", flush=True)
            continue
        try:
            sorted_bb = sort_backbone(bb)
            chain_sorted_bb[cid] = sorted_bb
            chain_termini[cid] = (int(sorted_bb[0].id), int(sorted_bb[-1].id))
            print(f"    Chain {cid}: {len(sorted_bb)} backbone atoms, "
                  f"termini ids={sorted_bb[0].id} - {sorted_bb[-1].id}", flush=True)
        except Exception as e:
            print(f"    Chain {cid}: sort_backbone failed ({e}), "
                  f"falling back to first/last atom id", flush=True)
            ids_sorted = sorted(int(x) for x in bb.ids)
            chain_termini[cid] = (ids_sorted[0], ids_sorted[-1])
            chain_sorted_bb[cid] = bb

    if not chain_termini:
        result = {
            "status": "failed",
            "error": "No chains with >= 2 backbone atoms found",
        }
        print(json.dumps(result))
        sys.exit(1)

    # Add unwrapping transformation if requested
    if args.unwrap:
        try:
            import MDAnalysis.transformations as trans
            unwrap_transform = trans.unwrap(u.atoms)
            u.trajectory.add_transformations(unwrap_transform)
            print("  Unwrapping coordinates using MDA transformations", flush=True)
        except Exception as e:
            print(f"  WARNING: MDA unwrap failed ({e}), using raw coordinates", flush=True)

    # Frame range
    start = args.skip_frames
    stop = None
    if args.max_frames is not None:
        stop = start + args.max_frames

    # Main trajectory loop
    all_rows = []
    frame_idx = 0

    for ts in u.trajectory[start:stop]:
        for cid, sorted_bb in chain_sorted_bb.items():
            r_a = sorted_bb[0].position
            r_b = sorted_bb[-1].position
            r_vec = r_b - r_a
            r_dist = float(np.linalg.norm(r_vec))

            all_rows.append({
                "frame": frame_idx,
                "timestep": int(ts.data.get("step", ts.frame)),
                "chain": int(cid),
                "rx": float(r_vec[0]),
                "ry": float(r_vec[1]),
                "rz": float(r_vec[2]),
                "distance": r_dist,
            })

        frame_idx += 1
        if frame_idx % 200 == 0:
            print(f"  e2e: frame {frame_idx}", flush=True)

    # Write CSV
    df_out = pd.DataFrame(all_rows)
    csv_path = str(output_dir / "end_to_end_vectors.csv")
    df_out.to_csv(csv_path, index=False)
    print(f"  Wrote {csv_path} ({len(df_out)} rows)", flush=True)

    # Per-chain statistics
    per_chain = []
    for cid, grp in df_out.groupby("chain"):
        d = grp["distance"]
        r2 = grp["rx"]**2 + grp["ry"]**2 + grp["rz"]**2
        per_chain.append({
            "chain": int(cid),
            "mean_R": float(d.mean()),
            "std_R": float(d.std()),
            "mean_R2": float(r2.mean()),
            "std_R2": float(r2.std()),
            "n_frames": int(len(d)),
        })

    # Termini used — ensure all values are native Python types
    termini_used = {str(k): [int(x) for x in v] for k, v in chain_termini.items()}

    summary = to_native({
        "status": "success",
        "data_file": args.data_file,
        "dump_file": args.dump_file,
        "output_dir": str(output_dir),
        "csv_file": csv_path,
        "num_chains": len(chain_sorted_bb),
        "frames_analysed": frame_idx,
        "backbone_types": args.backbone_types,
        "termini_used": termini_used,
        "per_chain": per_chain,
        "overall_mean_R": float(df_out["distance"].mean()) if len(df_out) > 0 else 0.0,
        "overall_mean_R2": float((df_out["rx"]**2 + df_out["ry"]**2 + df_out["rz"]**2).mean()) if len(df_out) > 0 else 0.0,
        "method": "MDAnalysis.analysis.polymer.sort_backbone",
        "mdanalysis_version": mda.__version__,
    })

    e2e_fig_png = str(graphs_dir / "end_to_end_distribution.png")
    try:
        _plot_end_to_end_distribution(df_out, per_chain,
                                      summary["overall_mean_R"], graphs_dir)
    except Exception as _pe:
        print(f"  WARNING: end_to_end_distribution plot failed: {_pe}", flush=True)
        e2e_fig_png = None
    summary["end_to_end_distribution_png"] = e2e_fig_png

    json_path = str(output_dir / "end_to_end_summary.json")
    with open(json_path, "w") as jf:
        json.dump(summary, jf, indent=2)

    print(json.dumps(summary))


if __name__ == "__main__":
    main()
