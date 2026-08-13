#!/usr/bin/env python3
"""Measure 1,4-diene C=C microstructure (cis vs trans fraction) in a LAMMPS .data file.

The C=C torsion is the CH2-CH=CH-CH2 dihedral: |phi| near 0 deg is cis, near 180 deg is trans.
United-atom fields carry a single stereo-agnostic sp2 type, so the isomer is only readable from
geometry -- never from atom types.

Usage: measure_microstructure.py <data_file> [--mass-signature 14.0268,13.0189,13.0189,14.0268]
Prints JSON to stdout.
"""
import argparse
import collections
import json
import math
import sys

DEFAULT_SIGNATURE = (14.0268, 13.0189, 13.0189, 14.0268)  # CH2, CH(sp2), CH(sp2), CH2


def _sections(lines):
    keys = ("Masses", "Atoms", "Bonds", "Angles", "Dihedrals", "Impropers", "Velocities")
    return {s: i for i, l in enumerate(lines)
            for s in [l.split("#")[0].strip()] if s in keys}


def _block(lines, idx, name):
    i = idx[name] + 2
    out = []
    while i < len(lines):
        s = lines[i].split("#")[0].strip()
        if not s:
            if out:
                break
            i += 1
            continue
        out.append(s.split())
        i += 1
    return out


def measure(path, signature):
    lines = open(path).read().splitlines()
    idx = _sections(lines)
    for need in ("Masses", "Atoms", "Dihedrals"):
        if need not in idx:
            raise SystemExit(f"{path}: no {need} section")

    box = {}
    for l in lines[:60]:
        for tag in ("xlo", "ylo", "zlo"):
            if tag in l:
                f = l.split()
                box[tag[0]] = float(f[1]) - float(f[0])
    if len(box) != 3:
        raise SystemExit(f"{path}: could not read an orthogonal box")

    mass = {}
    for f in _block(lines, idx, "Masses"):
        mass[int(f[0])] = float(f[1])

    pos, typ = {}, {}
    for a in _block(lines, idx, "Atoms"):
        aid = int(a[0])
        typ[aid] = int(a[2])
        pos[aid] = (float(a[4]), float(a[5]), float(a[6]))

    L = (box["x"], box["y"], box["z"])

    def vec(a, b):
        return tuple(
            (pos[b][k] - pos[a][k]) - L[k] * round((pos[b][k] - pos[a][k]) / L[k])
            for k in range(3)
        )

    def cross(u, v):
        return (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])

    def dot(u, v):
        return sum(u[k] * v[k] for k in range(3))

    def dihedral(i, j, k, l):
        b1, b2, b3 = vec(i, j), vec(j, k), vec(k, l)
        n1, n2 = cross(b1, b2), cross(b2, b3)
        m = cross(n1, b2)
        return abs(math.degrees(math.atan2(dot(m, n2) / math.sqrt(dot(b2, b2)), dot(n1, n2))))

    by_type = collections.defaultdict(list)
    for d in _block(lines, idx, "Dihedrals"):
        by_type[int(d[1])].append([int(x) for x in d[2:6]])

    matched = []
    for dt, quads in sorted(by_type.items()):
        sig = tuple(round(mass[typ[a]], 4) for a in quads[0])
        if sig == signature or sig == signature[::-1]:
            matched.append((dt, quads))
    if not matched:
        raise SystemExit(
            f"{path}: no dihedral type matches mass signature {signature} — "
            "pass --mass-signature for this force field"
        )

    angles, types = [], []
    for dt, quads in matched:
        types.append(dt)
        angles.extend(dihedral(*q) for q in quads)

    n = len(angles)
    cis = sum(1 for a in angles if a < 90.0)
    return {
        "data_file": path,
        "dihedral_types": types,
        "n_cc_torsions": n,
        "cis_fraction": round(cis / n, 4),
        "trans_fraction": round((n - cis) / n, 4),
        "n_cis": cis,
        "n_trans": n - cis,
        "n_within_15deg_of_cis": sum(1 for a in angles if a < 15.0),
        "n_within_15deg_of_trans": sum(1 for a in angles if a > 165.0),
        "n_in_45_120_band": sum(1 for a in angles if 45.0 < a < 120.0),
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("data_file")
    p.add_argument("--mass-signature", default=",".join(str(m) for m in DEFAULT_SIGNATURE))
    a = p.parse_args()
    sig = tuple(round(float(x), 4) for x in a.mass_signature.split(","))
    json.dump(measure(a.data_file, sig), sys.stdout, indent=2)
    print()


if __name__ == "__main__":
    main()
