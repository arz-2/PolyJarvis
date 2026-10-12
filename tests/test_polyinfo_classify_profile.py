"""classify — the group profile, which is the half RadonPy cannot report.

poly.polyinfo_classifier matches its tier-1 SMARTS on extract_mainchain(smi), i.e. the
BACKBONE ONLY. So a pendant ester is absent from its `flags` entirely, and "polyester" is
indistinguishable from "acrylic carrying an ester" by the label alone. That distinction
drives protocol choice, so `classify` re-matches the same SMARTS on the 2-mer for families
RadonPy did not flag and tags them pendant.

The PMMA/PLA pair below is the whole point of the enrichment: same ester group, opposite
location, different class, different protocol.

Marked requires_binaries: shells into the mol-builder conda env for RadonPy.
"""
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))

from classify_cli import classify_polymer  # noqa: E402

pytestmark = pytest.mark.requires_binaries


def test_pendant_ester_is_located_off_the_backbone_and_does_not_win_the_class():
    """PMMA. RadonPy's flags never mention PEST here; only the re-match finds it."""
    result = classify_polymer("*CC(*)(C)C(=O)OC")
    assert result["polymer_class"] == "PACR"
    assert result["flags"]["PEST"] is False, "polyinfo cannot see a pendant ester -- by design"
    assert result["groups"]["PEST"]["location"] == "pendant"
    assert result["groups"]["PEST"]["source"] == "dimer_rematch"
    assert result["groups"]["PACR"]["location"] == "backbone"


def test_backbone_ester_is_located_on_the_backbone_and_does_win_the_class():
    """PLA -- the contrast case for PMMA above."""
    result = classify_polymer("*OC(=O)C(*)C")
    assert result["polymer_class"] == "PEST"
    assert result["flags"]["PEST"] is True
    assert result["groups"]["PEST"]["location"] == "backbone"
    assert result["groups"]["PEST"]["source"] == "polyinfo_flags"


@pytest.mark.parametrize("name,smiles,expected,also_present", [
    ("PEEK", "*Oc1ccc(C(=O)c2ccc(Oc3ccc(*)cc3)cc2)cc1", "PKTN", {"POXI", "PPNL"}),
    ("PSU", "*Oc1ccc(C(C)(C)c2ccc(Oc3ccc(S(=O)(=O)c4ccc(*)cc4)cc3)cc2)cc1", "PSFO", {"POXI", "PPNL"}),
    ("BPA-PC", "*Oc1ccc(C(C)(C)c2ccc(OC(*)=O)cc2)cc1", "PCBN", {"PPNL"}),
    ("Nylon-6", "*CCCCCC(=O)N*", "PAMD", set()),
    ("PDMS", "*O[Si](*)(C)C", "PSIL", set()),
])
def test_co_occurring_backbone_groups_are_all_reported_not_just_the_winner(
        name, smiles, expected, also_present):
    """An aryl-ether backbone really does contain an ether; the ladder picks one class but
    the profile must still say what else is in there, because that is the evidence a
    downstream critic needs to challenge the choice."""
    result = classify_polymer(smiles)
    assert result["polymer_class"] == expected, name
    backbone = {c for c, g in result["groups"].items() if g["location"] == "backbone"}
    assert expected in backbone, name
    assert also_present <= backbone, f"{name}: expected {also_present} in {backbone}"


def test_runner_up_names_the_next_class_down_the_ladder():
    """Carried as evidence only -- never applied. PEEK's ether is the runner-up to its ketone."""
    result = classify_polymer("*Oc1ccc(C(=O)c2ccc(Oc3ccc(*)cc3)cc2)cc1")
    assert result["runner_up"] == "POXI"
    assert result["priority_rank"] < 21


def test_an_unclassifiable_molecule_refuses_instead_of_returning_a_class():
    from classify_cli import ClassificationError
    with pytest.raises(ClassificationError):
        classify_polymer("C")  # no chain-end markers at all


def test_override_reports_both_labels_so_the_substitution_is_never_silent():
    """PVC. polymer_rules.json says PVNL (-> PCFF); polyinfo ranks PHAL first (-> OPLS-AA).
    Whichever binds, a reader must be able to see the other."""
    result = classify_polymer("*CC(*)Cl")
    assert result["polymer_class"] == "PVNL"
    assert result["polyinfo_class"] == "PHAL"
    assert result["class_source"] == "override"
    assert result["override"]["displaced"] == "PHAL"
    assert "reason" in result["override"]
