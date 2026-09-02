#!/usr/bin/env python3
"""
rdkit_cli.py — every RDKit computation this repo runs, behind one CLI.

RDKit lives in the `radonpy`/`mol-builder` conda envs, never in the environment the
orchestration layer itself runs in, so each of these computations has to cross a
subprocess boundary via mol_python.run_in_mol_env(). Before 2026-09-02 those five
computations were spread across six files in three different shapes: two standalone CLI scripts
(backbone_rigidity.py, estimate_tg_group_contribution.py), a helper module those two
imported on the far side of the boundary (_repeat_unit_mol.py), and three RDKit snippets
embedded as string literals inside base-env modules (canon_smiles._PY_SNIPPET,
chem_similarity._PY_SNIPPET, select_hardware._RDKIT_SNIPPET) -- the last three invisible
to every grep for `from rdkit import`, and none of them able to share a line of code with
the others. This file is all five, so the wildcard-stripping trick is written once and
the in-env dependency is one path.

IMPORT-SAFE ONLY IN THE MOL ENVIRONMENT. This module is a CLI, not a library: base-env
callers must reach it through mol_python.run_in_mol_env(script_path=RDKIT_CLI, ...), which
is what every wrapper listed below already does. Do not `import rdkit_cli` from
orchestration code.

Subcommands, and the wrapper each one exists for:
  canon         -> canon_smiles.canonicalize()            (novelty-gate/evidence-store keys)
  similarity    -> chem_similarity.compute_similarities() (protocol-evidence retrieval)
  monomer-info  -> select_hardware._monomer_atoms_and_mw() (cell sizing + D-08 hardware)
  tg-estimate   -> stage_params._estimate_tg_group_contribution() (exp-Tg fallback/bracket)
  rigidity      -> select_system_size._backbone_rigidity() (D-04 chain-length advisory)

Output contracts differ per subcommand ON PURPOSE -- each wrapper's error handling was
written against its own, and unifying them would silently change wrapper behavior:
  canon, monomer-info  success JSON on stdout; failure raises SystemExit, so the message
                       lands on stderr with a nonzero exit and the wrapper's RuntimeError
                       carries it.
  similarity           always exit 0; per-SMILES failures are collected in "errors" so one
                       bad candidate never sinks a whole batch.
  tg-estimate          {"error": ...} JSON on stdout, exit 0 (json mode); the wrapper tests
                       for the key, and an unestimable Tg is not a crash.
  rigidity             {"error": ...} JSON on stdout, exit 1.

Usage:
  python3 orchestration/scripts/rdkit_cli.py canon --smiles '*CC*'
  python3 orchestration/scripts/rdkit_cli.py rigidity --smiles '*CC(*)c1ccccc1'
  python3 orchestration/scripts/rdkit_cli.py tg-estimate --smiles '*CC*' --output text
"""
import argparse
import json
import sys

try:
    from rdkit import Chem
    from rdkit.Chem import AllChem, DataStructs, Descriptors, RWMol
except ImportError:
    # "confidence" is part of estimate_tg_group_contribution's historical payload; harmless
    # for the other subcommands, and dropping it would change that one wrapper's contract.
    print(json.dumps({
        "error": "RDKit not available. Install via: conda install -c conda-forge rdkit",
        "confidence": "unavailable",
    }))
    sys.exit(1)


# ---------------------------------------------------------------------------
# Shared: repeat-unit preparation (used by tg-estimate and rigidity)
# ---------------------------------------------------------------------------
def _prepare_repeat_unit(smiles: str):
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
    path endpoints between the two ends of the repeat unit. tg-estimate ignores them; the
    rigidity subcommand is built on them.
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


# ---------------------------------------------------------------------------
# canon
# ---------------------------------------------------------------------------
def _cmd_canon(args) -> int:
    mol = Chem.MolFromSmiles(args.smiles)
    if mol is None:
        raise SystemExit("RDKit could not parse SMILES: " + args.smiles)
    canonical = Chem.MolToSmiles(mol, canonical=True, isomericSmiles=not args.no_isomeric)
    print(json.dumps({"smiles": args.smiles, "canonical_smiles": canonical}))
    return 0


