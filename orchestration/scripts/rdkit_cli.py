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

The `classify` subcommand additionally needs RadonPy (installed in the `mol-builder`
env, not `radonpy`); its import is deliberately deferred into the handler so every
other subcommand keeps working wherever only RDKit is present -- notably CI, which
sets POLYJARVIS_MOL_PYTHON to a venv holding rdkit and no RadonPy.

IMPORT-SAFE ONLY IN THE MOL ENVIRONMENT. This module is a CLI, not a library: base-env
callers must reach it through mol_python.run_in_mol_env(script_path=RDKIT_CLI, ...), which
is what every wrapper listed below already does. Do not `import rdkit_cli` from
orchestration code.

Subcommands, and the wrapper each one exists for:
  canon         -> rules_common.canonicalize()            (novelty-gate/evidence-store keys)
  similarity    -> chem_similarity.compute_similarities() (protocol-evidence retrieval)
  monomer-info  -> select_hardware._monomer_atoms_and_mw() (cell sizing + D-08 hardware)
  tg-estimate   -> stage_params._estimate_tg_group_contribution() (exp-Tg fallback/bracket)
  rigidity      -> select_system_size._backbone_rigidity() (D-04 chain-length advisory)
  match-moieties-> forcefield.select_by_moiety()           (D-01 build-blocker screen)
  classify      -> classify_cli.classify_polymer()         (polymer_class + group profile)
  chemistry     -> classify_cli.chemistry_profile()        (functional groups, all locations)

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
  match-moieties,      {"error": ...} JSON on stdout, exit 1; a batch always exits 0 and
  classify             reports per-SMILES errors inside its own results list.

Usage:
  python3 orchestration/scripts/rdkit_cli.py canon --smiles '*CC*'
  python3 orchestration/scripts/rdkit_cli.py rigidity --smiles '*CC(*)c1ccccc1'
  python3 orchestration/scripts/rdkit_cli.py tg-estimate --smiles '*CC*' --output text
