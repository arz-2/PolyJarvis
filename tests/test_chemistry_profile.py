"""chemistry_profile — the real chemistry of a repeat unit, and WHERE each group sits.

The distinction this exists to draw: `poly.polyinfo_classifier` matches its class-defining
SMARTS on `extract_mainchain`, i.e. the backbone only, so a pendant group is invisible to it
entirely -- PMMA reports PEST false. 404 of PI1070's 1077 real repeat units carry a polar
group that never informed their class label, and those class labels carry `electrostatics`,
`charge_method` and the rest of the protocol.

PMMA vs PLA is the whole test in one line: the same ester SMARTS, in-chain for one and
pendant for the other, giving different classes and different protocols.

Needs RDKit but not RadonPy, so it runs in the default suite.
"""
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))

pytest.importorskip("rdkit")

import rdkit_cli as rc  # noqa: E402


def profile(smiles):
    return rc.chemistry_profile(smiles)


def located(smiles):
    p = profile(smiles)
    return set(p["backbone_groups"]), set(p["pendant_groups"])


# --- the headline distinction ----------------------------------------------
def test_pmma_ester_is_pendant_and_pla_ester_is_backbone():
    pmma_bb, pmma_pd = located("*CC(*)(C)C(=O)OC")
    pla_bb, pla_pd = located("*OC(=O)C(*)C")
    assert "ester" in pmma_pd and "ester" not in pmma_bb
    assert "ester" in pla_bb and "ester" not in pla_pd


@pytest.mark.parametrize("name,smiles,backbone,pendant", [
    ("PS",      "*CC(*)c1ccccc1",      set(),                          {"benzene_ring"}),
    ("PVA",     "*CC(*)O",             set(),                          {"hydroxyl_alcohol"}),
    ("PVC",     "*CC(*)Cl",            set(),                          {"chloroalkyl"}),
    ("PAN",     "*CC(*)C#N",           set(),                          {"nitrile"}),
    ("PVME",    "*CC(*)OC",            set(),                          {"ether_aliphatic"}),
    ("PEO",     "*CCO*",               {"ether_aliphatic"},            set()),
    ("Nylon6",  "*CCCCCC(=O)N*",       {"amide_NH"},                   set()),
    ("PBD",     "*CC=CC*",             {"alkene"},                     set()),
    ("PDMS",    "*O[Si](*)(C)C",       {"siloxane", "silicon_alkyl"},  set()),
])
def test_group_locations(name, smiles, backbone, pendant):
    bb, pd = located(smiles)
    assert bb == backbone, f"{name} backbone: {bb}"
    assert pd == pendant, f"{name} pendant: {pd}"


def test_an_in_chain_ketone_is_backbone_despite_its_exocyclic_oxygen():
    """PEEK. The ketone's only heteroatom is the =O, which hangs off the path; the carbonyl
    carbon it belongs to is squarely in the chain. Judging on heteroatoms alone called this
    pendant -- hence _core_atoms including carbons double-bonded to a heteroatom."""
    bb, _ = located("*Oc1ccc(C(=O)c2ccc(Oc3ccc(*)cc3)cc2)cc1")
    assert {"ketone", "ether_aryl", "benzene_ring"} <= bb


def test_an_in_chain_sulfone_is_backbone():
    """PSU. Its SMARTS names only S and its two oxygens -- no flanking carbons -- so a rule
    keyed on 'two match atoms on the path' would call it pendant."""
    bb, _ = located("*Oc1ccc(C(C)(C)c2ccc(Oc3ccc(S(=O)(=O)c4ccc(*)cc4)cc3)cc2)cc1")
    assert "sulfone" in bb


def test_a_backbone_carbon_group_is_not_dragged_off_chain_by_a_pendant_carbonyl():
    """PMMA's alpha carbon IS backbone. quaternary_carbon's SMARTS names it plus all four
    neighbours, one of which is the pendant ester's carbonyl carbon; letting that carbonyl
    count as the group's 'core' reported a backbone atom as pendant. Apolar groups are
    exempt from the core test for exactly this reason."""
    bb, _ = located("*CC(*)(C)C(=O)OC")
    assert "quaternary_carbon" in bb


# --- composition ------------------------------------------------------------
@pytest.mark.parametrize("name,smiles,elements,mw", [
    ("PE",   "*CC*",                                   {"C": 2, "H": 4},           28.05),
    ("PMMA", "*CC(*)(C)C(=O)OC",                       {"C": 5, "H": 8, "O": 2},  100.12),
    ("PEEK", "*Oc1ccc(C(=O)c2ccc(Oc3ccc(*)cc3)cc2)cc1", {"C": 19, "H": 12, "O": 3}, 288.30),
])
def test_composition_is_per_repeat_unit(name, smiles, elements, mw):
    """Descriptors are measured on the 2-mer and halved. They must come back as ONE repeat
    unit -- these are the true monomer formulae and masses."""
    p = profile(smiles)
    assert p["elements"] == elements, name
    assert p["mw_repeat_unit"] == pytest.approx(mw, abs=0.05), name


