"""Tests for ff_routing — the single source of truth for FF/builder routing.

These run without the RadonPy/RDKit environment (server.py's heavy deps): we import
the dependency-light ff_routing module directly, not server.py.
"""
import sys
from pathlib import Path

import pytest

SERVER_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER_DIR))

import ff_routing  # noqa: E402

RULES = ff_routing.load_polymer_rules()
CLASSES = RULES["classes"]


@pytest.mark.parametrize("cid", sorted(CLASSES))
def test_routing_matches_polymer_rules(cid):
    """get_preferred_ff must mirror the authoritative JSON for every class."""
    got = ff_routing.get_preferred_ff(cid)
    e = CLASSES[cid]
    assert got["preferred_ff"] == e["preferred_ff"]
    assert got["preferred_builder"] == e["preferred_builder"]
    assert got["ff_confidence"] == e["confidence"]
    assert got["ff_justification_doi"] == e.get("ff_justification_doi")


@pytest.mark.parametrize(
    "cid,expected_ff",
    [("PEST", "pcff"), ("PSUL", "pcff"), ("PACR", "pcff")],
)
def test_previously_divergent_classes_now_authoritative(cid, expected_ff):
    """The old hardcoded helper advised opls-aa/2024 for these; now they follow the JSON."""
    got = ff_routing.get_preferred_ff(cid)
    assert got["preferred_ff"] == expected_ff
    assert got["preferred_ff"] != "opls-aa/2024"


def test_pstr_routes_pcff():
    """PSTR (polystyrenics) uses PCFF via EMC: Class II explicitly parameterizes aromatic
    C-H charges and pi-dihedral cross-terms governing PS Tg (~373 K). OPLS-AA over-predicts
    aPS Tg by ~+79 K (Afzal 2021) so PCFF is preferred for thermomechanical accuracy.
    confidence=medium until a direct PCFF PS Tg paper is found."""
    got = ff_routing.get_preferred_ff("PSTR")
    assert got["preferred_ff"] == "pcff"
    assert got["preferred_builder"] == "emc"
    assert got["ff_confidence"] == "medium"
    assert CLASSES["PSTR"]["forcefield"] == "PCFF"
    assert CLASSES["PSTR"]["charge_method"] == "bond-increment"
    assert CLASSES["PSTR"]["electrostatics"] == "pppm"


def test_unknown_class_falls_back_without_raising():
    got = ff_routing.get_preferred_ff("UNKNOWN")
    assert got["preferred_builder"] is None
    assert got["preferred_ff"] is None
    assert got["ff_confidence"] == "low"