"""
import argparse
import json
import sys
from pathlib import Path

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
    # ASSUMES an assessment temperature of 300 K, which is final_T_K's default. This estimator
    # runs before a plan exists (isolated RDKit env -- see the module docstring's "do not import
    # rdkit_cli"), so it cannot know a run's actual final_T_K. It is a SUGGESTION for a human
    # curating a new class entry, consumed by nothing: stage_params reads only tg_estimated_K
    # from this payload and derives T_workflow itself via workflow_reference_temperature, which
    # does compare against the real final_T_K. If a curator pastes this value into a class entry
    # for a run assessed off 300 K, it will be wrong -- re-derive it there.
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
# docstring warns against; that estimation was a literature-search responsibility until
# 2026-09-02, when the Kuhn/DP grounding fields were retired -- it is now simply not estimated
# anywhere, and a stiff backbone is REPORTED as a bias rather than sized around.
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
# Moiety matching -- D-01's force-field screen
# ---------------------------------------------------------------------------
# Same shape as _MOTIFS/_compiled_motifs above, with two deliberate differences:
#   * the patterns come from guides/ff_moiety_rules.json, not a table in this file, because
#     each one carries a measured precision that has to stay next to the number it was
#     measured against;
#   * matching runs on the raw repeat unit (Chem.MolFromSmiles), NOT _prepare_repeat_unit --
#     that helper strips the "*" atoms, and the precisions were measured on the raw string.
_MOIETY_RULES_PATH = (Path(__file__).resolve().parent.parent.parent
                      / "guides" / "ff_moiety_rules.json")
_MOIETY_CACHE: dict = {}


def _compiled_moieties(rules_path=None) -> list:
    """[(rule, compiled_pattern)], compiled once per rules file on first use."""
    key = str(rules_path or _MOIETY_RULES_PATH)
    if key not in _MOIETY_CACHE:
        doc = json.loads(Path(key).read_text())
        out = []
        for rule in doc.get("moieties", []):
            pat = Chem.MolFromSmarts(rule["smarts"])
            if pat is None:
                raise ValueError(f"Bad SMARTS for {rule['id']!r}: {rule['smarts']!r}")
            out.append((rule, pat))
        _MOIETY_CACHE[key] = out
    return _MOIETY_CACHE[key]


def _dimer_for_screening(smiles: str):
    """Two repeat units joined tail-to-head, outer `*` markers kept; None if not buildable.

    A repeat unit may be cut anywhere along the backbone, and the groups these rules describe
    are bonds, not atoms. Nylon-6 written `*NCCCCCC(=O)*` and `*CCCCCC(=O)N*` is the same
    polymer, but only the second shows an amide to `[NX3][CX3]=[OX1]`: in the first, the
    N-C(=O) bond is exactly the one the two `*` markers stand for, so the monomer never
    contains it. The chain always does, so the screen has to see a chain -- matching the 2-mer
    makes the answer independent of where the author cut the unit.

    Deliberately NOT built on _prepare_repeat_unit: freezing H counts and capping the outer
    ends breaks kekulization on aromatic-backbone repeat units (PPS, PEEK, PSU, PPV all failed).
    Joining the two INNER wildcards' neighbours and deleting only those two wildcards keeps every
    atom's degree unchanged, so RDKit's implicit-H bookkeeping needs no help and the outer `*`
    pair -- which the SMARTS ignore -- marks the ends exactly as in the monomer.
    """
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    wc = [a.GetIdx() for a in mol.GetAtoms() if a.GetAtomicNum() == 0]
    if len(wc) != 2:
        return None
    n = mol.GetNumAtoms()
    combo = RWMol(Chem.CombineMols(mol, mol))
    inner_a, inner_b = wc[1], wc[0] + n          # copy 1's tail, copy 2's head
    try:
        nbr_a = combo.GetAtomWithIdx(inner_a).GetNeighbors()[0].GetIdx()
        nbr_b = combo.GetAtomWithIdx(inner_b).GetNeighbors()[0].GetIdx()
    except IndexError:
        return None                              # malformed: a `*` with no neighbour
    combo.AddBond(nbr_a, nbr_b, Chem.BondType.SINGLE)
    for idx in sorted((inner_a, inner_b), reverse=True):
        combo.RemoveAtom(idx)
    try:
        Chem.SanitizeMol(combo)
    except Exception:
        return None
    return combo.GetMol()


def match_moieties(smiles: str, rules_path=None) -> dict:
    """Which measured build-blocking groups this polymer contains.

    Matched against the 2-mer (see _capped_dimer) so the answer does not depend on where the
    repeat unit was cut; falls back to the monomer when the dimer will not build, which is the
    pre-2026-09-04 behaviour and still better than no screen.

    `unmatched_heavy_frac` mirrors estimate_tg's own bookkeeping and is the honest half of the
    answer: no match means UNSCREENED, not cleared -- these rules cover 77% of the measured
    failures, so the caller still has to probe.
    """
    mol = _dimer_for_screening(smiles)
    screened_on = "2-mer"
    if mol is None:
        mol = Chem.MolFromSmiles(smiles)
        screened_on = "repeat_unit"
    if mol is None:
        return {"smiles": smiles, "error": f"Could not parse SMILES: {smiles!r}"}
    assigned: set = set()
    hits = []
    for rule, pat in _compiled_moieties(rules_path):
        matches = mol.GetSubstructMatches(pat)
        if not matches:
            continue
        for m in matches:
            assigned.update(m)
        hits.append({"id": rule["id"], "label": rule.get("label"),
                     "smarts": rule["smarts"], "n_matches": len(matches),
                     "blocks": rule.get("blocks", {}),
                     "precision": (rule.get("evidence") or {}).get("precision")})
    heavy = sum(1 for a in mol.GetAtoms() if a.GetAtomicNum() != 1)
    return {"smiles": smiles, "screened_on": screened_on, "moieties": hits,
            "unmatched_heavy_frac": round(max(0.0, 1.0 - len(assigned) / max(heavy, 1)), 3)}


def _cmd_match_moieties(args) -> int:
    if bool(args.smiles) == bool(args.input):
        print(json.dumps({"error": "give exactly one of --smiles or --input"}))
        return 1
    if args.smiles:
        result = match_moieties(args.smiles, args.rules)
    else:
        # One subprocess for the whole list: a per-SMILES round trip through the conda seam
        # is what makes a 982-molecule sweep take minutes instead of seconds.
        smiles_list = json.loads(Path(args.input).read_text())
        result = {"results": [match_moieties(s, args.rules) for s in smiles_list]}
    print(json.dumps(result, indent=2))
    return 1 if "error" in result else 0


# ---------------------------------------------------------------------------
# classify
# ---------------------------------------------------------------------------
PROFILE_RULES = Path(__file__).resolve().parent.parent.parent / "guides" / "polymer_group_profile.json"


def _load_profile(rules_path=None) -> dict:
    return json.loads(Path(rules_path or PROFILE_RULES).read_text())


def _group_locations(smiles: str, profile: dict, flags: dict) -> dict:
    """Every group family in the profile, tagged backbone vs pendant.

    This is the part RadonPy structurally cannot report. polyinfo_classifier matches its
    tier-1 SMARTS on extract_mainchain(smi) -- the BACKBONE ONLY -- so a pendant ester
    (PMMA's -C(=O)OMe) never appears in its `flags` at all. That distinction is not
    cosmetic: "polyester" and "acrylic carrying an ester" want different protocols.

    So the two halves are read from two different places, and neither is re-derived:
      backbone  <- RadonPy's own `flags`, which are by construction mainchain-only.
      pendant   <- the same SMARTS re-matched on the 2-mer (_dimer_for_screening, so a
                   chain-end cut cannot hide a group) for families RadonPy did NOT flag.

    Tier-2 (styrene/acryl) and the element-count families are reported from `flags` alone.
    Their SMARTS are written against the `[14C]` mainchain isotope tagging that
    polyinfo_classifier applies to its own working copy; matching them raw against an
    untagged molecule yields noise, not information, so this does not try.
    """
    dimer = _dimer_for_screening(smiles)
    out = {}
    for cls, rule in profile["groups"].items():
        flagged = bool(flags.get(cls, False))
        patterns = rule.get("smarts")
        tier = rule.get("tier")
        if flagged:
            out[cls] = {"location": "backbone", "source": "polyinfo_flags",
                        "smarts_var": rule.get("smarts_var")}
            continue
        if tier != 1 or not patterns or dimer is None:
            continue  # see docstring: tier-2/element-count are not independently matchable
        n = 0
        for smarts in patterns:
            pat = Chem.MolFromSmarts(smarts)
            if pat is not None:
                n += len(dimer.GetSubstructMatches(pat))
        if n:
            out[cls] = {"location": "pendant", "source": "dimer_rematch",
                        "n_matches_2mer": n, "smarts_var": rule.get("smarts_var")}
    return out


def classify(smiles: str, rules_path=None, overrides_path=None, fg_rules_path=None) -> dict:
    """Full chemical-group profile of a repeat unit, plus its PoLyInfo class.

    The LABEL is RadonPy's -- poly.polyinfo_classifier is called directly, never
    reimplemented, because docs/ff_coverage_sweep/arm0.jsonl (this repo's classification
    ground truth) IS that function's output. Everything else here is additive:

      groups        every family present, tagged backbone vs pendant -- see
                    _group_locations for why RadonPy cannot report the pendant half.
      co_occurring  families RadonPy flagged that did not win the priority ladder.
      runner_up     the next class down that ladder; carried as evidence, never applied.
      chemistry     the REAL chemistry: every functional group in guides/functional_groups.json
                    that the repeat unit contains, wherever it sits, with per-group backbone/
                    pendant location plus composition and the descriptors that bear on
                    protocol choice. This is the half a backbone taxonomy cannot give -- see
                    chemistry_profile.

    `polymer_class` may differ from `polyinfo_class` when guides/class_overrides.json
    records a deliberate departure (see that file). Both are always reported, and
    `class_source` says which one is binding, so the substitution is never silent.
    """
    from radonpy.core import poly as _poly

    profile = _load_profile(rules_path)
    groups = profile["groups"]
    by_id = {v["class_id"]: k for k, v in groups.items()}

    try:
        class_id, flags = _poly.polyinfo_classifier(smiles, return_flag=True)
    except Exception as exc:
        return {"smiles": smiles, "error": f"polyinfo_classifier failed: {exc}"}

    polyinfo_class = by_id.get(class_id)
    if class_id == 0 or polyinfo_class is None:
        return {"smiles": smiles, "error": "UNRESOLVED_CLASS",
                "detail": (f"polyinfo_classifier returned class_id={class_id}; the repeat unit "
                           "matched no PoLyInfo family. A guessed class would silently set "
                           "charge_method, electrostatics, cutoff_A, dt_fs, T_equil_K and the "
                           "experimental bands, so this refuses instead."),
                "class_id": class_id}

    ranked = sorted((c for c, on in flags.items() if on and c in groups),
                    key=lambda c: groups[c]["priority_rank"])
    runner_up = next((c for c in ranked if c != polyinfo_class), None)

    result = {
        "smiles": smiles,
        "class_id": class_id,
        "polyinfo_class": polyinfo_class,
        "polymer_class": polyinfo_class,
        "class_source": "radonpy_polyinfo",
        "priority_rank": groups[polyinfo_class]["priority_rank"],
        "flags": {c: bool(flags.get(c, False)) for c in groups},
        "co_occurring": [c for c in ranked if c != polyinfo_class],
        "runner_up": runner_up,
        "groups": _group_locations(smiles, profile, flags),
        "chemistry": chemistry_profile(smiles, fg_rules_path),
    }

    override = _lookup_override(smiles, overrides_path)
    if override:
        result["polymer_class"] = override["polymer_class"]
        result["class_source"] = "override"
        result["override"] = {**override, "displaced": polyinfo_class}
    return result


def _lookup_override(smiles: str, overrides_path=None) -> dict | None:
    """A deliberate, documented departure from polyinfo's label for this exact molecule.

    Keyed on the isomeric canonical SMILES so it cannot be dodged by rewriting the input.
    Absent file or absent key means no override -- this is a small allowlist, not a
    second taxonomy.
    """
    path = Path(overrides_path or (PROFILE_RULES.parent / "class_overrides.json"))
    if not path.is_file():
        return None
    entries = json.loads(path.read_text()).get("overrides", {})
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    return entries.get(Chem.MolToSmiles(mol))


def _cmd_classify(args) -> int:
    if bool(args.smiles) == bool(args.input):
        print(json.dumps({"error": "give exactly one of --smiles or --input"}))
        return 1
    if args.smiles:
        result = classify(args.smiles, args.rules, args.overrides, args.fg_rules)
    else:
        # One subprocess for the whole list -- the 982-molecule sweep is minutes, not
        # hours, only because it does not re-cross the conda seam per SMILES.
        smiles_list = json.loads(Path(args.input).read_text())
        result = {"results": [classify(s, args.rules, args.overrides, args.fg_rules)
                              for s in smiles_list]}
    print(json.dumps(result, indent=2))
    return 1 if "error" in result else 0


# ---------------------------------------------------------------------------
# chemistry profile (functional groups, wherever they sit)
# ---------------------------------------------------------------------------
FG_RULES = Path(__file__).resolve().parent.parent.parent / "guides" / "functional_groups.json"

#: Strongest wins. The molecule's polarity class is the strongest category it contains.
POLARITY_ORDER = ("apolar", "weakly_polar", "polar_aprotic", "polar_protic", "ionic")

_FG_CACHE: dict = {}


def _compiled_fgs(rules_path=None) -> list:
    key = str(rules_path or FG_RULES)
    if key not in _FG_CACHE:
        doc = json.loads(Path(key).read_text())
        out = []
        for rule in doc.get("groups", []):
            pat = Chem.MolFromSmarts(rule["smarts"])
            if pat is None:
                raise ValueError(f"Bad SMARTS for {rule['id']!r}: {rule['smarts']!r}")
            out.append((rule, pat))
        _FG_CACHE[key] = out
    return _FG_CACHE[key]


def _backbone_path_of_dimer(mol) -> set:
    """Atom indices along the main chain of a 2-mer built by _dimer_for_screening.

    That helper keeps the OUTER two wildcards, so the chain runs from one to the other and
    the shortest path between their neighbours is the backbone -- through both repeat units,
    including the junction bond a single repeat unit cannot show.
    """
    wc = [a.GetIdx() for a in mol.GetAtoms() if a.GetAtomicNum() == 0]
    if len(wc) != 2:
        return set()
    ends = []
    for idx in wc:
        nbrs = mol.GetAtomWithIdx(idx).GetNeighbors()
        if len(nbrs) != 1:
            return set()
        ends.append(nbrs[0].GetIdx())
    return set(Chem.GetShortestPath(mol, ends[0], ends[1]))


def _core_atoms(mol, match) -> list:
    """The atoms that make a functional group the group it is.

    Its heteroatoms, plus any carbon double-bonded to one -- a carbonyl carbon is as much
    the identity of an ester or a ketone as its oxygens are. Everything else in a match is
    context: the SMARTS for a ketone names the two flanking carbons, the one for a hydroxyl
    names the carbon it hangs from, and those say nothing about where the group sits.
    """
    core = []
    for idx in match:
        atom = mol.GetAtomWithIdx(idx)
        if atom.GetAtomicNum() not in (1, 6):
            core.append(idx)
            continue
        for bond in atom.GetBonds():
            other = bond.GetOtherAtom(atom)
            if (bond.GetBondType() == Chem.BondType.DOUBLE
                    and other.GetAtomicNum() not in (1, 6)):
                core.append(idx)
                break
    return core


def _match_location(mol, match, backbone: set, polarity: str | None = None) -> str:
    """Is this functional group IN the main chain, or hanging off it?

    Decided on the group's core atoms (see _core_atoms), because that is the distinction
    that matters and the one polyinfo_classifier structurally cannot draw -- it matches on
    the extracted mainchain, so it never sees a pendant group at all. PLA's ester oxygen and
    carbonyl carbon lie on the backbone path (in-chain ester -> polyester); PMMA's lie off
    it (pendant ester on a hydrocarbon backbone -> acrylic). Same SMARTS, opposite answer.

    Two failure modes this avoids. Testing ALL match atoms would call PVA's hydroxyl
    "backbone", because the SMARTS names the backbone carbon the -OH hangs from. Testing
    heteroatoms alone would call PEEK's ketone "pendant", because its only heteroatom is the
    exocyclic =O while the carbonyl carbon it belongs to is squarely in the chain.

    Apolar groups -- a phenyl ring, an alkene, a quaternary centre -- are exempt from the
    core test entirely, not merely expected to have no core. Their identity is carbon, so any
    heteroatom the SMARTS happens to name is context: quaternary_carbon matches the alpha
    carbon AND its four neighbours, one of which in PMMA is an ester carbonyl carbon. Letting
    that carbonyl become the "core" would report PMMA's backbone alpha-carbon as pendant.
    They fall back to the whole match: PS's pendant phenyl touches no backbone atom, PEEK's
    in-chain arylene is threaded by the path.
    """
    probe = (list(match) if polarity == "apolar"
             else (_core_atoms(mol, match) or list(match)))
    return "backbone" if any(i in backbone for i in probe) else "pendant"


def chemistry_profile(smiles: str, rules_path=None) -> dict:
    """Every functional group in the repeat unit, how many, and where.

    Matched on the 2-mer for the same reason the build-blocker screen is (see
    _dimer_for_screening): a repeat unit can be cut anywhere along the chain, and a group
    that spans the cut is invisible in the monomer.

    Descriptors are computed on the wildcard-stripped MONOMER so counts are per repeat unit
    rather than doubled, and so H counts reflect true backbone connectivity.
    """
    dimer = _dimer_for_screening(smiles)
    screened_on = "2-mer"
    if dimer is None:
        dimer = Chem.MolFromSmiles(smiles)
        screened_on = "repeat_unit"
    if dimer is None:
        return {"error": f"Could not parse SMILES: {smiles!r}"}

    backbone = _backbone_path_of_dimer(dimer)
    groups = []
    for rule, pat in _compiled_fgs(rules_path):
        matches = dimer.GetSubstructMatches(pat)
        if not matches:
            continue
        locations = [_match_location(dimer, m, backbone, rule.get("polarity"))
                     for m in matches]
        groups.append({
            "id": rule["id"], "label": rule.get("label"), "polarity": rule.get("polarity"),
            # Per repeat unit: the 2-mer contains two copies of everything that does not
            # span the junction, so halve and keep at least one.
            "count": max(1, len(matches) // 2),
            "count_2mer": len(matches),
            "location": "backbone" if "backbone" in locations else "pendant",
            "locations": {"backbone": locations.count("backbone"),
                          "pendant": locations.count("pendant")},
            "hbond_donors": rule.get("hbond_donors", 0),
            "hbond_acceptors": rule.get("hbond_acceptors", 0),
            "note": rule.get("note"),
        })

    # Descriptors come off the 2-mer, not _prepare_repeat_unit's monomer. That helper
    # freezes H counts and caps the ends, which breaks kekulization on aromatic-backbone
    # repeat units -- PPS, PEEK, PSU and PPV all fail it, and so does every fused polyimide.
    # Silently empty descriptors there made `elements` empty, and an empty set is a subset of
    # {C,H}: polyimides were reporting as apolar hydrocarbons. Extensive quantities are
    # halved back to one repeat unit; the dimer joins two units without losing an atom, so
    # the division is exact rather than approximate.
    descriptors = _descriptors(dimer, per_unit=2 if screened_on == "2-mer" else 1)

    # The molecule's OWN transition temperature, carried alongside its chemistry so a caller
    # is not forced to read Tg off a class label. estimate_tg also derives a T_equil_K from it
    # (Tg + 200 K); chemistry_policy.check_melt_margin uses the Tg to ask whether the class's
    # prescribed melt temperature leaves enough headroom for THIS repeat unit.
    tg = estimate_tg(smiles)

    present = {g["polarity"] for g in groups}
    polarity = next((p for p in reversed(POLARITY_ORDER) if p in present), "apolar")

    elements = descriptors.get("elements", {})
    # Aromatic carbon is not electrostatically inert. An aryl ring is quadrupolar and the
    # all-atom fields assign real partial charges to it -- polymer_rules' own ff_note for
    # PSTR says PCFF is preferred over TraPPE-UA precisely because of aromatic ring charges.
    # So "pure hydrocarbon" alone is not a licence to drop long-range electrostatics; PS is
    # C/H only and correctly carries pppm.
    # Fail CLOSED when composition is unknown: no elements means no evidence of apolarity,
    # and lj_cut is the answer that can be a physics error.
    hydrocarbon_only = bool(elements) and set(elements) <= {"C", "H"}
    apolar_aliphatic = hydrocarbon_only and not descriptors.get("n_aromatic_rings")
    return {
        "screened_on": screened_on,
        "functional_groups": sorted(groups, key=lambda g: (g["location"], g["id"])),
        "backbone_groups": [g["id"] for g in groups if g["location"] == "backbone"],
        "pendant_groups": [g["id"] for g in groups if g["location"] == "pendant"],
        "tm_estimate": estimate_tm_boyer(smiles),
        "tg_estimate": ({k: tg.get(k) for k in
                         ("tg_estimated_K", "T_equil_K", "method", "confidence",
                          "unmatched_heavy_frac")}
                        if "error" not in tg else {"error": tg["error"]}),
        "polarity_class": polarity,
        "hydrocarbon_only": hydrocarbon_only,
        "apolar_aliphatic": apolar_aliphatic,
        # The only two classes carrying lj_cut in polymer_rules.json are PHYC and PDIE --
        # the aliphatic-hydrocarbon ones -- so this reconstructs that table's own rule from
        # the MOLECULE rather than from its class label. Advisory: chemistry_policy compares
        # the two and reports a divergence; it never overrides the class.
        "implied_electrostatics": (None if not elements
                                   else "lj_cut" if apolar_aliphatic else "pppm"),
        **descriptors,
    }


def _descriptors(mol, per_unit: int = 1) -> dict:
    """Composition and the physicochemical descriptors that bear on protocol choice.

    `per_unit` divides the EXTENSIVE quantities (counts, mass, polar surface area) so they
    describe one repeat unit when the molecule handed in is an n-mer. Fractions are
    intensive and pass through unchanged. Wildcard atoms are excluded from every count --
    they are chain-end markers, not chemistry.
    """
    if mol is None:
        return {}
    real = [a for a in mol.GetAtoms() if a.GetAtomicNum() != 0]
    if not real:
        return {}
    hetero = [a for a in real if a.GetAtomicNum() not in (1, 6)]
    aromatic = [a for a in real if a.GetIsAromatic()]

    elements: dict = {}
    try:
        for atom in Chem.AddHs(mol).GetAtoms():
            if atom.GetAtomicNum() == 0:
                continue
            elements[atom.GetSymbol()] = elements.get(atom.GetSymbol(), 0) + 1
    except Exception:  # noqa: BLE001 -- composition is advisory; never sink a profile for it
        for atom in real:
            elements[atom.GetSymbol()] = elements.get(atom.GetSymbol(), 0) + 1

    def per(value):
        return round(value / per_unit, 3) if isinstance(value, float) else value // per_unit

    out = {
        "elements": {k: per(v) for k, v in sorted(elements.items())},
        "n_heavy_atoms": per(len(real)),
        "heteroatom_fraction": round(len(hetero) / len(real), 3),
        "aromatic_atom_fraction": round(len(aromatic) / len(real), 3),
        "descriptor_basis": f"{per_unit}-mer, divided to one repeat unit" if per_unit > 1
                            else "repeat unit",
    }
    for name, fn, cast in (
        ("n_aromatic_rings", Chem.rdMolDescriptors.CalcNumAromaticRings, int),
        ("hbond_donors", Chem.rdMolDescriptors.CalcNumHBD, int),
        ("hbond_acceptors", Chem.rdMolDescriptors.CalcNumHBA, int),
        ("rotatable_bonds", Chem.rdMolDescriptors.CalcNumRotatableBonds, int),
        ("tpsa", Chem.rdMolDescriptors.CalcTPSA, float),
        ("mw_repeat_unit", Descriptors.MolWt, float),
    ):
        try:
            out[name] = per(cast(fn(mol)))
        except Exception:  # noqa: BLE001
            out[name] = None
    out["formal_charge"] = Chem.GetFormalCharge(mol) // per_unit
    return out


def _cmd_chemistry(args) -> int:
    result = chemistry_profile(args.smiles, args.rules)
    print(json.dumps(result, indent=2))
    return 1 if "error" in result else 0


def backbone_symmetry(smiles: str):
    """Boyer-Beaman backbone symmetry, from the SMILES alone.

    A chain is UNSYMMETRICAL if any backbone atom carries two different substituents -- the
    -CH2-CHR- of a vinyl polymer. It is SYMMETRICAL when every backbone atom's two pendant
    slots are filled identically: PE's CH2, PIB's C(CH3)2, PTFE's CF2.

    Identity is decided by RDKit's canonical ranking with breakTies=False, which gives
    constitutionally equivalent atoms the same rank. Comparing pendant SUBSTRUCTURES instead
    was tried and is fragile: a fixed-radius environment around each pendant reaches back
    through the backbone, so two identical groups can look different purely from where the
    traversal ran out.

    Returns (is_symmetric, [backbone atom indices that break it]), or (None, reason).
    """
    mol = _dimer_for_screening(smiles)
    if mol is None:
        return None, "repeat unit does not build a 2-mer"
    backbone = _backbone_path_of_dimer(mol)
    if not backbone:
        return None, "no backbone path"
    rank = list(Chem.CanonicalRankAtoms(mol, breakTies=False))
    asymmetric = []
    for idx in backbone:
        atom = mol.GetAtomWithIdx(idx)
        if atom.GetAtomicNum() == 0:
            continue
        pendant = [n.GetIdx() for n in atom.GetNeighbors()
                   if n.GetIdx() not in backbone and n.GetAtomicNum() != 0]
        slots = [rank[p] for p in pendant] + ["H"] * atom.GetTotalNumHs()
        if len(slots) == 2 and slots[0] != slots[1]:
            asymmetric.append(idx)
    return (not asymmetric), asymmetric


#: Boyer-Beaman ratios Tg/Tm. Symmetrical chains sit near 0.5, unsymmetrical near 0.667.
BOYER_TG_OVER_TM = {True: 0.5, False: 0.667}

#: Mean absolute error of the Boyer Tm below, measured 2026-09-07 against experimental Tm for
#: the 16 crystallizable curated members. See estimate_tm_boyer for why that number matters.
BOYER_TM_MAE_K = 130


def estimate_tm_boyer(smiles: str, tg_K=None) -> dict:
    """Melting point from the SMILES, via Boyer-Beaman on the estimated or supplied Tg.

    READ THE ACCURACY BEFORE USING THIS. Measured against experimental Tm for the 16
    crystallizable curated members it carries a mean absolute error of 130 K, spanning -280 K
    (PTFE, whose 600 K Tm it puts at 320) to +242 K (PEK, whose 638 K it puts at 880). Boyer
    is a correlation over crystallizable chains, not a predictor.

    It is also a CATEGORY ERROR on amorphous polymers, which have no Tm at all. Applied to
    PSU (Tg 493) it returns 986 K, well into thermal decomposition. `crystallizable` is
    reported but not decided here -- backbone symmetry is a necessary condition for
    crystallinity, not a sufficient one, and PSU, PPO and BPA-PC are all symmetric and
    amorphous.

    So this is EVIDENCE, for a critic or a human weighing a per-SMILES melt temperature
    against literature. It is deliberately not wired to T_equil_K: at +-130 K it cannot be
    trusted to lower a curated melt, and lowering one below Tm produces a run that never
    melts -- silently, since every downstream gate would still pass on a stuck structure.
    """
    symmetric, detail = backbone_symmetry(smiles)
    if symmetric is None:
        return {"error": f"backbone symmetry unresolved: {detail}"}

    if tg_K is None:
        tg = estimate_tg(smiles)
        if "error" in tg:
            return {"error": f"no Tg to work from: {tg['error']}"}
        tg_K = tg.get("tg_estimated_K")
        tg_source, tg_confidence = "group_contribution", tg.get("confidence")
    else:
        tg_source, tg_confidence = "supplied", "curated"
    if not isinstance(tg_K, (int, float)):
        return {"error": "no usable Tg"}

    ratio = BOYER_TG_OVER_TM[bool(symmetric)]
    return {
        "tm_estimated_K": round(tg_K / ratio),
        "tg_K": tg_K,
        "tg_source": tg_source,
        "tg_confidence": tg_confidence,
        "backbone_symmetric": bool(symmetric),
        "boyer_ratio_tg_over_tm": ratio,
        "n_asymmetric_backbone_atoms": len(detail),
        "method": "boyer_beaman",
        "mae_vs_experimental_K": BOYER_TM_MAE_K,
        "valid_only_if_crystallizable": True,
        "caution": ("+-130 K mean absolute error; meaningless for amorphous polymers, which "
                    "have no Tm. Evidence only -- not a basis for setting T_equil_K."),
    }


def _cmd_tm_estimate(args) -> int:
    result = estimate_tm_boyer(args.smiles, args.tg_K)
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

    c = sub.add_parser("match-moieties",
                       help="measured build-blocking chemical groups in a repeat unit")
    c.add_argument("--smiles", default=None)
    c.add_argument("--input", default=None,
                   help="JSON file holding a list of SMILES; one subprocess for the batch")
    c.add_argument("--rules", default=None,
                   help="Override guides/ff_moiety_rules.json (testing only)")
    c.set_defaults(func=_cmd_match_moieties)

    c = sub.add_parser("classify",
                       help="PoLyInfo class + full chemical-group profile of a repeat unit")
    c.add_argument("--smiles", default=None)
    c.add_argument("--input", default=None,
                   help="JSON file holding a list of SMILES; one subprocess for the batch")
    c.add_argument("--rules", default=None,
                   help="Override guides/polymer_group_profile.json (testing only)")
    c.add_argument("--overrides", default=None,
                   help="Override guides/class_overrides.json (testing only)")
    c.add_argument("--fg-rules", default=None,
                   help="Override guides/functional_groups.json (testing only)")
    c.set_defaults(func=_cmd_classify)

    c = sub.add_parser("tm-estimate",
                       help="Boyer-Beaman melting point from backbone symmetry (EVIDENCE ONLY)")
    c.add_argument("--smiles", required=True)
    c.add_argument("--tg_K", type=float, default=None,
                   help="use a curated Tg instead of the group-contribution estimate")
    c.set_defaults(func=_cmd_tm_estimate)

    c = sub.add_parser("chemistry",
                       help="functional-group inventory of a repeat unit, backbone and pendant")
    c.add_argument("--smiles", required=True)
    c.add_argument("--rules", default=None,
                   help="Override guides/functional_groups.json (testing only)")
    c.set_defaults(func=_cmd_chemistry)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
