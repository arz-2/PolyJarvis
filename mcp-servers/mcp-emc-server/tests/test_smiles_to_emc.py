"""
Unit tests for smiles_to_emc.py

Tests cover .esh generation only (no EMC subprocess calls).
Integration tests that actually run EMC are in test_smiles_to_emc_integration.py.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from smiles_to_emc import make_esh

# ---------------------------------------------------------------------------
# Representative SMILES for the five PCFF target classes
# ---------------------------------------------------------------------------

CASES = {
    "PCBN_BPA_PC": {
        "smiles": "*OC(=O)Oc1ccc(C(C)(C)c2ccc(*)cc2)cc1",
        "class": "PCBN",
        "polymer": "BPA-PC",
        "density": 0.6,
        "dp": 20,
    },
    "PAMD_Nylon6": {
        "smiles": "*C(=O)NCCCCC*",
        "class": "PAMD",
        "polymer": "Nylon-6",
        "density": 0.57,
        "dp": 25,
    },
    "PKTN_PEEK": {
        "smiles": "*Oc1ccc(Oc2ccc(C(=O)c3ccc(*)cc3)cc2)cc1",
        "class": "PKTN",
        "polymer": "PEEK",
        "density": 0.65,
        "dp": 15,
    },
    "PSFO_PSU": {
        "smiles": "*Oc1ccc(C(C)(C)c2ccc(Oc3ccc(S(=O)(=O)c4ccc(*)cc4)cc3)cc2)cc1",
        "class": "PSFO",
        "polymer": "PSU (Udel)",
        "density": 0.65,
        "dp": 15,
    },
    "PIMD_Kapton": {
        "smiles": "*c1ccc(n2c(=O)c3cc4c(cc3c2=O)c(=O)n(c5ccc(Oc6ccc(*)cc6)cc5)c4=O)cc1",
        "class": "PIMD",
        "polymer": "PMDA-ODA (Kapton)",
        "density": 0.70,
        "dp": 15,
    },
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def sections(esh: str) -> dict:
    """Parse ITEM ... ITEM END blocks into a dict keyed by section name."""
    result = {}
    current = None
    lines = []
    for line in esh.splitlines():
        stripped = line.strip()
        if stripped.startswith("ITEM") and not stripped.startswith("ITEM END"):
            current = stripped.split(None, 1)[1]
            lines = []
        elif stripped == "ITEM END" and current is not None:
            result[current] = "\n".join(lines)
            current = None
        elif current is not None:
            lines.append(line)
    return result


# ---------------------------------------------------------------------------
# Structural tests (no EMC, no subprocess)
# ---------------------------------------------------------------------------

class TestMakeEshStructure:
    def test_required_sections_present(self):
        esh = make_esh("*CC*")
        s = sections(esh)
        assert "OPTIONS" in s
        assert "GROUPS" in s
        assert "CLUSTERS" in s
        assert "POLYMERS" in s

    def test_smiles_in_groups(self):
        smiles = "*CC(F)(F)*"
        esh = make_esh(smiles)
        s = sections(esh)
        assert smiles in s["GROUPS"]

    def test_cap_group_present(self):
        esh = make_esh("*CC*")
        s = sections(esh)
        assert "*[H]" in s["GROUPS"]
        assert "cap" in s["GROUPS"]

    def test_connection_spec_repeat(self):
        esh = make_esh("*CC*")
        s = sections(esh)
        # repeat group connects its left end (1) to adjacent repeat's right end (2)
        assert "1,repeat:2" in s["GROUPS"]

    def test_connection_spec_cap_both_ends(self):
        esh = make_esh("*CC*")
        s = sections(esh)
        # cap can terminate either end of the repeat unit
        assert "1,repeat:1" in s["GROUPS"]
        assert "1,repeat:2" in s["GROUPS"]

    def test_dp_in_polymers(self):
        esh = make_esh("*CC*", dp=30)
        s = sections(esh)
        assert "repeat,30" in s["POLYMERS"]

    def test_field_in_options(self):
        esh = make_esh("*CC*", field="pcff")
        s = sections(esh)
        assert "pcff" in s["OPTIONS"]

    def test_density_in_options(self):
        esh = make_esh("*CC*", density=1.2)
        s = sections(esh)
        assert "1.200000" in s["OPTIONS"]

    def test_ntotal_in_options(self):
        esh = make_esh("*CC*", ntotal=5000)
        s = sections(esh)
        assert "5000" in s["OPTIONS"]

    def test_output_name_as_esh_filename(self):
        # output name is derived from the .esh filename passed to emc_setup.pl,
        # not embedded in the OPTIONS section
        esh = make_esh("*CC*")
        s = sections(esh)
        # confirm OPTIONS does not contain an 'output' key (it goes via CLI flag)
        assert "output" not in s["OPTIONS"].lower().split()

    def test_polymer_cluster_alternate(self):
        esh = make_esh("*CC*")
        s = sections(esh)
        assert "alternate" in s["CLUSTERS"]
        assert "poly" in s["CLUSTERS"]

    def test_cap_terminators_count_2(self):
        esh = make_esh("*CC*", dp=20)
        s = sections(esh)
        # POLYMERS line: "100    repeat,20,cap,2"
        assert "cap,2" in s["POLYMERS"]


class TestMakeEshChainCount:
    """nchains>0 selects EMC 'number' mode (exact chain count); otherwise the
    ntotal-driven default sizing is used."""

    def test_default_no_number_mode(self):
        # nchains defaults to 0 → no 'number' option, cluster fraction stays 1
        esh = make_esh("*CC*")
        s = sections(esh)
        assert "number" not in s["OPTIONS"].lower().split()
        assert "poly    alternate    1" in s["CLUSTERS"]

    def test_nchains_zero_no_number_mode(self):
        esh = make_esh("*CC*", nchains=0)
        s = sections(esh)
        assert "number" not in s["OPTIONS"].lower().split()

    def test_nchains_enables_number_mode(self):
        esh = make_esh("*CC*", nchains=20)
        s = sections(esh)
        opts = s["OPTIONS"].split()
        # 'number true' must be present in ITEM OPTIONS
        assert "number" in opts
        idx = opts.index("number")
        assert opts[idx + 1] == "true"

    def test_nchains_sets_cluster_fraction(self):
        esh = make_esh("*CC*", nchains=20)
        s = sections(esh)
        # cluster fraction field carries the literal chain count
        assert "poly    alternate    20" in s["CLUSTERS"]


class TestMakeEshValidation:
    def test_wrong_star_count_zero(self):
        with pytest.raises(ValueError, match="exactly 2"):
            make_esh("CCC")

    def test_wrong_star_count_one(self):
        with pytest.raises(ValueError, match="exactly 2"):
            make_esh("*CCC")

    def test_wrong_star_count_three(self):
        with pytest.raises(ValueError, match="exactly 2"):
            make_esh("*CC(*)*")


# ---------------------------------------------------------------------------
# Per-class tests: verify each SMILES round-trips into the .esh correctly
# ---------------------------------------------------------------------------

class TestPerClass:
    @pytest.mark.parametrize("name,case", CASES.items())
    def test_smiles_preserved(self, name, case):
        esh = make_esh(case["smiles"], density=case["density"], dp=case["dp"])
        s = sections(esh)
        assert case["smiles"] in s["GROUPS"], (
            f"{case['polymer']}: SMILES not found in GROUPS section"
        )

    @pytest.mark.parametrize("name,case", CASES.items())
    def test_star_count(self, name, case):
        assert case["smiles"].count("*") == 2, (
            f"{case['polymer']}: test SMILES must have exactly 2 * atoms"
        )

    @pytest.mark.parametrize("name,case", CASES.items())
    def test_dp_in_polymers(self, name, case):
        esh = make_esh(case["smiles"], dp=case["dp"])
        s = sections(esh)
        assert f"repeat,{case['dp']}" in s["POLYMERS"], (
            f"{case['polymer']}: dp={case['dp']} not found in POLYMERS"
        )

    @pytest.mark.parametrize("name,case", CASES.items())
    def test_density_in_options(self, name, case):
        esh = make_esh(case["smiles"], density=case["density"])
        s = sections(esh)
        assert f"{case['density']:.6f}" in s["OPTIONS"], (
            f"{case['polymer']}: density={case['density']} not in OPTIONS"
        )
