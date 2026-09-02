"""Multi-member value resolution for _exp_density_point / _exp_K_range.

Member resolution matches on the run's own SMILES (canonicalized, stereo-stripped)
against the class's member_smiles table, never run_name. No match -> refuse rather than
guess (no group-contribution density estimator exists, unlike Tg, so the fallback is
None, not another member's value). A planning agent that has reasoned out the correct
member pins it via overrides.experimental_density_gcm3 (OVERRIDE_RANGES), which lands
here as the plain-scalar branch.

_exp_density_range was removed (dead code, once the finite-size forecast stopped
consuming any curated experimental density -- see run_campaign.py's COMPRESSION_RATIO);
its coverage above (member-vs-class-vs-override resolution) is still exercised via
_exp_density_point, which is now the only surviving density-member resolver.

rules_common.canonicalize shells into a conda env, so it's monkeypatched to identity here;
PHYC's member_smiles carries placeholder tokens (not real chemistry) so matching stays
deterministic without real RDKit.
"""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "orchestration" / "scripts"))

import rules_common  # noqa: E402
from stage_params import _exp_density_point, _exp_K_range  # noqa: E402

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
    rules_common._canon_for_match.cache_clear()
    yield
    rules_common._canon_for_match.cache_clear()


@pytest.fixture(autouse=True)
def _identity_canonicalize(monkeypatch):
    monkeypatch.setattr(rules_common, "canonicalize", lambda smi, *a, **k: smi)


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
