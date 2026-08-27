#!/usr/bin/env python3
"""
backbone_rigidity.py — backbone-path rigidity classifier for polymer repeat-unit SMILES.

Parses a repeat-unit SMILES (the two-`*`-wildcard convention used throughout this repo),
finds the backbone path between the two chain-end atoms, and computes rigidity metrics
RESTRICTED TO THAT PATH -- not the whole molecule. This distinction is the whole point:
polystyrene's and PMMA's pendant aromatic/ester groups sit off the backbone path and must
NOT make those polymers look stiff, while a backbone like PEEK's or PSU's, where the
aromatic rings really are in-chain, correctly does.

Used by orchestration/scripts/select_system_size.py's solve_system_size() to classify a
polymer as flexible / semi-rigid / stiff, which decides whether a plan-time DP
recommendation needs a literature Kuhn-length check on top of the plain molecular-weight
baseline (see that file's _kuhn_floor). This is purely a structural classification (bond
counting) -- it estimates NO physical quantity (no Kuhn length, no persistence length,
no Rg) and is not the "invented-physics shortcut" select_system_size.py's own docstring
warns against; that estimation stays a literature-search responsibility (see
.claude/agents/system-size-literature-worker.md), never a heuristic derived here.

Usage:
  python3 orchestration/scripts/backbone_rigidity.py --smiles "*CC(*)c1ccccc1"
Prints JSON, {"error": ...} + exit 1 on unparseable SMILES or a SMILES without exactly
two `*` atoms; success payload + exit 0 otherwise -- same contract as
estimate_tg_group_contribution.py.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from rdkit import Chem
    from _repeat_unit_mol import prepare_repeat_unit
except ImportError:
    print(json.dumps({
        "error": "RDKit not available. Install via: conda install -c conda-forge rdkit",
    }))
    sys.exit(1)


# Classification thresholds -- no repo precedent existed for these numbers before this
# module; chosen and hand-validated against reference polymers (see
# tests/test_backbone_rigidity.py). The three correctness cases that drove the choice:
#   - PS/PMMA must land flexible: their pendant aromatic/ester groups are off the
#     backbone path, so backbone_rotatable_fraction=1.0, backbone_ring_fraction=0.0.
#   - PET must land semi-rigid: one in-path phenylene ring per repeat unit amid flexible
#     ester/glycol linkages gives backbone_ring_fraction=0.40 exactly -- a first pass at
#     STIFF_RING_FRACTION_MIN=0.40 put PET in "stiff" with no margin, which is wrong: PET
#     is a real semi-rigid anchor, meaningfully less rigid than PEEK/PSU below.
#   - PEEK/PSU must land stiff: their aromatic rings ARE in the backbone path, giving
#     backbone_ring_fraction=0.80 -- a full factor of 2 above PET's 0.40, which is why
#     the threshold sits at the midpoint (0.50) rather than right at PET's value.
FLEXIBLE_ROTATABLE_FRACTION_MIN = 0.5
FLEXIBLE_RING_FRACTION_MAX = 0.15
STIFF_RING_FRACTION_MIN = 0.50
STIFF_ROTATABLE_FRACTION_MAX = 0.15


def _is_amide_like(mol, a1, a2) -> bool:
    """True if the single bond between a1/a2 is a C-N bond where the C also carries a
    C=O (amide/imide) -- these are conjugated and effectively non-rotatable at
    MD-relevant timescales, which is what actually makes polyamide/polyimide backbones
    rigid, not just their ring content."""
    syms = {a1.GetSymbol(), a2.GetSymbol()}
    if syms != {"C", "N"}:
        return False
    carbon = a1 if a1.GetSymbol() == "C" else a2
    for nb in carbon.GetNeighbors():
        if nb.GetSymbol() == "O":
            bond = mol.GetBondBetweenAtoms(carbon.GetIdx(), nb.GetIdx())
            if bond.GetBondType() == Chem.BondType.DOUBLE:
                return True
    return False


def analyze(smiles: str) -> dict:
    mol, head_idx, tail_idx = prepare_repeat_unit(smiles)
    if mol is None:
        return {"error": f"Could not parse SMILES or find exactly two `*` atoms: {smiles!r}"}

    path = list(Chem.GetShortestPath(mol, head_idx, tail_idx))
    if len(path) < 2:
        return {"error": (f"Backbone path between the two chain-end atoms has fewer than "
                          f"2 atoms (both `*` attach to the same atom?): {smiles!r}")}

    bonds = [mol.GetBondBetweenAtoms(path[i], path[i + 1]) for i in range(len(path) - 1)]
    n_bonds = len(bonds)

    rigid_flags = []  # True = non-rotatable (rigid) bond, aligned with `bonds`
    n_rotatable = 0
    for bond in bonds:
        a1, a2 = bond.GetBeginAtom(), bond.GetEndAtom()
        is_single = bond.GetBondType() == Chem.BondType.SINGLE
        in_ring = bond.IsInRing()
        amide_like = is_single and not in_ring and _is_amide_like(mol, a1, a2)
        rotatable = is_single and not in_ring and not amide_like
        rigid_flags.append(not rotatable)
        if rotatable:
            n_rotatable += 1
    rotatable_fraction = n_rotatable / n_bonds if n_bonds else 0.0

    ring_atoms = sum(1 for idx in path if mol.GetAtomWithIdx(idx).IsInRing())
    ring_fraction = ring_atoms / len(path)

    longest_rigid_run = 1
    current_run = 1
    for flag in rigid_flags:
        if flag:
            current_run += 1
            longest_rigid_run = max(longest_rigid_run, current_run)
        else:
            current_run = 1

    if rotatable_fraction >= FLEXIBLE_ROTATABLE_FRACTION_MIN and ring_fraction < FLEXIBLE_RING_FRACTION_MAX:
        rigidity_class = "flexible"
    elif ring_fraction >= STIFF_RING_FRACTION_MIN or rotatable_fraction < STIFF_ROTATABLE_FRACTION_MAX:
        rigidity_class = "stiff"
    else:
        rigidity_class = "semi_rigid"

    note = (f"backbone_rotatable_fraction={rotatable_fraction:.2f}, "
            f"backbone_ring_fraction={ring_fraction:.2f}, "
            f"longest_rigid_backbone_run={longest_rigid_run} atoms -> {rigidity_class}")

    return {
        "smiles": smiles,
        "backbone_path_atom_count": len(path),
        "backbone_rotatable_fraction": round(rotatable_fraction, 3),
        "backbone_ring_fraction": round(ring_fraction, 3),
        "longest_rigid_backbone_run": longest_rigid_run,
        "rigidity_class": rigidity_class,
        "classification_note": note,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--smiles", required=True)
    p.add_argument("--output", choices=["json"], default="json")
    args = p.parse_args()

    result = analyze(args.smiles)
    print(json.dumps(result, indent=2))
    return 1 if "error" in result else 0


if __name__ == "__main__":
    sys.exit(main())
