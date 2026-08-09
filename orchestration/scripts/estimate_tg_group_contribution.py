#!/usr/bin/env python3
"""
estimate_tg_group_contribution.py — Structural motif Tg estimator for polymer repeat units.

Uses a motif-based group contribution method: the repeat unit is partitioned into
non-overlapping structural motifs (whole functional units), each assigned a characteristic
Tg derived from known homopolymers. The estimate is a mass-weighted average of motif Tg.

Accuracy: ±80 K for polymers whose backbone chemistry resembles a known motif. The purpose
is to distinguish rubbery (Tg<300 K) from glassy and to bracket the Tg sweep range.
Always report confidence=low — this is NOT a substitute for measured Tg.

Usage:
  python3 orchestration/estimate_tg_group_contribution.py --smiles "*CC(C)(C(=O)OC)*"
  python3 orchestration/estimate_tg_group_contribution.py --smiles "*CC*" --output text
  python3 orchestration/estimate_tg_group_contribution.py --run-regressions
"""

import argparse
import json
import sys

try:
    from rdkit import Chem
    from rdkit.Chem import RWMol
except ImportError:
    print(json.dumps({
        "error": "RDKit not available. Install via: conda install -c conda-forge rdkit",
        "confidence": "unavailable",
    }))
    sys.exit(1)


def _prepare_repeat_unit(smiles: str):
    """Parse a polymer repeat-unit SMILES, removing chain-end wildcards (*) and
    preserving the correct H count on wildcard-adjacent atoms.

    In a polymer SMILES like *CC*, the terminal C atoms each have an implicit H
    count of 2 (backbone CH2) — one bond goes to * (the chain), one to the
    next backbone atom. Replacing * with [H] would add a spurious H, turning
    CH2 into CH3. This function freezes the H count BEFORE removing * atoms so
    that the resulting molecule reflects the true backbone connectivity.
    """
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    rw = RWMol(mol)

    # Identify wildcard atoms (atomic num 0 = *)
    wc_idxs = [a.GetIdx() for a in mol.GetAtoms() if a.GetAtomicNum() == 0]

    for wc_idx in wc_idxs:
        wc_atom = rw.GetAtomWithIdx(wc_idx)
        for nb in wc_atom.GetNeighbors():
            n = rw.GetAtomWithIdx(nb.GetIdx())
            # GetTotalNumHs() returns implicit+explicit Hs as seen with * present
            h = n.GetTotalNumHs()
            n.SetNoImplicit(True)
            n.SetNumExplicitHs(h)

    # Remove wildcards from highest index downward (preserves lower indices)
    for wc_idx in sorted(wc_idxs, reverse=True):
        rw.RemoveAtom(wc_idx)

    try:
        Chem.SanitizeMol(rw)
    except Exception:
        return None

    return rw.GetMol()


# ---------------------------------------------------------------------------
# Motif table: (name, SMARTS, tg_K, M_g_per_match)
#
# tg_K calibrated against known homopolymers (polymer_rules.json + literature):
#   PE:193, PEO:213, PS:373, PDMS:148, PMMA:378, PA6:330, PC:423, PSU:463, PI:673
#
# Priority: highest-Tg motifs first. Non-overlapping: once an atom is assigned,
# it is not re-matched. M_g_per_match is approximate (±10% acceptable).
# ---------------------------------------------------------------------------
_MOTIFS = [
    # name, SMARTS, tg_K, M_g_per_match
    # --- Imide (-N(CO)2-) ---
    ("imide",           "[N;H0]([C](=O))[C](=O)",                  640, 41),
    # --- Sulfone (-SO2-) ---
    ("sulfone",         "[#16](=[O])=[O]",                          460, 64),
    # --- Carbonate (-O-C(=O)-O-) ---
    ("carbonate",       "[O][C](=O)[O]",                            430, 60),
    # --- Amide (-C(=O)-NH-) ---
    ("amide",           "[C](=O)[NH]",                              400, 43),
    # --- Aromatic ether (Ar-O-Ar, PEEK-like) ---
    ("aryl_ether",      "[c][O][c]",                                390, 28),
    # --- Methacrylate unit: -CH2-C(CH3)(C(=O)O)- ---
    ("methacrylate",    "[CH2][C;H0;!a]([CH3])[C](=O)[O]",         360, 85),
    # --- Acrylate unit: -CH2-CH(C(=O)O)- ---
    ("acrylate",        "[CH2][CH1;!a][C](=O)[O]",                  290, 71),
    # --- Phenyl pendant on sp3 backbone ---
    ("phenyl_vinyl",    "[CX4;!a][c]1[cH][cH][cH][cH][cH]1",       430, 90),
    # --- 1,4-Phenylene in backbone ---
    ("phenylene",       "[c]1[cH][cH][c]([CX4,CX3])[cH][cH]1",     370, 76),
    # --- Generic ester / polyester (-C(=O)-O-) ---
    ("ester",           "[CX3](=O)[O;!H;!$(OC=O)]",                 310, 44),
    # --- PTFE (-CF2-CF2-) ---
    ("PTFE",            "[CF2][CF2]",                               390, 100),
    # --- PVDF (-CF2-CH2-) ---
    ("PVDF",            "[CF2][CH2]",                               240,  64),
    # --- Siloxane (-Si-O-) ---
    ("siloxane",        "[Si][O]",                                   148,  44),
    # --- Vinyl / diene ---
    ("vinyl",           "[CH2]=[CH]",                                200,  26),
    # --- Ether oxygen: detect single O in C-O-C or chain-end O ---
    ("ether_O",         "[O;!H;!$(O=*);!$(Oc=*);!$(O[C]=O)]",       240,  16),
    # --- Backbone carbons (lowest priority, catch-all) ---
    ("backbone_CH2",    "[CH2;!a;!$(C=*)]",                         193,  14),
    ("backbone_CH",     "[CH1;!a;!$(C=*)]",                         200,  13),
    ("backbone_Cq",     "[C;H0;!a;!$(C=*);!$(C#*);!$(C([F,Cl,Br]))]", 230,  12),
    ("methyl_pendant",  "[CH3;!a]",                                  150,  15),
]

