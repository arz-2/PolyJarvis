"""Multi-member exp_density_gcm3 resolution for _exp_density_range / _exp_density_point.

`_exp_density_range` used to fall back to the class MEDIAN across every member of a
multi-member `experimental_density_gcm3` dict (e.g. PHYC's {PE: 0.855, PP: 0.91, PIB: 0.92})
when run_name didn't resolve a member -- silently grading against an unrelated member's real
measured value. A PE1 run got PP's median (0.91) banded to [0.864, 0.956] instead of PE's own
[0.812, 0.898], sitting PE's true ~0.855 g/cm3 right at the wrong band's edge.

Fixed the same way as _exp_tg_point: no run_name match -> refuse rather than guess (no
group-contribution density estimator exists, unlike Tg, so the fallback is the generic
density_initial_gcm3-derived band / None, not another member's value). A planning agent that
has reasoned out the correct member pins it via overrides.experimental_density_gcm3
(OVERRIDE_RANGES), which lands here as the plain-scalar branch.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "orchestration" / "scripts"))

from stage_params import _exp_density_range, _exp_density_point, _exp_K_range  # noqa: E402

PHYC = {
    "experimental_density_gcm3": {
        "PE": 0.855,
        "PP": 0.91,
        "PIB": 0.92,
        "note": "fully amorphous TraPPE-UA densities at 300K",
    }
}


def test_run_name_resolves_to_its_own_member_not_the_class_median():
    assert _exp_density_range(PHYC, run_name="PE1") == [round(0.855 * 0.95, 3), round(0.855 * 1.05, 3)]
    assert _exp_density_range(PHYC, run_name="PP2") == [round(0.91 * 0.95, 3), round(0.91 * 1.05, 3)]
    assert _exp_density_range(PHYC, run_name="PIB1") == [round(0.92 * 0.95, 3), round(0.92 * 1.05, 3)]


def test_no_run_name_falls_back_to_generic_band_not_a_sibling_members_value():
    d0 = PHYC.get("density_initial_gcm3", 0.6)
    implied_rt = d0 / 0.55
    expected = [round(implied_rt * 0.85, 3), round(implied_rt * 1.15, 3)]
    assert _exp_density_range(PHYC) == expected


def test_unmatched_run_name_falls_back_to_generic_band_not_a_sibling_members_value():
    d0 = PHYC.get("density_initial_gcm3", 0.6)
    implied_rt = d0 / 0.55
    expected = [round(implied_rt * 0.85, 3), round(implied_rt * 1.15, 3)]
    assert _exp_density_range(PHYC, run_name="UNKNOWN99") == expected


def test_single_value_class_unaffected():
    cls = {"experimental_density_gcm3": 1.19}
    assert _exp_density_range(cls, run_name="PMMA1") == [round(1.19 * 0.95, 3), round(1.19 * 1.05, 3)]


def test_scalar_experimental_density_override_wins_outright():
    """overrides.experimental_density_gcm3 replaces the class's dict wholesale via
    apply_plan's {**cls, **decided_params}, landing here as a plain scalar."""
    cls = {**PHYC, "experimental_density_gcm3": 0.855}
    assert _exp_density_range(cls, run_name="UNKNOWN99") == [round(0.855 * 0.95, 3), round(0.855 * 1.05, 3)]


def test_exp_density_point_unmatched_run_name_returns_none_not_a_sibling_members_value():
    assert _exp_density_point(PHYC, run_name="UNKNOWN99") is None
    assert _exp_density_point(PHYC) is None


def test_exp_density_point_run_name_resolves_its_own_member():
    assert _exp_density_point(PHYC, run_name="PE1") == 0.855


def test_exp_density_point_scalar_override_wins():
    cls = {**PHYC, "experimental_density_gcm3": 0.855}
    assert _exp_density_point(cls, run_name="UNKNOWN99") == 0.855


PACR = {
    "exp_K_GPa": {"min": 3.5, "max": 4.2,
                  "note": "K_T for glassy PMMA specifically -- PACR also covers PMA"},
}


def test_exp_k_range_uses_class_default_when_no_override():
    assert _exp_K_range(PACR) == [3.5, 4.2]


def test_exp_k_range_override_wins_for_a_different_member():
    """PACR's exp_K_GPa is scoped to PMMA only (see its note); a PMA run pins its own range."""
    cls = {**PACR, "exp_K_min_GPa": 2.1, "exp_K_max_GPa": 2.6}
    assert _exp_K_range(cls) == [2.1, 2.6]


def test_exp_k_range_no_class_default_and_no_override():
    assert _exp_K_range({}) == [None, None]
