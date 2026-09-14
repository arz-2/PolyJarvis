"""A truncated data file must be refused on every force field, not just charged ones.

Dropping atom rows while the header keeps its count is round-1's F6 fault and the shape a
half-written EMC or restart write leaves behind. Before 2026-09-13 `validate_data_file` had
no header-vs-rows check and no topology-reference check, so the fault was caught only
INCIDENTALLY -- by the charge sum, because the deleted atoms happened to carry charge.

Measured by injecting the identical fault into three chemistries:
    PLLA  (PEST/PCFF, charged)     -> net-charge error   (right verdict, wrong reason)
    PTFE  (PHAL/OPLS-AA, charged)  -> net-charge error   (right verdict, wrong reason)
    PE    (PHYC/TraPPE-UA, uncharged) -> NO ERROR AT ALL (truncated cell validated clean)

The uncharged case is the one that matters: TraPPE-UA carries no partial charges, so nothing
was left to catch it. The bond/atom ratio warning does not cover it either -- three atoms out
of thousands does not move the ratio past its 0.5/3.0 bounds.
"""
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ENGINE))

from script_generator import ScriptGenerator  # noqa: E402


def _cell(n_atoms, atom_rows, bonds=(), charge=0.0):
    """A minimal but structurally valid LAMMPS data file."""
    rows = "\n".join(
        "%d 1 1 %.4f %.3f %.3f %.3f" % (i, charge, i * 1.0, 0.0, 0.0)
        for i in atom_rows
    )
    bond_sec = ""
    if bonds:
        bond_sec = "\n\nBonds\n\n" + "\n".join(
            "%d 1 %d %d" % (n + 1, a, b) for n, (a, b) in enumerate(bonds)
        )
    return (
        "LAMMPS data file\n\n"
        "%d atoms\n%d bonds\n1 atom types\n1 bond types\n\n"
        "0.0 100.0 xlo xhi\n0.0 100.0 ylo yhi\n0.0 100.0 zlo zhi\n\n"
        "Masses\n\n1 12.011\n\n"
        "Atoms\n\n%s%s\n"
    ) % (n_atoms, len(bonds), rows, bond_sec)


def _errors(text):
    return ScriptGenerator(data_file="").validate_data_file(content=text)["errors"]


def test_an_intact_uncharged_cell_is_accepted():
    """The control. Without this, every assertion below could be measuring a false positive."""
    errs = _errors(_cell(4, [1, 2, 3, 4], bonds=[(1, 2), (2, 3), (3, 4)]))
    assert not [e for e in errs if "rows but the header" in e or "Topology references" in e]


def test_truncation_is_caught_with_no_charges_to_betray_it():
    """The PE case: uncharged, so the charge sum stays 0.0 and cannot flag anything."""
    text = _cell(4, [1, 2, 3], bonds=[(1, 2), (2, 3)])   # header says 4, only 3 rows
    errs = _errors(text)
    assert any("3 rows but the header declares 4" in e for e in errs), errs
    assert not any("Net charge" in e for e in errs), "charge must not be what catches this"


def test_dangling_topology_reference_is_caught():
    """Bonds naming an atom id that no longer exists."""
    text = _cell(3, [1, 2, 3], bonds=[(1, 2), (2, 99)])
    errs = _errors(text)
    assert any("Topology references atom id(s) absent" in e for e in errs), errs


def test_a_valid_cell_reports_matching_row_count_in_stats():
    res = ScriptGenerator(data_file="").validate_data_file(content=_cell(3, [1, 2, 3]))
    assert res["stats"]["n_atom_rows"] == 3
    assert res["stats"]["dangling_topology_refs"] == 0
