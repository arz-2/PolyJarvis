"""Force-field autodetection from a .data file: the united-atom hole.

`_detect_ff_from_data_file` classifies pre-equil EMC cells by improper count and atom
type naming. Both signals are all-atom assumptions, so a united-atom cell whose type
names don't spell `cNhN` fell through to whichever branch its improper count picked —
and *both* branches are wrong for a UA cell:

  - TraPPE-EH PMMA/PS carry 1 improper type -> PCFF branch -> `lj/class2/coul/long`
    + `mix sixthpower` against a params file holding harmonic/LJ coefficients.
  - TraPPE-EH PE/cis-PBD carry 0 -> OPLS fallback -> PPPM + 1-4 scaling on a cell
    with no charges at all.

Neither fails loudly. United-atom is now decided first, by mass.
"""
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "mcp-servers" / "mcp-lammps-engine"))

from script_generator import (  # noqa: E402
    _detect_ff_from_data_file,
    _has_united_atom_masses,
)


def _cell(masses, n_improper=0, inline_pair=None):
    """Minimal EMC-shaped .data file: header counts, then a Masses section."""
    head = ["LAMMPS data", "", "  100  atoms", "  99  bonds"]
    if n_improper:
        head.append(f"  {n_improper}  improper types")
    head += ["", "Masses", ""]
    body = [f"   {i + 1}   {m:.5f}  # {n}" for i, (m, n) in enumerate(masses)]
    tail = ["", "Atoms", "", "   1   1   1  0.0  0.0 0.0 0.0"]
    text = "\n".join(head + body + tail)
    if inline_pair:
        text += f"\n\nPair Coeffs # {inline_pair}\n\n   1  0.1  3.5\n"
    return text


# Real signatures, transcribed from EMC v9.4.4 builds.
UA_PE       = [(14.02680, "c2"), (15.03470, "c32")]
UA_PMMA_EH  = [(12.01100, "c"), (14.02680, "c2"), (15.03470, "c32"),
               (12.01100, "ct"), (15.99940, "o"), (15.99940, "os")]
UA_TRAPPE   = [(14.02680, "c4h2"), (15.03470, "c4h3")]
AA_OPLS_PS  = [(12.01100, "c3a"), (12.01100, "c4"), (1.00790, "h1"), (1.00790, "h1a")]
AA_PCFF     = [(12.01100, "c"), (1.00790, "hc"), (15.99940, "o_1")]
AA_PTFE     = [(12.01100, "c4"), (18.99840, "f1")]


# ─── the two mis-routed branches ───────────────────────────────────────────────

def test_ua_cell_with_impropers_is_not_read_as_pcff(tmp_path):
    """TraPPE-EH PMMA has 1 improper type. Taking the PCFF branch would run a
    class2 pair style against harmonic coefficients."""
    p = tmp_path / "c.data"
    p.write_text(_cell(UA_PMMA_EH, n_improper=1))
    assert _detect_ff_from_data_file(str(p)) == {
        "use_pcff": False, "use_trappe": True, "use_opls": False}


def test_ua_cell_without_impropers_is_not_read_as_opls(tmp_path):
    """TraPPE-EH PE has 0 impropers and type names `c2`/`c32`, which the old
    `cNhN` regex missed — so it reached the OPLS fallback and would have run
    PPPM + 1-4 scaling on a chargeless united-atom cell."""
    p = tmp_path / "c.data"
    p.write_text(_cell(UA_PE))
    assert _detect_ff_from_data_file(str(p))["use_trappe"] is True


# ─── the branches that must keep working ───────────────────────────────────────

def test_archived_trappe_ua_naming_still_detects(tmp_path):
    p = tmp_path / "c.data"
    p.write_text(_cell(UA_TRAPPE))
    assert _detect_ff_from_data_file(str(p))["use_trappe"] is True


def test_all_atom_opls_cell_still_reaches_the_opls_branch(tmp_path):
    """PHAL/PSIL depend on this fallback. EMC's OPLS-AA defines impropers only for
    c3= alkene centers, so 0 impropers on an aromatic is normal, not a defect."""
    p = tmp_path / "c.data"
    p.write_text(_cell(AA_OPLS_PS))
    assert _detect_ff_from_data_file(str(p))["use_opls"] is True


def test_pcff_cell_with_impropers_still_detects(tmp_path):
    p = tmp_path / "c.data"
    p.write_text(_cell(AA_PCFF, n_improper=4))
    assert _detect_ff_from_data_file(str(p))["use_pcff"] is True


def test_fluoropolymer_is_all_atom_despite_having_no_hydrogen(tmp_path):
    """The reason the check is mass-based and not hydrogen-absence-based: PTFE is
    all-atom OPLS (PHAL) and contains no H. Keying off missing hydrogen would
    misroute the entire fluoropolymer class to TraPPE."""
    p = tmp_path / "c.data"
    p.write_text(_cell(AA_PTFE))
    assert _detect_ff_from_data_file(str(p))["use_opls"] is True


# ─── the mass discriminator itself ─────────────────────────────────────────────

@pytest.mark.parametrize("mass,name", [
    (13.0189, "CH"), (14.0268, "CH2"), (15.0347, "CH3"), (16.0426, "CH4")])
def test_each_lumped_mass_is_recognised(mass, name):
    assert _has_united_atom_masses(_cell([(mass, "x")])) is True


@pytest.mark.parametrize("mass,name", [
    (1.00790, "H"), (12.01100, "C"), (14.00700, "N"), (15.99940, "O"),
    (18.99840, "F"), (28.08600, "Si"), (32.06000, "S"), (35.45000, "Cl")])
def test_no_element_mass_is_mistaken_for_a_lumped_one(mass, name):
    """N 14.007 vs CH2 14.0268 is the tightest pair — 0.020 apart against a 0.005
    tolerance. If that tolerance is ever widened, every nitrogen-bearing all-atom
    cell (PAMD, PIMD, PURT) starts routing to TraPPE."""
    assert _has_united_atom_masses(_cell([(mass, name)])) is False


def test_inline_coeff_files_are_unaffected(tmp_path):
    """The equilibrated-file path keys off the `Pair Coeffs #` style comment and
    must not be perturbed by the UA mass check."""
    p = tmp_path / "c.data"
    p.write_text(_cell(AA_PCFF, n_improper=4, inline_pair="lj/class2/coul/long/kk"))
    assert _detect_ff_from_data_file(str(p))["use_pcff"] is True


def test_missing_masses_section_does_not_crash():
    assert _has_united_atom_masses("LAMMPS data\n\n 10 atoms\n") is False