def test_aromatic_backbone_polymers_still_get_composition():
    """_prepare_repeat_unit breaks kekulization on aromatic-backbone units (PPS, PEEK, PSU,
    PPV, and every fused polyimide), which silently returned NO descriptors at all. Empty
    elements then made `set() <= {C,H}` true and reported polyimides as apolar hydrocarbons
    routed to lj_cut. Descriptors come off the 2-mer now."""
    for smiles in ("*Oc1ccc(C(=O)c2ccc(Oc3ccc(*)cc3)cc2)cc1",
                   "*Sc1ccc(*)cc1",
                   "*n1c(=O)c2cc3c(cc2c1=O)c(=O)n(c3=O)CCCCCCCCC*"):
        p = profile(smiles)
        assert p["elements"], smiles
        assert p["heteroatom_fraction"] > 0, smiles
        assert p["implied_electrostatics"] == "pppm", smiles


# --- polarity and the electrostatics rule -----------------------------------
@pytest.mark.parametrize("smiles,polarity", [
    ("*CC*",            "apolar"),
    ("*CC(*)Cl",        "weakly_polar"),
    ("*CC(*)(C)C(=O)OC", "polar_aprotic"),
    ("*CC(*)O",         "polar_protic"),
])
def test_polarity_class_is_the_strongest_category_present(smiles, polarity):
    assert profile(smiles)["polarity_class"] == polarity


@pytest.mark.parametrize("smiles,implied", [
    ("*CC*",             "lj_cut"),   # PE   -- aliphatic hydrocarbon
    ("*CC(C)*",          "lj_cut"),   # PP
    ("*CC=CC*",          "lj_cut"),   # PBD
    ("*CC(*)c1ccccc1",   "pppm"),     # PS   -- hydrocarbon, but aromatic
    ("*CC(*)Cl",         "pppm"),     # PVC
    ("*CCO*",            "pppm"),     # PEO
])
def test_implied_electrostatics(smiles, implied):
    assert profile(smiles)["implied_electrostatics"] == implied


def test_an_aromatic_hydrocarbon_does_not_get_lj_cut():
    """PS is C/H only, yet PSTR correctly carries pppm: an aryl ring is quadrupolar and the
    all-atom fields put real partial charges on it. 'Pure hydrocarbon' alone is not a licence
    to truncate Coulomb."""
    p = profile("*CC(*)c1ccccc1")
    assert p["hydrocarbon_only"] is True
    assert p["apolar_aliphatic"] is False
    assert p["implied_electrostatics"] == "pppm"


def test_unknown_composition_never_implies_lj_cut():
    """Fail closed. lj_cut is the answer that can be a physics error, so absent evidence it
    must not be the default -- an empty element set is a subset of {C,H}, which is how
    polyimides came to be reported as apolar."""
    assert rc.chemistry_profile("not a molecule").get("error")
    for elements in ({}, None):
        assert (None if not elements else "lj_cut") is None


def test_a_group_spanning_the_repeat_unit_cut_is_still_found():
    """The reason matching happens on the 2-mer. Nylon-6 written `*NCCCCCC(=O)*` puts the
    amide bond exactly where the two chain-end markers are, so the monomer never contains
    it; the chain always does."""
    bb, _ = located("*NCCCCCC(=O)*")
    assert "amide_NH" in bb


def test_counts_are_reported_per_repeat_unit_not_per_dimer():
    """PMMA's pendant ester appears twice in the 2-mer and once per repeat unit."""
    p = profile("*CC(*)(C)C(=O)OC")
    ester = next(g for g in p["functional_groups"] if g["id"] == "ester")
    assert ester["count_2mer"] == 2
    assert ester["count"] == 1


def test_a_group_at_the_chain_end_is_counted_at_least_once():
    """PEO's 2-mer is `*CCOCCO*`: the trailing oxygen's second neighbour is a chain-end
    marker, not a carbon, so only ONE of the two ethers matches. Halving that would round to
    zero and erase the defining group of a polyether, so the count floors at one. It means
    counts are a lower bound for groups adjacent to the cut -- fine for advisory use, and
    stated here so nobody reads them as exact stoichiometry."""
    p = profile("*CCO*")
    ether = next(g for g in p["functional_groups"] if g["id"] == "ether_aliphatic")
    assert ether["count_2mer"] == 1
    assert ether["count"] == 1
    assert "ether_aliphatic" in p["backbone_groups"]


# --- the claim the whole advisory layer rests on ----------------------------
def _member_cases():
    import json
    rules = json.loads((REPO_ROOT / "guides" / "polymer_rules.json").read_text())["classes"]
    for cls, entry in rules.items():
        for name, smis in (entry.get("member_smiles") or {}).items():
            if isinstance(smis, list):          # 'note' entries are prose
                for s in smis:
                    yield cls, name, s, entry.get("electrostatics")


MEMBERS = list(_member_cases())


def test_there_are_curated_members_to_check_against():
    assert len(MEMBERS) >= 40


