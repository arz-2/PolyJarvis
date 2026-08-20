"""Multi-member exp_density_gcm3 resolution for _exp_density_range / _exp_density_point.

Member resolution matches on the run's own SMILES (canonicalized, stereo-stripped)
against the class's member_smiles table, never run_name. No match -> refuse rather than
guess (no group-contribution density estimator exists, unlike Tg, so the fallback is the
generic density_initial_gcm3-derived band / None, not another member's value). A planning
agent that has reasoned out the correct member pins it via overrides.experimental_density_gcm3
(OVERRIDE_RANGES), which lands here as the plain-scalar branch.

canon_smiles.canonicalize shells into a conda env, so it's monkeypatched to identity here;
PHYC's member_smiles carries placeholder tokens (not real chemistry) so matching stays
deterministic without real RDKit.
"""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "orchestration" / "scripts"))

import canon_smiles  # noqa: E402
import hw_common  # noqa: E402
from stage_params import _exp_density_range, _exp_density_point, _exp_K_range  # noqa: E402

PHYC = {
    "experimental_density_gcm3": {
        "PE": 0.855,
        "PP": 0.91,
        "PIB": 0.92,
        "note": "fully amorphous TraPPE-UA densities at 300K",
    },
    "member_smiles": {"PE": ["PE_SMI"], "PP": ["PP_SMI"], "PIB": ["PIB_SMI"]},
}


@pytest.fixture(autouse=True)
def _clear_canon_cache():
    hw_common._canon_for_match.cache_clear()
    yield
    hw_common._canon_for_match.cache_clear()


@pytest.fixture(autouse=True)
def _identity_canonicalize(monkeypatch):
    monkeypatch.setattr(canon_smiles, "canonicalize", lambda smi, *a, **k: smi)


def test_smiles_resolves_to_its_own_member_not_the_class_median():
    assert _exp_density_range(PHYC, smiles="PE_SMI") == [round(0.855 * 0.95, 3), round(0.855 * 1.05, 3)]
    assert _exp_density_range(PHYC, smiles="PP_SMI") == [round(0.91 * 0.95, 3), round(0.91 * 1.05, 3)]
    assert _exp_density_range(PHYC, smiles="PIB_SMI") == [round(0.92 * 0.95, 3), round(0.92 * 1.05, 3)]


def test_no_smiles_falls_back_to_generic_band_not_a_sibling_members_value():
    d0 = PHYC.get("density_initial_gcm3", 0.6)
    implied_rt = d0 / 0.55
    expected = [round(implied_rt * 0.85, 3), round(implied_rt * 1.15, 3)]
    assert _exp_density_range(PHYC) == expected


def test_unmatched_smiles_falls_back_to_generic_band_not_a_sibling_members_value():
    d0 = PHYC.get("density_initial_gcm3", 0.6)
    implied_rt = d0 / 0.55
    expected = [round(implied_rt * 0.85, 3), round(implied_rt * 1.15, 3)]
    assert _exp_density_range(PHYC, smiles="NOT_A_MEMBER") == expected


def test_single_value_class_unaffected():
    cls = {"experimental_density_gcm3": 1.19}
    assert _exp_density_range(cls, smiles="ANYTHING") == [round(1.19 * 0.95, 3), round(1.19 * 1.05, 3)]


def test_scalar_experimental_density_override_wins_outright():
    """overrides.experimental_density_gcm3 replaces the class's dict wholesale via
    apply_plan's {**cls, **decided_params}, landing here as a plain scalar."""
    cls = {**PHYC, "experimental_density_gcm3": 0.855}
    assert _exp_density_range(cls, smiles="NOT_A_MEMBER") == [round(0.855 * 0.95, 3), round(0.855 * 1.05, 3)]


def test_exp_density_point_unmatched_smiles_returns_none_not_a_sibling_members_value():
    assert _exp_density_point(PHYC, smiles="NOT_A_MEMBER") is None
    assert _exp_density_point(PHYC) is None


def test_exp_density_point_smiles_resolves_its_own_member():
    assert _exp_density_point(PHYC, smiles="PE_SMI") == 0.855


def test_exp_density_point_scalar_override_wins():
    cls = {**PHYC, "experimental_density_gcm3": 0.855}
    assert _exp_density_point(cls, smiles="NOT_A_MEMBER") == 0.855


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
