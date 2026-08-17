#!/usr/bin/env python3
"""
derive_backbone_types.py — Derive backbone_types from a LAMMPS .data file's bond topology alone.

Runs the heavy-atom bond-graph-diameter walk (backbone_topology.backbone_path) on every chain in
the file and unions the atom type IDs found along each chain's reconstructed backbone. No
simulation, no dump trajectory, no atom-type-name guessing — Masses + Bonds only, so this can run
immediately after a cell is built.

Output contract:
  - Prints a JSON summary to stdout as the last line.
  - Exit 0 on success, non-zero on failure (errors to stderr).

Usage:
    python derive_backbone_types.py --data_file /path/to/cell.data
"""

import argparse
import json
import sys

import MDAnalysis as mda

from backbone_topology import backbone_path


def derive(data_file: str) -> dict:
    u = mda.Universe(data_file)
    chain_ids = sorted(set(int(r) for r in u.atoms.resids))
    if not chain_ids:
        return {"status": "failed", "error": "no chains (resids) found in data file"}

    all_types = set()
    n_resolved = 0
    for cid in chain_ids:
        chain = u.select_atoms(f"resid {cid}")
        _, idx = backbone_path(chain)
        if idx is None:
            continue
        n_resolved += 1
        all_types.update(int(t) for t in u.atoms[idx].types)

    if not all_types:
        return {"status": "failed",
                "error": "no chain yielded a resolvable backbone (fewer than 2 heavy atoms, "
                         "or no bond topology, in every chain)",
                "n_chains": len(chain_ids)}

    return {
        "status": "success",
        "backbone_types": sorted(all_types),
        "method": "heavy_atom_graph_diameter",
        "n_chains": len(chain_ids),
        "n_chains_resolved": n_resolved,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Derive backbone_types from a LAMMPS .data file's bond topology."
    )
    parser.add_argument("--data_file", required=True, help="Path to the .data file.")
    args = parser.parse_args()

    try:
        result = derive(args.data_file)
    except Exception as e:
        result = {"status": "failed", "error": str(e)}

    print(json.dumps(result))
    sys.exit(0 if result.get("status") == "success" else 1)


if __name__ == "__main__":
    main()