@pytest.mark.parametrize("cls,name,smiles,declared",
                         MEMBERS, ids=[m[1] for m in MEMBERS])
def test_chemistry_implied_electrostatics_matches_every_curated_class(cls, name, smiles, declared):
    """43/43 on this repo's own curated chemistry.

    This is what licenses the whole advisory layer. `electrostatics` is a per-CLASS constant
    -- a backbone taxonomy standing in for polarity -- and this asserts that a rule derived
    from the MOLECULE reproduces it exactly on every polymer the repo has curated. Because
    the proxy is exact here rather than merely usually-right, a disagreement on a novel
    polymer is signal rather than noise, and CHEM_ELECTROSTATICS_UNDERSPECIFIED means
    something.

    A failure here is not a test to relax: either the chemistry rule drifted, or a class
    constant changed and the two now genuinely disagree.
    """
    implied = profile(smiles)["implied_electrostatics"]
    assert implied == declared, (
        f"{name} ({cls}): class declares {declared}, chemistry implies {implied}")


# --- Boyer Tm: SMILES-derived, and deliberately advisory --------------------
@pytest.mark.parametrize("name,smiles,symmetric", [
    ("PE",   "*CC*",              True),
    ("PIB",  "*CC(C)(C)*",        True),
    ("PTFE", "*C(F)(F)C(*)(F)F",  True),
    ("POM",  "*COC*",             True),
    ("PEO",  "*CCO*",             True),
    ("PDMS", "*O[Si](*)(C)C",     True),
    ("PP",   "*CC(C)*",           False),
    ("PS",   "*CC(*)c1ccccc1",    False),
    ("PVC",  "*CC(*)Cl",          False),
    ("PVA",  "*CC(*)O",           False),
    ("PMMA", "*CC(*)(C)C(=O)OC",  False),
    ("PLA",  "*OC(=O)C(*)C",      False),
])
def test_backbone_symmetry_from_smiles(name, smiles, symmetric):
    """Boyer's branch depends on whether backbone atoms carry two identical substituents.
    PE's CH2 and PIB's C(CH3)2 are symmetric; PP's CH(CH3) is not."""
    assert rc.backbone_symmetry(smiles)[0] is symmetric, name


def test_symmetry_uses_canonical_ranks_not_substructure_comparison():
    """PIB's two methyls are constitutionally equivalent and must compare equal. Comparing
    fixed-radius environments around each pendant instead reaches back through the backbone,
    so identical groups can differ purely by where the traversal stopped."""
    assert rc.backbone_symmetry("*CC(C)(C)*")[0] is True
    assert rc.backbone_symmetry("*C(F)(F)C(*)(F)F")[0] is True


def test_boyer_applies_the_right_ratio_to_each_branch():
    assert rc.BOYER_TG_OVER_TM[True] == 0.5      # symmetric  -> Tm ~ 2.0 Tg
    assert rc.BOYER_TG_OVER_TM[False] == 0.667   # unsymmetric -> Tm ~ 1.5 Tg
    pe = rc.estimate_tm_boyer("*CC*", tg_K=195)
    assert pe["backbone_symmetric"] is True
    assert pe["tm_estimated_K"] == 390


def test_the_estimate_carries_its_own_accuracy_and_scope():
    """It is 130 K mean absolute error and meaningless for amorphous polymers. A caller that
    cannot see that from the payload will misuse it."""
    out = rc.estimate_tm_boyer("*CC*", tg_K=195)
    assert out["mae_vs_experimental_K"] == 130
    assert out["valid_only_if_crystallizable"] is True
    assert "amorphous" in out["caution"]


def test_boyer_is_not_wired_to_the_melt_temperature():
    """Measured 2026-09-07: -280 K on PTFE (600 K Tm estimated at 320) and +242 K on PEK.
    Driving T_equil from it would melt PTFE 220 K below its melting point -- a run that never
    melts, and every downstream gate still passes on the stuck structure. It would also put
    amorphous PSU at 986 K. So it stays evidence for a critic, and T_equil_K remains reachable
    only through the validated `overrides` path.
    """
    import stage_params
    src = Path(stage_params.__file__).read_text()
    assert "estimate_tm_boyer" not in src
    assert "boyer" not in src.lower() or "1.5 * tg" in src.lower()

    ptfe = rc.estimate_tm_boyer("*C(F)(F)C(*)(F)F", tg_K=160)
    assert ptfe["tm_estimated_K"] == 320          # real PTFE Tm is ~600 K
    psu = rc.estimate_tm_boyer(
        "*Oc1ccc(C(C)(C)c2ccc(Oc3ccc(S(=O)(=O)c4ccc(*)cc4)cc3)cc2)cc1", tg_K=463)
    assert psu["tm_estimated_K"] == 926           # PSU is amorphous; it has no Tm


def test_an_unresolvable_backbone_reports_an_error_not_a_number():
    assert "error" in rc.estimate_tm_boyer("C")   # no chain-end markers
