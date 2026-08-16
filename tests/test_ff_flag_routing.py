"""Force-field flag routing for the Class II comparison fields.

`stage_params._lammps_flags` and `hw_common.resolve_ff_family` both classify a field by
substring. That works for the routed defaults by accident of naming -- "pcff_ore" contains
"pcff" -- but **compass** shares no token with any family. It silently returned
all-False flags (so the deck fell back to GAFF2 styles: lj/charmm/coul/long with
`mix arithmetic`, against a class2 params file) and family "gaff" (so the hardware policy
handed out the wrong engine and rank count).

Neither failure raises. The run would have produced numbers.
"""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "orchestration" / "scripts"))

from stage_params import _lammps_flags  # noqa: E402
from hw_common import resolve_ff_family  # noqa: E402


# ─── style-block selection ─────────────────────────────────────────────────────

@pytest.mark.parametrize("ff", ["pcff", "pcff_ore", "compass"])
def test_every_class_ii_field_selects_the_class2_block(ff):
    """compass and pcff_ore share pcff's class2 functional form (9-6 LJ, quartic bonds,
    cross terms), so all three must emit the same style block."""
    f = _lammps_flags(None, {"preferred_ff": ff})
    assert f["use_pcff"] is True, ff
    assert f["use_opls"] is False and f["use_trappe"] is False


def test_compass_is_not_left_flagless():
    """The regression: all-False makes the generator fall through to the GAFF2 default,
    which pairs an amber special_bonds and arithmetic mixing with class2 coefficients."""
    assert any(_lammps_flags(None, {"preferred_ff": "compass"}).values())


@pytest.mark.parametrize("ff,key", [
    ("opls/2024/opls-aa", "use_opls"),
    ("opls/2012/opls-aa", "use_opls"),
    ("trappe-ua", "use_trappe"),
    ("trappe-eh", "use_trappe"),
])
def test_other_families_are_unchanged(ff, key):
    f = _lammps_flags(None, {"preferred_ff": ff})
    assert f[key] is True
    assert sum(bool(v) for v in f.values()) == 1, f


def test_gaff_still_falls_through_to_no_flags():
    """RadonPy/GAFF2 legitimately sets none of the three -- the generator's default path
    is the GAFF2 one, so this must NOT be swept up by the compass fix."""
    assert not any(_lammps_flags(None, {"preferred_ff": "GAFF2_mod"}).values())


def test_explicit_json_still_wins():
    assert _lammps_flags('{"use_pcff": false, "use_opls": true, "use_trappe": false}',
                         {"preferred_ff": "compass"})["use_opls"] is True


# ─── hardware family, which picks engine and rank count ────────────────────────

@pytest.mark.parametrize("ff", ["pcff", "pcff_ore", "compass"])
def test_class_ii_fields_share_the_pcff_hardware_profile(ff):
    """compass resolving to "gaff" gave mpi_ranks=4 on a KOKKOS single-rank build --
    the exact combination the KOKKOS pinning note says must never be launched."""
    assert resolve_ff_family(ff, {}) == "pcff"


def test_unknown_field_still_defaults_to_gaff():
    assert resolve_ff_family("some-new-field", {}) == "gaff"


def test_alias_table_takes_precedence():
    hp = {"ff_aliases": {"compass": "opls"}}
    assert resolve_ff_family("compass", hp) == "opls"