# ---------------------------------------------------------------------------
# similarity
# ---------------------------------------------------------------------------
def _cmd_similarity(args) -> int:
    """Tanimoto over Morgan fingerprints, whole batch in one process.

    The candidate list arrives as a JSON file rather than argv: a query against every
    class's member_smiles at once is far past a comfortable argv length, and a file also
    keeps SMILES stereo markers (forward and back slashes) out of shell text entirely.
    """
    with open(args.input) as f:
        payload = json.load(f)

    query = payload["query"]
    candidates = payload["candidates"]
    radius = payload.get("radius", 2)
    n_bits = payload.get("n_bits", 2048)

    def fp(smi):
        mol = Chem.MolFromSmiles(smi)
        if mol is None:
            return None
        return AllChem.GetMorganFingerprintAsBitVect(mol, radius, nBits=n_bits)

    errors = []
    query_fp = fp(query)
    if query_fp is None:
        errors.append(f"query SMILES did not parse: {query}")

    scores = {}
    for cand in candidates:
        if query_fp is None:
            break
        cand_fp = fp(cand)
        if cand_fp is None:
            errors.append(f"candidate SMILES did not parse: {cand}")
            continue
        scores[cand] = DataStructs.TanimotoSimilarity(query_fp, cand_fp)

    print(json.dumps({"scores": scores, "errors": errors}))
    return 0


# ---------------------------------------------------------------------------
# monomer-info
# ---------------------------------------------------------------------------
def _cmd_monomer_info(args) -> int:
    """Atom count and molar mass for one repeat unit.

    The count is heavy-atom for united-atom force fields (--ua, e.g. TraPPE) and all-atom
    with hydrogens otherwise; the mass is always all-atom.
    """
    mol = Chem.MolFromSmiles(args.smiles)
    if mol is None:
        raise SystemExit("RDKit could not parse SMILES: " + args.smiles)
    # The two `*` connection points parse as dummy atoms: discount them from the atom count
    # rather than deleting them from the string, which would leave an empty branch `c(...)` ->
    # `c()` and fail to parse for any SMILES whose `*` sits inside a branch.
    dummies = sum(1 for a in mol.GetAtoms() if a.GetAtomicNum() == 0)
    with_h = Chem.AddHs(mol)
    n_atoms = (mol.GetNumAtoms() if args.ua else with_h.GetNumAtoms()) - dummies
    # Dummy atoms carry zero mass, so this is the repeat unit's residue mass as it appears
    # in the chain -- exactly what the cell-mass estimate needs.
    print(json.dumps({"n_atoms": n_atoms, "mw_g_per_mol": Descriptors.MolWt(with_h)}))
    return 0


# ---------------------------------------------------------------------------
# tg-estimate
#
# Motif-based group contribution: the repeat unit is partitioned into non-overlapping
# structural motifs (whole functional units), each assigned a characteristic Tg derived
# from known homopolymers. The estimate is a mass-weighted average of motif Tg.
#
# Accuracy: +-80 K for polymers whose backbone chemistry resembles a known motif. The
# purpose is to distinguish rubbery (Tg<300 K) from glassy and to bracket the Tg sweep
# range. Always report confidence=low -- this is NOT a substitute for measured Tg.
#
# Motif table: (name, SMARTS, tg_K, M_g_per_match)
#
# tg_K calibrated against known homopolymers (polymer_rules.json + literature):
#   PE:193, PEO:213, PS:373, PDMS:148, PMMA:378, PA6:330, PC:423, PSU:463, PI:673
#
# Priority: highest-Tg motifs first. Non-overlapping: once an atom is assigned,
# it is not re-matched. M_g_per_match is approximate (+-10% acceptable).
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

_COMPILED: list = []


def _compiled_motifs() -> list:
    """Compile the motif SMARTS once, on first use rather than at import: a `canon` or
    `similarity` call has no business paying for -- or failing on -- this table."""
    if not _COMPILED:
        for name, sma, tg, m in _MOTIFS:
            pat = Chem.MolFromSmarts(sma)
            if pat is None:
                raise ValueError(f"Bad SMARTS for '{name}': {sma!r}")
            _COMPILED.append((name, tg, m, pat))
    return _COMPILED


def estimate_tg(smiles: str) -> dict:
    """Estimate Tg and derived simulation temperatures from a polymer repeat-unit SMILES."""
    mol, _head, _tail = _prepare_repeat_unit(smiles)
    if mol is None:
        return {"error": f"Could not parse SMILES: {smiles!r}", "confidence": "unavailable"}

    assigned: set = set()
    hits: list = []

    for name, tg, M_motif, pat in _compiled_motifs():
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


