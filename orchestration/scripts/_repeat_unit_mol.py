#!/usr/bin/env python3
"""
_repeat_unit_mol.py — shared helper for turning a polymer repeat-unit SMILES (the
two-wildcard chain-end convention used throughout this repo) into a sanitized RDKit Mol
with the wildcard-adjacent backbone atoms' original H-counts preserved.

Factored out of estimate_tg_group_contribution.py's own (unchanged) wildcard-stripping
logic so backbone_rigidity.py can reuse it rather than re-deriving the same trick a
second time. Import-safe only where RDKit is already importable (the radonpy conda env);
callers already shell into that env before importing this module.
"""
from rdkit import Chem
from rdkit.Chem import RWMol


def prepare_repeat_unit(smiles: str):
    """(mol, head_idx, tail_idx) for a repeat-unit SMILES with exactly two `*` atoms,
    or (None, None, None) on any parse/sanitize failure, or a SMILES that doesn't have
    exactly two singly-bonded wildcard atoms.

    In a polymer SMILES like *CC*, the terminal C atoms each have an implicit H count of
    2 (backbone CH2) -- one bond goes to * (the chain), one to the next backbone atom.
    Replacing * with [H] would add a spurious H, turning CH2 into CH3. This function
    freezes the H count BEFORE removing the * atoms so the resulting molecule reflects
    true backbone connectivity.

    head_idx/tail_idx (indices in the RETURNED, post-removal mol) are the two atoms that
    were each bonded to one of the removed `*` atoms -- i.e. the backbone's
    chain-continuation points, which callers doing backbone-path analysis need as the
    path endpoints between the two ends of the repeat unit.
    """
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None, None, None
    wc_idxs = [a.GetIdx() for a in mol.GetAtoms() if a.GetAtomicNum() == 0]
    if len(wc_idxs) != 2:
        return None, None, None

    rw = RWMol(mol)
    endpoint_idxs = []
    for wc_idx in wc_idxs:
        wc_atom = rw.GetAtomWithIdx(wc_idx)
        nbrs = list(wc_atom.GetNeighbors())
        if len(nbrs) != 1:
            return None, None, None  # malformed: * should be a single-bonded chain-end marker
        endpoint_idxs.append(nbrs[0].GetIdx())
        n = rw.GetAtomWithIdx(nbrs[0].GetIdx())
        # GetTotalNumHs() returns implicit+explicit Hs as seen with * present
        h = n.GetTotalNumHs()
        n.SetNoImplicit(True)
        n.SetNumExplicitHs(h)

    # Remove wildcards from highest index downward (preserves lower indices), tracking
    # how each removal shifts the still-pending endpoint indices (RDKit reindexes on
    # RemoveAtom -- every atom after the removed index shifts down by one).
    for wc_idx in sorted(wc_idxs, reverse=True):
        rw.RemoveAtom(wc_idx)
        endpoint_idxs = [e - 1 if e > wc_idx else e for e in endpoint_idxs]

    try:
        Chem.SanitizeMol(rw)
    except Exception:
        return None, None, None

    return rw.GetMol(), endpoint_idxs[0], endpoint_idxs[1]