_COMPILED: list[tuple] = []
for _name, _sma, _tg, _m in _MOTIFS:
    _pat = Chem.MolFromSmarts(_sma)
    if _pat is None:
        raise ValueError(f"Bad SMARTS for '{_name}': {_sma!r}")
    _COMPILED.append((_name, _tg, _m, _pat))


def estimate_tg(smiles: str) -> dict:
    """Estimate Tg and derived simulation temperatures from a polymer repeat-unit SMILES."""
    mol = _prepare_repeat_unit(smiles)
    if mol is None:
        return {"error": f"Could not parse SMILES: {smiles!r}", "confidence": "unavailable"}

    assigned: set[int] = set()
    hits: list[tuple[str, float, float]] = []

    for name, tg, M_motif, pat in _COMPILED:
        for match in mol.GetSubstructMatches(pat):
            if assigned.intersection(match):
                continue
            assigned.update(match)
            hits.append((name, tg, M_motif))

    # Heavy-atom coverage
    total_heavy = sum(1 for a in mol.GetAtoms() if a.GetAtomicNum() != 1)
    matched_heavy = len(assigned)
    unmatched_frac = max(0.0, 1.0 - matched_heavy / max(total_heavy, 1))

    if not hits:
        return {
            "error": "No structural motifs matched.",
            "confidence": "unavailable",
            "smiles": smiles,
        }

    total_Y = sum(tg * M for _, tg, M in hits)
    total_M = sum(M for _, _, M in hits)
    tg_est  = max(50, min(round(total_Y / total_M), 1100))

    T_equil        = tg_est + 200
    annealing_high = tg_est + 300
    tg_t_high      = max(round(tg_est * 1.5), T_equil + 20)
    tg_t_low       = max(round(tg_est * 0.65), 100)
    T_workflow     = 300.0 if tg_est < 300 else float(T_equil)

    confidence = "very_low" if unmatched_frac > 0.30 else "low"
    warning = None
    if unmatched_frac > 0.30:
        warning = (
            f"{unmatched_frac*100:.0f}% of heavy atoms unmatched; "
            "temperature estimates unreliable — leave global_defaults unchanged."
        )
    elif unmatched_frac > 0.10:
        warning = f"{unmatched_frac*100:.0f}% of heavy atoms unmatched; use with caution."

    return {
        "tg_estimated_K":        tg_est,
        "T_equil_K":             T_equil,
        "annealing_T_high_K":    annealing_high,
        "tg_t_high_K":           tg_t_high,
        "tg_t_low_K":            tg_t_low,
        "T_workflow_K":          T_workflow,
        "method":                "structural_motif_group_contribution",
        "confidence":            confidence,
        "motifs_matched":        [n for n, _, _ in hits],
        "unmatched_heavy_frac":  round(unmatched_frac, 3),
        "warning":               warning,
    }


# ---------------------------------------------------------------------------
# Regression guard — known polymers must land in expected range
# ---------------------------------------------------------------------------
def _check(label: str, smiles: str, lo: int, hi: int) -> None:
    r = estimate_tg(smiles)
    tg = r.get("tg_estimated_K")
    assert tg is not None, f"{label}: estimation failed — {r}"
    assert lo <= tg <= hi, (
        f"{label}: Tg={tg} K outside [{lo},{hi}]  motifs={r.get('motifs_matched')}"
    )


def run_regressions() -> None:
    _check("PMMA",  "*CC(C)(C(=O)OC)*",     270, 420)   # exp ~378 K
    _check("PE",    "*CC*",                  130, 240)   # exp ~195 K
    _check("PS",    "*CC(c1ccccc1)*",        290, 480)   # exp ~373 K
    _check("PDMS",  "*[Si](C)(C)O*",         100, 200)   # exp ~148 K
    _check("PEO",   "*OCCO*",                160, 280)   # exp ~213 K


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    p = argparse.ArgumentParser(
        description="Estimate polymer Tg and simulation temperatures from repeat-unit SMILES."
    )
    p.add_argument("--smiles", default=None)
    p.add_argument("--output", choices=["json", "text"], default="json")
    p.add_argument("--run-regressions", action="store_true")
    args = p.parse_args()

    if args.run_regressions:
        run_regressions()
        print("All regressions passed.")
        return

    if not args.smiles:
        p.error("--smiles is required")

    r = estimate_tg(args.smiles)

    if args.output == "json":
        print(json.dumps(r, indent=2))
    else:
        if "error" in r:
            print(f"ERROR: {r['error']}", file=sys.stderr)
            sys.exit(1)
        print(f"Tg estimate:          {r['tg_estimated_K']} K  ({r['confidence']})")
        print(f"T_equil_K:            {r['T_equil_K']} K")
        print(f"annealing_T_high_K:   {r['annealing_T_high_K']} K")
        print(f"tg_t_high_K:          {r['tg_t_high_K']} K")
        print(f"tg_t_low_K:           {r['tg_t_low_K']} K")
        print(f"T_workflow_K:         {r['T_workflow_K']} K")
        print(f"Motifs:               {r['motifs_matched']}")
        if r["warning"]:
            print(f"WARNING: {r['warning']}")


if __name__ == "__main__":
    main()
