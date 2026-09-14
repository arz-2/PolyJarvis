#!/usr/bin/env python3
"""Per-chain radius of gyration from a LAMMPS dump, written as RadonPy's rg.profile.

RadonPy's Rg criterion reads `fix ave/time 1 1000 1000 c_gyr1 file rgN.profile mode vector`,
where gyr1 is `compute gyration/chunk` over molecule chunks: mass-weighted, on image-unwrapped
coordinates. PolyJarvis never writes that file, so this rebuilds it from the dump the run kept,
in the exact format RadonPy's own `Analyze.parse_ave` reads. RadonPy's `calc_rg` -- not a
re-implementation of it -- then computes the statistic.

One bias, stated rather than corrected: RadonPy's profile holds 1000-step running averages
(Nevery 1, Nrepeat 1000); a dump holds one instantaneous snapshot per 1000 steps. Snapshot noise
inflates the per-chain time sd, so this can only make a PolyJarvis cell look LESS converged under
RadonPy's rule, never more.

Usage:
    python rg_profile.py --dump npt_production.dump --data npt_production_out.data --out rg.profile
"""
from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path

import numpy as np

REQUIRED_COLUMNS = ("type", "mol", "x", "y", "z", "ix", "iy", "iz")


def read_masses(data_file) -> dict[int, float]:
    """The Masses section of a LAMMPS data file, {atom type: mass}."""
    masses: dict[int, float] = {}
    in_masses = False
    with open(data_file) as fh:
        for line in fh:
            s = line.split("#")[0].strip()
            if not in_masses:
                in_masses = s == "Masses"
                continue
            if not s:
                if masses:
                    break
                continue
            tok = s.split()
            if not tok[0].isdigit():
                break
            masses[int(tok[0])] = float(tok[1])
    if not masses:
        raise ValueError(f"no Masses section in {data_file}")
    return masses


def iter_dump_frames(path):
    """Yield (timestep, box_lengths, columns, array) per frame of a LAMMPS text dump.

    A final frame cut short by a killed run is dropped rather than reshaped into garbage.
    """
    with open(path) as fh:
        while True:
            line = fh.readline()
            if not line:
                return
            if not line.startswith("ITEM: TIMESTEP"):
                continue
            timestep = int(fh.readline())
            fh.readline()  # ITEM: NUMBER OF ATOMS
            n_atoms = int(fh.readline())
            fh.readline()  # ITEM: BOX BOUNDS
            bounds = np.array([[float(v) for v in fh.readline().split()[:2]] for _ in range(3)])
            columns = fh.readline().split()[2:]
            tokens = "".join(itertools.islice(fh, n_atoms)).split()
            if len(tokens) != n_atoms * len(columns):
                return
            arr = np.array(tokens, dtype=float).reshape(n_atoms, len(columns))
            yield timestep, bounds[:, 1] - bounds[:, 0], columns, arr


def chain_rg(columns, arr, box_lengths, masses: dict[int, float]):
    """(sorted molecule ids, mass-weighted Rg per molecule) for one frame -- what
    `compute gyration/chunk` over molecule chunks reports."""
    idx = {c: i for i, c in enumerate(columns)}
    missing = [c for c in REQUIRED_COLUMNS if c not in idx]
    if missing:
        raise ValueError(f"dump lacks columns {missing}; has {columns}")

    types = arr[:, idx["type"]].astype(int)
    mass_lut = np.zeros(max(masses) + 1)
    for t, m in masses.items():
        mass_lut[t] = m
    m = mass_lut[types]

    xyz = np.column_stack([arr[:, idx[c]] + arr[:, idx[i]] * L
                           for c, i, L in zip("xyz", ("ix", "iy", "iz"), box_lengths)])
    mol_ids, inv = np.unique(arr[:, idx["mol"]].astype(int), return_inverse=True)
    total = np.bincount(inv, m)
    com = np.column_stack([np.bincount(inv, m * xyz[:, k]) / total for k in range(3)])
    d2 = ((xyz - com[inv]) ** 2).sum(axis=1)
    return mol_ids, np.sqrt(np.bincount(inv, m * d2) / total)


def write_ave_vector(path, timesteps, rg_rows, fix_id="rg1", compute_id="c_gyr1"):
    """LAMMPS `fix ave/time ... mode vector` output: three header lines, then per output a
    `<timestep> <nrows>` line followed by `<row> <value>` lines."""
    with open(path, "w") as fh:
        fh.write(f"# Time-averaged data for fix {fix_id}\n")
        fh.write("# TimeStep Number-of-rows\n")
        fh.write(f"# Row {compute_id}\n")
        for ts, row in zip(timesteps, rg_rows):
            fh.write(f"{int(ts)} {len(row)}\n")
            for i, value in enumerate(row, start=1):
                fh.write(f"{i} {value:.8f}\n")


def build_profile(dump, data, out) -> dict:
    """Write the profile and return the Rg matrix's own summary, for the round-trip check."""
    masses = read_masses(data)
    timesteps, rows, mol_ids = [], [], None
    for ts, box, columns, arr in iter_dump_frames(dump):
        ids, rg = chain_rg(columns, arr, box, masses)
        if mol_ids is None:
            mol_ids = ids
        elif not np.array_equal(ids, mol_ids):
            raise ValueError(f"molecule set changed at timestep {ts}")
        timesteps.append(ts)
        rows.append(rg)
    if not rows:
        raise ValueError(f"no complete frames in {dump}")
    write_ave_vector(out, timesteps, rows)
    matrix = np.array(rows)
    steps = np.diff(timesteps)
    return {"profile": str(out), "dump": str(dump), "data": str(data),
            "n_frames": len(rows), "n_chains": int(matrix.shape[1]),
            "mol_ids": [int(i) for i in mol_ids],
            "timestep_interval": int(steps[0]) if len(steps) and np.all(steps == steps[0]) else None,
            "mean_Rg_A": float(matrix.mean()),
            "matrix": matrix}


def window_stats(matrix: np.ndarray, width: int) -> dict:
    """calc_rg's statistics on the last `width` outputs, in numpy, for comparison against what
    RadonPy computes from the written file. Population sd (ddof 0), as calc_rg uses."""
    tail = matrix[-width:]
    sd = tail.std(axis=0)
    means = tail.mean(axis=0)
    return {"sd_max": float(sd.max()), "mean_mean": float(means.mean()), "n_frames": len(tail)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dump", required=True)
    parser.add_argument("--data", required=True, help="data file carrying the Masses section")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    summary = build_profile(args.dump, args.data, args.out)
    summary.pop("matrix")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
