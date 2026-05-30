#!/usr/bin/env python3
"""
unwrap_dump.py — Write a new LAMMPS dump file with fully unwrapped coordinates.

Reads every frame of a LAMMPS dump file, applies image-flag unwrapping
(x_unwrap = x + ix*Lx), and writes a new dump where x/y/z hold unwrapped
Cartesian positions and ix/iy/iz are zeroed out.

Output contract:
  - Prints a JSON summary line to stdout as the last output.
  - Writes the unwrapped dump file to --output_file.
  - Exit 0 on success, non-zero on failure (errors to stderr).

Usage:
    python unwrap_dump.py --dump_file /path/to/wrapped.dump \
                          --output_file /path/to/unwrapped.dump
"""

import argparse
import json
import os
import sys
import numpy as np
import pandas as pd
from pathlib import Path


# ---------------------------------------------------------------------------
# LAMMPS dump parsing helpers
# ---------------------------------------------------------------------------

def parse_lammps_dump_frame(fh):
    """
    Read one frame from an already-open LAMMPS dump file.
    Returns a dict with keys: timestep, natoms, box (np array), df (DataFrame).
    Returns None at EOF or on a malformed header.
    """
    line = fh.readline()
    if not line:
        return None
    if "ITEM: TIMESTEP" not in line:
        return None
    timestep = int(fh.readline().strip())

    fh.readline()  # ITEM: NUMBER OF ATOMS
    natoms = int(fh.readline().strip())

    fh.readline()  # ITEM: BOX BOUNDS …
    box = np.array([
        list(map(float, fh.readline().split()[:2])) for _ in range(3)
    ])

    header = fh.readline()  # ITEM: ATOMS col1 col2 …
    columns = header.strip().split()[2:]

    rows = [fh.readline().split() for _ in range(natoms)]
    df = pd.DataFrame(rows, columns=columns)
    for col in columns:
        try:
            df[col] = pd.to_numeric(df[col])
        except (ValueError, TypeError):
            pass

    return {"timestep": timestep, "natoms": natoms, "box": box, "df": df}


def unwrap_frame(df, box):
    """
    Return an (N, 3) array of unwrapped coordinates.
    Prefers unwrapped columns (xu, yu, zu) if present, otherwise
    uses image flags (ix, iy, iz) with formula x + ix * Lx.
    Falls back to wrapped coords only if neither is available.
    """
    has_unwrapped = all(c in df.columns for c in ("xu", "yu", "zu"))
    has_images    = all(c in df.columns for c in ("ix", "iy", "iz"))
    if has_unwrapped:
        return df[["xu", "yu", "zu"]].values.astype(float)
    elif has_images:
        coords  = df[["x", "y", "z"]].values.astype(float)
        images  = df[["ix", "iy", "iz"]].values.astype(float)
        lengths = (box[:, 1] - box[:, 0]).reshape(1, 3)
        return coords + images * lengths
    else:
        print("WARNING: no unwrapped coords or image flags — using wrapped x,y,z",
              flush=True)
        return df[["x", "y", "z"]].values.astype(float)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Unwrap coordinates in a LAMMPS dump file using image flags."
    )
    parser.add_argument("--dump_file", required=True,
                        help="Path to the wrapped LAMMPS dump file.")
    parser.add_argument("--output_file", required=True,
                        help="Destination path for the unwrapped dump file.")
    args = parser.parse_args()

    dump_file = args.dump_file
    output_file = args.output_file

    # Ensure parent directory exists
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)

    frames_written = 0
    natoms_last = 0

    with open(dump_file, "r") as fin, open(output_file, "w") as fout:
        while True:
            frame = parse_lammps_dump_frame(fin)
            if frame is None:
                break

            df = frame["df"]
            box = frame["box"]
            cols = list(df.columns)

            # Validate image flags are present
            for flag in ("ix", "iy", "iz"):
                if flag not in cols:
                    raise ValueError(
                        f"Column '{flag}' missing from dump. "
                        "Dump must be written with 'dump … id mol type x y z ix iy iz' "
                        "(or similar including image flags)."
                    )

            # Compute unwrapped positions, zero out image flags
            unwrapped = unwrap_frame(df, box)
            df = df.copy()
            df["x"]  = unwrapped[:, 0]
            df["y"]  = unwrapped[:, 1]
            df["z"]  = unwrapped[:, 2]
            df["ix"] = 0
            df["iy"] = 0
            df["iz"] = 0

            # Write LAMMPS dump header
            fout.write("ITEM: TIMESTEP\n")
            fout.write(f"{frame['timestep']}\n")
            fout.write("ITEM: NUMBER OF ATOMS\n")
            fout.write(f"{frame['natoms']}\n")
            fout.write("ITEM: BOX BOUNDS pp pp pp\n")
            for lo, hi in frame["box"]:
                fout.write(f"{lo:.10f} {hi:.10f}\n")
            fout.write("ITEM: ATOMS " + " ".join(cols) + "\n")

            # Determine per-column format: integer for id/mol/type/image flags, float otherwise
            int_cols = {"id", "mol", "type", "ix", "iy", "iz"}
            fmt = " ".join("%d" if c in int_cols else "%.6f" for c in cols)
            np.savetxt(fout, df.values.astype(float), fmt=fmt)

            frames_written += 1
            natoms_last = frame["natoms"]

            if frames_written % 500 == 0:
                print(f"  unwrap: {frames_written} frames written...", flush=True)

    size_bytes = os.path.getsize(output_file)
    print(json.dumps({
        "status":         "success",
        "output_file":    output_file,
        "frames_written": frames_written,
        "natoms":         natoms_last,
        "size_bytes":     size_bytes,
    }))


if __name__ == "__main__":
    main()
