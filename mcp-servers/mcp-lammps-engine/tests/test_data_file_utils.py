"""Unit tests for the LAMMPS .data file parser and validator.

The MCP tools ``parse_data_file`` and ``validate_data_file`` in server.py are
thin wrappers around ``ScriptGenerator.parse_data_file`` /
``ScriptGenerator.validate_data_file`` (script_generator.py, stdlib-only). The
validator is the pre-submission gate that refuses a malformed cell, so its
checks are exercised here directly against a minimal in-memory data file.
"""
import pytest

from script_generator import ScriptGenerator

# A minimal but complete atom_style=full data file: 4 atoms, 2 atom types,
# charge-neutral, complete Pair Coeffs, 4 Angstrom box. The small box keeps the
# computed density realistic (~0.68 g/cm3); tests that care about the
# box-vs-cutoff check pass an appropriately small lj_cutoff.
CLEAN_DATA = """\
# test polymer data file
4 atoms
0 bonds
2 atom types

0.0 4.0 xlo xhi
0.0 4.0 ylo yhi
0.0 4.0 zlo zhi

Masses

1 1.008 # hc
2 12.011 # c3

Pair Coeffs

1 0.0157 2.6495
2 0.1094 3.3996

Atoms

1 1 2 -0.12 1.0 1.0 1.0
2 1 1 0.06 2.0 1.0 1.0
3 1 1 0.06 1.0 2.0 1.0
4 1 2 0.00 2.0 2.0 1.0
"""


def _gen():
    # data_file path is unused when content is passed explicitly.
    return ScriptGenerator(data_file="unused.data")


# ── parse_data_file ────────────────────────────────────────────────────────

def test_parse_extracts_counts_and_box():
    info = _gen().parse_data_file(content=CLEAN_DATA)
    assert info["n_atoms"] == 4
    assert info["n_bonds"] == 0
    assert info["n_atom_types"] == 2
    assert info["box_x"] == 4.0
    assert info["box_y"] == 4.0
    assert info["box_z"] == 4.0


def test_parse_extracts_atom_type_names_and_h_types():
    info = _gen().parse_data_file(content=CLEAN_DATA)
    assert info["atom_type_names"] == ["hc", "c3"]
    # 'hc' (type 1) starts with 'h' -> flagged as a SHAKE hydrogen type
    assert info["h_type_ids"] == [1]
    assert info["has_charges"] is True


# ── validate_data_file ─────────────────────────────────────────────────────

def test_clean_file_is_valid():
    res = _gen().validate_data_file(content=CLEAN_DATA, lj_cutoff=1.0)
    assert res["valid"] is True
    assert res["errors"] == []
    assert res["warnings"] == []
    assert abs(res["stats"]["net_charge_e"]) <= 0.01


def test_box_smaller_than_two_cutoffs_is_blocked():
    # default lj_cutoff=12 -> needs a >=24 A box; the 4 A box must be rejected
    res = _gen().validate_data_file(content=CLEAN_DATA)
    assert res["valid"] is False
    assert any("box" in e.lower() for e in res["errors"])


def test_nonneutral_charge_is_blocked():
    bad = CLEAN_DATA.replace("4 1 2 0.00", "4 1 2 0.50")  # net charge +0.50 e
    res = _gen().validate_data_file(content=bad, lj_cutoff=1.0)
    assert res["valid"] is False
    assert any("charge" in e.lower() for e in res["errors"])


def test_incomplete_pair_coeffs_is_blocked():
    # drop the second Pair Coeff line: 1 entry but header declares 2 atom types
    bad = CLEAN_DATA.replace("1 0.0157 2.6495\n2 0.1094 3.3996", "1 0.0157 2.6495")
    res = _gen().validate_data_file(content=bad, lj_cutoff=1.0)
    assert res["valid"] is False
    assert any("Pair Coeffs" in e for e in res["errors"])


def test_out_of_range_type_id_is_blocked():
    # only 2 atom types exist; requesting type 5 as a SHAKE H is invalid
    res = _gen().validate_data_file(content=CLEAN_DATA, lj_cutoff=1.0, h_type_ids=[5])
    assert res["valid"] is False
    assert any("range" in e.lower() for e in res["errors"])
