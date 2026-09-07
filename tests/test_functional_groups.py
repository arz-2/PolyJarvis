"""guides/functional_groups.json — every rule compiles, matches, and does not over-match.

This library is the repo's answer to "what chemistry is actually in this repeat unit",
independent of the backbone taxonomy. A SMARTS that silently fails to compile, or matches
everything, degrades quietly: the profile just reports less chemistry than is there, and the
advisories built on it go quiet with it. So every rule carries its own positive and negative
example and both are asserted here.

The substrate matters and is the same one the matcher uses. Matching on the raw repeat-unit
SMILES fails for 8 of these rules, because a `*` chain-end marker sits where the SMARTS
expects a carbon -- an ether oxygen in `*CCO*` has a wildcard for one neighbour. The 2-mer
puts a real atom there, which is also why a group spanning the repeat-unit cut is visible at
all (see _dimer_for_screening).

Needs RDKit but not RadonPy, so it runs in the default suite.
"""
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))

pytest.importorskip("rdkit", reason="RDKit not importable in this interpreter")

from rdkit import Chem  # noqa: E402

import rdkit_cli as rc  # noqa: E402

RULES = json.loads((REPO_ROOT / "guides" / "functional_groups.json").read_text())["groups"]
IDS = [r["id"] for r in RULES]


def _substrate(smiles: str):
    """Exactly what chemistry_profile matches against."""
    mol = rc._dimer_for_screening(smiles)
    return mol if mol is not None else Chem.MolFromSmiles(smiles)


def test_the_library_is_not_empty_and_has_unique_ids():
    assert len(RULES) >= 30
    assert len(IDS) == len(set(IDS)), "duplicate rule ids"


@pytest.mark.parametrize("rule", RULES, ids=IDS)
def test_smarts_compiles(rule):
    assert Chem.MolFromSmarts(rule["smarts"]) is not None, rule["smarts"]


@pytest.mark.parametrize("rule", RULES, ids=IDS)
def test_rule_matches_its_own_example(rule):
    mol = _substrate(rule["example_smiles"])
    assert mol is not None, f"unparseable example {rule['example_smiles']!r}"
    assert mol.HasSubstructMatch(Chem.MolFromSmarts(rule["smarts"])), (
        f"{rule['id']} does not match its documented example "
        f"{rule['example_name']} ({rule['example_smiles']})")


@pytest.mark.parametrize("rule", RULES, ids=IDS)
def test_rule_does_not_match_its_counterexample(rule):
    """The negative half. Several of these are near-misses chosen on purpose -- a
    carboxylic acid must not match its own methyl ester, a secondary amine must not match a
    tertiary one, an amide N-H must not match an N,N-disubstituted amide."""
    mol = _substrate(rule["counterexample_smiles"])
    assert mol is not None, f"unparseable counterexample {rule['counterexample_smiles']!r}"
    assert not mol.HasSubstructMatch(Chem.MolFromSmarts(rule["smarts"])), (
        f"{rule['id']} wrongly matches {rule['counterexample_smiles']}")


@pytest.mark.parametrize("rule", RULES, ids=IDS)
def test_every_rule_declares_a_known_polarity(rule):
    assert rule["polarity"] in rc.POLARITY_ORDER, rule["polarity"]


def test_polarity_order_is_weakest_to_strongest():
    """chemistry_profile takes the LAST match walking the order backwards, so the ordering
    is what decides a molecule's polarity class."""
    assert rc.POLARITY_ORDER[0] == "apolar"
    assert rc.POLARITY_ORDER[-1] == "ionic"
    assert rc.POLARITY_ORDER.index("polar_aprotic") < rc.POLARITY_ORDER.index("polar_protic")


def test_hbond_counts_are_non_negative_integers():
    for rule in RULES:
        assert isinstance(rule["hbond_donors"], int) and rule["hbond_donors"] >= 0
        assert isinstance(rule["hbond_acceptors"], int) and rule["hbond_acceptors"] >= 0


def test_protic_groups_declare_at_least_one_donor():
    """polar_protic means "has an H to donate"; a protic rule with zero donors is a typo
    that would silently mute the H-bond-network advisory."""
    for rule in RULES:
        if rule["polarity"] == "polar_protic":
            assert rule["hbond_donors"] >= 1, rule["id"]


def test_apolar_groups_declare_no_hydrogen_bonding():
    for rule in RULES:
        if rule["polarity"] == "apolar":
            assert rule["hbond_donors"] == 0 and rule["hbond_acceptors"] == 0, rule["id"]


def test_this_library_is_not_the_class_taxonomy():
    """guides/polymer_group_profile.json mirrors RadonPy's 21 class-DEFINING patterns in
    order to reproduce a label. This file describes molecules. Collapsing the two would put
    a second taxonomy in the codebase, which is exactly what the mirror file must not
    become -- so they are asserted to be different things."""
    profile = json.loads((REPO_ROOT / "guides" / "polymer_group_profile.json").read_text())
    assert set(IDS).isdisjoint(profile["groups"]), (
        "functional-group ids collide with polymer class codes")
