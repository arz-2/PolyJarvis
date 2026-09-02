"""Force-field domain coverage: what it measures, and what it must never claim.

The check answers a provenance question -- has this field been exercised on these
atom types in a completed run -- and the archive backtest shows it does NOT predict
accuracy. These tests lock both halves, because the second is the one likely to be
forgotten and turned back into a gate.
"""
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))

from forcefield import (  # noqa: E402
    abundance_from_data,
    assess_domain,
    build_vocabulary,
    cell_fingerprint,
    types_from_params,
)

ARCHIVE = REPO_ROOT / "manuscript" / "data"


def _has_archive():
    return (ARCHIVE / "PMMA4" / "lammps" / "cell" / "emc_build.params").exists()


# ─── parsing ───────────────────────────────────────────────────────────────────

def _write_params(tmp_path, lines):
    p = tmp_path / "emc_build.params"
    p.write_text("\n".join(lines) + "\n")
    return p


def test_types_come_from_the_mass_block_not_pair_coeff(tmp_path):
    """`mass` has one row per type; pair_coeff diagonals can omit a type that never
    appears in a written diagonal comment. PCFF's `o` was missed that way."""
    p = _write_params(tmp_path, [
        "mass\t\t1    12.01115  # c",
        "mass\t\t2     1.00797  # hc",
        "mass\t\t3    15.99940  # o_1",
        "pair_coeff\t 1  1    0.05400    4.01000  # c,c",
    ])
    assert types_from_params(str(p)) == {1: "c", 2: "hc", 3: "o_1"}


def test_unreadable_params_is_empty_not_an_exception():
    assert types_from_params("/nonexistent/emc_build.params") == {}


def test_abundance_counts_atoms_by_type_name(tmp_path):
    d = tmp_path / "cell.data"
    d.write_text(
        "LAMMPS\n\n4 atoms\n2 atom types\n\n"
        "0.0 10.0 xlo xhi\n0.0 10.0 ylo yhi\n0.0 10.0 zlo zhi\n\n"
        "Masses\n\n1 12.0\n2 1.0\n\n"
        "Atoms\n\n"
        "1 1 1 0.0 1.0 1.0 1.0\n"
        "2 1 2 0.0 2.0 1.0 1.0\n"
        "3 1 2 0.0 3.0 1.0 1.0\n"
        "4 1 2 0.0 4.0 1.0 1.0\n")
    assert abundance_from_data(str(d), {1: "c", 2: "hc"}) == {"c": 1, "hc": 3}


def test_missing_data_file_falls_back_to_unweighted(tmp_path):
    """A cell with params but no cell.data must still yield a type list."""
    _write_params(tmp_path, ["mass\t\t1    12.01115  # c"])
    fp = cell_fingerprint(str(tmp_path))
    assert fp["types"] == ["c"]
    assert fp["atom_fraction"] == {}


# ─── verdicts ──────────────────────────────────────────────────────────────────

VOCAB = {"pcff": {"c": ["PMMA"], "hc": ["PMMA"], "o_1": ["PMMA"]}}


def test_all_types_known_is_in_domain():
    fp = {"types": ["c", "hc"], "atom_fraction": {"c": 0.4, "hc": 0.6}, "n_atoms": 10}
    r = assess_domain(fp, VOCAB, "pcff")
    assert r["verdict"] == "FF_IN_DOMAIN"
    assert r["type_coverage"] == 1.0
    assert r["extrapolated_types"] == []


def test_new_type_is_extrapolating_and_reports_its_atom_share():
    fp = {"types": ["c", "cl"], "atom_fraction": {"c": 0.8, "cl": 0.2}, "n_atoms": 10}
    r = assess_domain(fp, VOCAB, "pcff")
    assert r["verdict"] == "FF_EXTRAPOLATING"
    assert r["extrapolated_types"] == ["cl"]
    assert r["extrapolated_atom_fraction"] == 0.2


def test_unused_field_has_no_domain_at_all():
    """COMPASS has never been run here, so it has no demonstrated domain -- that must
    be said explicitly rather than silently passing."""
    r = assess_domain({"types": ["c"], "atom_fraction": {}, "n_atoms": 1}, VOCAB, "compass")
    assert r["verdict"] == "FF_UNAVAILABLE"
    assert "pcff" in r["validated_fields"]


def test_verdict_never_claims_to_predict_accuracy():
    """The guard against this being re-sold as an accuracy gate. Backtested on the
    archive the correlation is NEGATIVE (-0.26 on K, -0.64 on density): PLA
    extrapolates on 0.2% of atoms with the worst K error (+33%), cis-PBD on 49.8%
    with among the best densities (-0.2%)."""
    fp = {"types": ["c", "cl"], "atom_fraction": {"c": 0.8, "cl": 0.2}, "n_atoms": 10}
    r = assess_domain(fp, VOCAB, "pcff")
    assert r["is_accuracy_prediction"] is False
    assert "NOT a prediction" in r["reason"]
    assert "Do not discard this field" in r["reason"]


# ─── archive backtest ──────────────────────────────────────────────────────────

@pytest.mark.skipif(not _has_archive(), reason="archived build cells not present")
def test_every_archived_run_is_in_domain_against_its_own_field():
    """Sanity floor: a run that helped define the vocabulary must be inside it."""
    import glob
    import os
    from forcefield import _field_of_run

    vocab = build_vocabulary(str(ARCHIVE))
    checked = 0
    for params in glob.glob(str(ARCHIVE / "*" / "lammps" / "cell" / "emc_build.params")):
        cell_dir = os.path.dirname(params)
        field = _field_of_run(cell_dir.split(os.sep + "lammps" + os.sep)[0])
        fp = cell_fingerprint(cell_dir)
        if not field or not fp:
            continue
        assert assess_domain(fp, vocab, field)["verdict"] == "FF_IN_DOMAIN", params
        checked += 1
    assert checked >= 30


@pytest.mark.skipif(not _has_archive(), reason="archived build cells not present")
def test_pcff_vocabulary_is_the_measured_fifteen():
    """Locks the vocabulary the plan's numbers were derived from. A change here means
    the archive changed, and every downstream coverage figure needs re-deriving."""
    vocab = build_vocabulary(str(ARCHIVE))
    assert sorted(vocab["pcff"]) == [
        "c", "c1", "c_0", "c_1", "cl", "cp", "hc", "ho", "ho2",
        "o", "o_1", "o_2", "oc", "oh", "sf",
    ]
    assert sorted(vocab["trappe-ua"]) == ["c3h", "c4h2", "c4h3"]