# Regression guard — known polymers must land in expected range
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


def _cmd_tg_estimate(args) -> int:
    if args.run_regressions:
        run_regressions()
        print("All regressions passed.")
        return 0

    if not args.smiles:
        raise SystemExit("tg-estimate: --smiles is required")

    r = estimate_tg(args.smiles)

    if args.output == "json":
        print(json.dumps(r, indent=2))
        # Deliberately exit 0 even on {"error": ...}: stage_params tests for the key, and a
        # SMILES no motif matches is a low-confidence miss, not a failed subprocess.
        return 0

    if "error" in r:
        print(f"ERROR: {r['error']}", file=sys.stderr)
        return 1
    print(f"Tg estimate:          {r['tg_estimated_K']} K  ({r['confidence']})")
    print(f"T_equil_K:            {r['T_equil_K']} K")
    print(f"annealing_T_high_K:   {r['annealing_T_high_K']} K")
    print(f"tg_t_high_K:          {r['tg_t_high_K']} K")
    print(f"tg_t_low_K:           {r['tg_t_low_K']} K")
    print(f"T_workflow_K:         {r['T_workflow_K']} K")
    print(f"Motifs:               {r['motifs_matched']}")
    if r["warning"]:
        print(f"WARNING: {r['warning']}")
    return 0


# ---------------------------------------------------------------------------
# rigidity
#
# Backbone-path rigidity classifier. Finds the backbone path between the two chain-end
# atoms and computes rigidity metrics RESTRICTED TO THAT PATH -- not the whole molecule.
# This distinction is the whole point: polystyrene's and PMMA's pendant aromatic/ester
# groups sit off the backbone path and must NOT make those polymers look stiff, while a
# backbone like PEEK's or PSU's, where the aromatic rings really are in-chain, correctly
# does.
#
# Consumed by select_system_size.py's solve_system_size(), which reports a stiff/semi-rigid
# result as the RIGID_BACKBONE_CHAIN_LENGTH_BIAS uncertainty. Purely a structural
# classification (bond counting) -- it estimates NO physical quantity (no Kuhn length, no
# persistence length, no Rg) and is not the "invented-physics shortcut" that module's
# docstring warns against; that estimation stays a literature-search responsibility (see
# .claude/agents/literature-grounding-worker.md's Part B), never a heuristic derived here.
#
# Classification thresholds -- no repo precedent existed for these numbers before this
# code; chosen and hand-validated against reference polymers (see
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
# ---------------------------------------------------------------------------
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
    mol, head_idx, tail_idx = _prepare_repeat_unit(smiles)
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


def _cmd_rigidity(args) -> int:
    result = analyze(args.smiles)
    print(json.dumps(result, indent=2))
    return 1 if "error" in result else 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)

    c = sub.add_parser("canon", help="canonicalize a SMILES")
    c.add_argument("--smiles", required=True)
    c.add_argument("--no-isomeric", action="store_true",
                   help="drop stereochemistry (matches the member_smiles convention)")
    c.set_defaults(func=_cmd_canon)

    c = sub.add_parser("similarity", help="Morgan/Tanimoto similarity, one batch per call")
    c.add_argument("--input", required=True,
                   help="JSON file: {query, candidates[], radius?, n_bits?}")
    c.set_defaults(func=_cmd_similarity)

    c = sub.add_parser("monomer-info", help="repeat-unit atom count and molar mass")
    c.add_argument("--smiles", required=True)
    c.add_argument("--ua", action="store_true",
                   help="heavy-atom count for united-atom force fields (e.g. TraPPE)")
    c.set_defaults(func=_cmd_monomer_info)

    c = sub.add_parser("tg-estimate", help="structural-motif group-contribution Tg estimate")
    c.add_argument("--smiles", default=None)
    c.add_argument("--output", choices=["json", "text"], default="json")
    c.add_argument("--run-regressions", action="store_true")
    c.set_defaults(func=_cmd_tg_estimate)

    c = sub.add_parser("rigidity", help="backbone-path rigidity classification")
    c.add_argument("--smiles", required=True)
    c.set_defaults(func=_cmd_rigidity)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
