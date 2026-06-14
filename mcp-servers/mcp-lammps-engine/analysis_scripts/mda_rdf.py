#!/usr/bin/env python3
"""
RDF calculation using MDAnalysis InterRDF.

Computes pair radial distribution functions g(r) from a LAMMPS
data file (topology) + dump file (trajectory) using MDAnalysis.

Output:
    rdf_t<T1>-t<T2>.csv   — columns: r, g_r  (one file per pair)
    rdf_summary.json       — metadata and file paths

Usage:
    python mda_rdf.py --data_file FILE --dump_file FILE [options]
"""

import argparse
import json
import sys
import warnings
from pathlib import Path

import numpy as np
import MDAnalysis as mda
from MDAnalysis.analysis.rdf import InterRDF

sys.path.insert(0, str(Path(__file__).parent))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from plot_style import apply_style, save_fig

warnings.filterwarnings("ignore", message="Reader has no dt information")


def parse_args():
    p = argparse.ArgumentParser(description="RDF via MDAnalysis InterRDF")
    p.add_argument("--data_file", required=True, help="LAMMPS .data file (topology)")
    p.add_argument("--dump_file", required=True, help="LAMMPS dump file (trajectory)")
    p.add_argument("--atom_type_pairs", type=str, default=None,
                   help='JSON list of [t1,t2] pairs, e.g. \'[[1,2],[2,2]]\'. '
                        'If omitted, all unique pairs are computed.')
    p.add_argument("--rmax", type=float, default=15.0, help="Max distance in Angstrom")
    p.add_argument("--nbins", type=int, default=150, help="Number of histogram bins")
    p.add_argument("--skip_frames", type=int, default=0, help="Frames to skip at start")
    p.add_argument("--max_frames", type=int, default=None, help="Max frames to analyse")
    p.add_argument("--output_dir", type=str, default=None,
                   help="Output directory (default: <dump_dir>/analysis)")
    p.add_argument("--graphs_dir", type=str, default=None,
                   help="Directory for PNG figures (default: <output_dir>/figures/)")
    p.add_argument("--atom_style", type=str, default="id resid type charge x y z",
                   help="LAMMPS atom_style column order for the data file")
    return p.parse_args()


def _plot_rdf_all_pairs(rdf_data, graphs_dir):
    # rdf_data: dict of {pair_label: (bins_array, gr_array)}
    if not rdf_data:
        return
    apply_style()
    colors = plt.cm.tab10.colors
    fig, ax = plt.subplots(figsize=(9, 5))
    for i, (pair, (bins, gr)) in enumerate(rdf_data.items()):
        ax.plot(bins, gr, color=colors[i % len(colors)], label=pair)
    ax.axhline(1.0, color='k', ls='--', lw=0.8, alpha=0.5)
    ax.set_xlabel('r (Å)')
    ax.set_ylabel('g(r)')
    ax.set_title('Radial distribution functions')
    ncol = min(3, max(1, (len(rdf_data) + 4) // 5))
    ax.legend(loc='upper right', ncol=ncol, fontsize=9)
    save_fig(fig, str(graphs_dir / 'rdf_all_pairs.png'))


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

    # Determine frame range
    start = args.skip_frames
    stop = None
    if args.max_frames is not None:
        stop = start + args.max_frames
    n_frames_actual = len(u.trajectory[start:stop])
    print(f"  Analysing frames {start} to {stop or u.trajectory.n_frames} "
          f"({n_frames_actual} frames)", flush=True)

    # Determine atom type pairs
    if args.atom_type_pairs:
        pairs = json.loads(args.atom_type_pairs)
    else:
        unique_types = sorted(set(u.atoms.types))
        pairs = []
        for i, t1 in enumerate(unique_types):
            for t2 in unique_types[i:]:
                pairs.append([t1, t2])
        print(f"  Auto-detected {len(pairs)} type pairs from {len(unique_types)} types",
              flush=True)

    # Compute RDF for each pair
    rdf_files = {}
    rdf_memory = {}   # {pair_label: (bins, gr)} — kept in memory for plotting
    pairs_computed = []

    for t1, t2 in pairs:
        # MDA atom types are strings
        s1, s2 = str(t1), str(t2)
        g1 = u.select_atoms(f'type {s1}')
        g2 = u.select_atoms(f'type {s2}')

        if len(g1) == 0 or len(g2) == 0:
            print(f"  Skipping pair ({s1},{s2}): empty selection", flush=True)
            continue

        print(f"  Computing RDF for types ({s1},{s2}): "
              f"{len(g1)} x {len(g2)} atoms...", flush=True)

        # exclusion_block=None means no intramolecular exclusions
        # For same-type pairs, InterRDF handles the self-pair exclusion
        rdf_analysis = InterRDF(
            g1, g2,
            nbins=args.nbins,
            range=(0.0, args.rmax),
            norm='rdf',
        )
        rdf_analysis.run(start=start, stop=stop, verbose=True)

        # Extract results
        bins = rdf_analysis.results.bins
        gr = rdf_analysis.results.rdf

        # Write CSV
        fname = str(output_dir / f"rdf_t{s1}-t{s2}.csv")
        import pandas as pd
        pd.DataFrame({"r": bins, "g_r": gr}).to_csv(fname, index=False)
        rdf_files[f"{s1}-{s2}"] = fname
        rdf_memory[f"{s1}-{s2}"] = (bins, gr)
        pairs_computed.append(f"{s1}-{s2}")
        print(f"  Wrote {fname}", flush=True)

    # Summary
    summary = {
        "status": "success",
        "data_file": args.data_file,
        "dump_file": args.dump_file,
        "output_dir": str(output_dir),
        "rmax": args.rmax,
        "nbins": args.nbins,
        "frames_analysed": n_frames_actual,
        "pairs_computed": pairs_computed,
        "rdf_files": rdf_files,
        "method": "MDAnalysis.analysis.rdf.InterRDF",
        "mdanalysis_version": mda.__version__,
    }

    rdf_fig_png = str(graphs_dir / "rdf_all_pairs.png")
    try:
        _plot_rdf_all_pairs(rdf_memory, graphs_dir)
    except Exception as _pe:
        print(f"  WARNING: rdf_all_pairs plot failed: {_pe}", flush=True)
        rdf_fig_png = None
    summary["rdf_all_pairs_png"] = rdf_fig_png

    json_path = str(output_dir / "rdf_summary.json")
    with open(json_path, "w") as jf:
        json.dump(summary, jf, indent=2)

    # Print JSON to stdout for MCP parsing
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
