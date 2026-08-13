"""Parameter provenance: where a built cell's numbers actually came from.

The check exists because EMC exits 0 whether a coefficient came from the published
field, a wildcard fallback, a local hand-edit, or a zero substituted for a row that
does not exist. These tests lock the two things most likely to rot: the archive
calibration (NO_SOURCE_ROW is a parser self-test and must stay at zero) and the
scope boundary (existence, not value equality).
"""
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))

from ff_provenance import (  # noqa: E402
    FrcField,
    PrmField,
    _match,
    _tok,
    assess,
    open_field,
    parse_params,
)

ARCHIVE = REPO_ROOT / "manuscript" / "data"
EMC = Path.home() / "emc"


def _cells():
    return sorted(p.parent for p in ARCHIVE.glob("*/lammps/cell/emc_build.params"))


def _field_of(cell_dir):
    plan = cell_dir.parents[1] / "raw" / "run_plan.json"
    if not plan.exists():
        return None
    return json.loads(plan.read_text()).get("decided_params", {}).get("preferred_ff")


needs_archive = pytest.mark.skipif(not _cells(), reason="no archived cells")
needs_emc = pytest.mark.skipif(not EMC.exists(), reason="no installed EMC field tree")


# --- wildcard conventions -------------------------------------------------------

def test_leading_star_is_a_pure_wildcard():
    # .frc _auto rows use `*`, and the numbered `*1`/`*2` variants are distinct rows
    # that all match anything -- treating `*1` as a glob would match only types ending
    # in "1"
    assert _tok("c4h2", "*")
    assert _tok("c4h2", "*1")
    assert _tok("anything", "*5")


def test_trailing_glob_matches_by_prefix():
    # .prm _AUTO rows use `c4*`
    assert _tok("c4h2", "c4*")
    assert not _tok("c3h", "c4*")


def test_exact_token_requires_equality():
    assert _tok("cp", "cp")
    assert not _tok("cp", "c")


def test_match_requires_equal_arity():
    assert not _match(["a", "b"], ["a", "b", "c"])


# --- readers --------------------------------------------------------------------

@needs_emc
def test_frc_reader_applies_auto_equivalence_positionally():
    field, _ = open_field("pcff")
    assert isinstance(field, FrcField)
    # a bonded _auto lookup keys on the underscored forms; the centre and end atoms of
    # an angle map through different columns
    ends = field.equivalents(["cp", "cp", "cp"], "angle", "auto")
    specific = field.equivalents(["cp", "cp", "cp"], "angle", "specific")
    assert ends != specific, "auto lookups must not reuse the specific equivalence table"
    assert ends[0] != ends[1], "angle end and apex atoms map through different columns"


@needs_emc
def test_prm_and_frc_are_selected_by_installed_extension():
    assert isinstance(open_field("opls/2024/opls-aa")[0], PrmField)
    assert isinstance(open_field("pcff")[0], FrcField)


@needs_emc
def test_short_field_key_resolves_through_the_capability_registry():
    # a run plan records `trappe-ua`; the installed tree is trappe/2014/trappe-ua
    _, path = open_field("trappe-ua")
    assert path.endswith("trappe-ua.prm")


# --- params parsing -------------------------------------------------------------

@needs_archive
def test_class2_cross_terms_are_not_mistaken_for_primary_terms():
    cell = next(c for c in _cells() if c.parents[1].name.startswith("PMMA"))
    rows = parse_params(cell / "emc_build.params")
    # BondBond and AngleAngle reuse angle_coeff/improper_coeff with a sub-tag, and are
    # distinguishable only by their section header
    kinds = {r["section"] for r in rows if r["kind"] is None}
    assert "BondBond" in kinds and "AngleAngle" in kinds
    assert all(r["section"] in ("Pair", "Bond", "Angle", "Dihedral", "Improper")
               for r in rows if r["kind"] is not None)


# --- archive calibration --------------------------------------------------------

@needs_archive
@needs_emc
def test_no_source_row_is_zero_across_the_archive():
    """NO_SOURCE_ROW means the lookup missed a row that exists -- a bug here, not a
    finding about the field. Every archived cell was built successfully, so any
    occurrence is a regression in the reader."""
    offenders = {}
    for cell in _cells():
        field = _field_of(cell)
        if not field:
            continue
        r = assess(str(cell), field)
        n = r.get("counts", {}).get("NO_SOURCE_ROW", 0)
        if n:
            offenders[cell.parents[1].name] = n
    assert not offenders, f"lookup missed rows in {offenders}"


@needs_archive
@needs_emc
def test_no_local_patch_under_pcff():
    """The vendored patches are OPLS-only; PCFF must come back clean."""
    for cell in _cells():
        if _field_of(cell) != "pcff":
            continue
        r = assess(str(cell), "pcff")
        assert not r["counts"].get("LOCAL_PATCH"), cell


@needs_archive
@needs_emc
def test_zero_impropers_are_advisory_not_blocking():
    """A zero out-of-plane term is the norm for sp3 centres and appears in every
    archived cell. Escalating it would make the whole archive unrunnable."""
    cell = next(c for c in _cells() if c.parents[1].name.startswith("PMMA"))
    r = assess(str(cell), "pcff")
    zeros = [f for f in r["findings"] if "ZERO_SUBSTITUTED" in f["flags"]]
    assert zeros, "PMMA cells carry zeroed improper rows"
    assert all(f["kind"] == "improper" and f["severity"] == "advisory" for f in zeros)


# --- scope ----------------------------------------------------------------------

@needs_archive
@needs_emc
def test_check_is_existence_not_value_equality():
    """A wrong-but-present parameter is out of scope, and the note must keep saying so
    -- reproducing EMC's values would trade a reliable check for an unreliable one."""
    cell = next(c for c in _cells() if c.parents[1].name.startswith("PMMA"))
    r = assess(str(cell), "pcff")
    assert "Existence check only" in r["note"]


def test_no_source_row_never_blocks():
    """A gap in this parser must not demote a field or reject a plan -- that would let
    a lookup bug silently change which force field a run uses. cis-PBD under PCFF was
    the live case: one unmatched out-of-plane permutation demoted the field entirely."""
    from ff_provenance import _severity
    assert _severity(["NO_SOURCE_ROW"], "improper") == "self_check"
    assert _severity(["NO_SOURCE_ROW"], "torsion") == "self_check"
    assert _severity(["LOCAL_PATCH"], "torsion") == "blocking"


def test_out_of_plane_matching_permutes_substituents():
    """PCFF stores one canonical substituent order; EMC emits every permutation of it.
    cis-PBD writes both `c=2,c,c=2,hc` and `c=2,c,hc,c=2` against a single `c c= c= h`
    row, so matching must permute the three substituents, not just rotate the centre."""
    pytest.importorskip("pathlib")
    if not (EMC / "field" / "pcff" / "pcff.frc").exists():
        pytest.skip("no installed PCFF field")
    field, _ = open_field("pcff")
    for tuple_ in (["c=2", "c", "c=2", "hc"], ["c=2", "c", "hc", "c=2"]):
        assert field.lookup("improper", tuple_) is not None, tuple_


@needs_archive
@needs_emc
def test_cross_terms_are_reported_unchecked_not_dropped():
    cell = next(c for c in _cells() if c.parents[1].name.startswith("PMMA"))
    r = assess(str(cell), "pcff")
    assert r["unchecked_cross_terms"], "Class II cross terms must be reported, not hidden"
