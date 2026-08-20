"""plan_system_size_arms.py: the opt-in two-arm split for divergent D-04 property floors.

The split rule is deliberately narrow -- it only fires when BOTH a genuine measured
entanglement floor (bulk_modulus) AND a Fox-Flory floor (tg) are in play and diverge by
a real margin. It reuses select_system_size.py's own property_floors()/select_system_size()
arithmetic rather than a second, driftable copy -- these tests pin that the two never
disagree.

Member resolution (which class member a SMILES is) matches on the run's own SMILES, not
run_name -- plan_arms() keeps a run_name parameter only to NAME the split arms
("<run_name>_tg" / "<run_name>_bm"). canon_smiles.canonicalize shells into a conda env, so
it's monkeypatched to identity here; PACR's member_smiles is locally overridden to the
test's own SMILES constants so matching stays deterministic without real RDKit.
"""
import copy
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))

import canon_smiles  # noqa: E402
import hw_common  # noqa: E402
import select_system_size as sss  # noqa: E402
import plan_system_size_arms as psa  # noqa: E402
import validate_run_plan as vrp  # noqa: E402
from plan_system_size_arms import plan_arms  # noqa: E402
from validate_run_plan import _target_density, _finite_size_findings  # noqa: E402
from hw_common import load_rules, get_class_entry  # noqa: E402

PACR_SMILES = "*CC(C)(C(=O)OC)*"
PHYC_SMILES = "*CC*"
PKTN_SMILES = "*c1ccc(Oc2ccc(C(=O)c3ccc(O*)cc3)cc2)cc1"


def _mw_stub(monkeypatch, atoms=15, mw=100.12):
    monkeypatch.setattr(sss, "_monomer_atoms_and_mw", lambda smiles, is_ua: (atoms, mw))


@pytest.fixture(autouse=True)
def _clear_canon_cache():
    hw_common._canon_for_match.cache_clear()
    yield
    hw_common._canon_for_match.cache_clear()


@pytest.fixture(autouse=True)
def _identity_canonicalize(monkeypatch):
    monkeypatch.setattr(canon_smiles, "canonicalize", lambda smi, *a, **k: smi)


def _patch_class_member_smiles(monkeypatch, polymer_class, member_smiles):
    """Real class entry with member_smiles overridden to the test's own SMILES constants,
    patched into every module that independently loads polymer_rules.json for this class
    (plan_system_size_arms, select_system_size, validate_run_plan)."""
    cls = copy.deepcopy(hw_common.get_class_entry(hw_common.load_rules(), polymer_class))
    cls["member_smiles"] = member_smiles
    fake_rules = {"classes": {polymer_class: cls}}
    fake_get = lambda rules, pc, warn_on_miss=False: cls
    for mod in (psa, sss, vrp):
        monkeypatch.setattr(mod, "load_rules", lambda: fake_rules)
        monkeypatch.setattr(mod, "get_class_entry", fake_get)
    return cls


# --- split fires: large, genuine divergence ----------------------------------------

def test_split_fires_for_pacr_pmma_tg_and_bulk_modulus(monkeypatch):
    _mw_stub(monkeypatch)
    _patch_class_member_smiles(monkeypatch, "PACR", {"PMMA": [PACR_SMILES]})
    r = plan_arms("PACR", PACR_SMILES, "PMMA1", ["tg", "bulk_modulus"])
    assert r["split"] is True
    assert r["divergence"] == pytest.approx(125 / 20)
    arms = {a["run_name"]: a for a in r["arms"]}
    assert arms["PMMA1_tg"]["properties"] == ["tg"]
    assert arms["PMMA1_tg"]["dp_typical"] == 20
    assert arms["PMMA1_bm"]["properties"] == ["bulk_modulus"]
    assert arms["PMMA1_bm"]["dp_typical"] == 125


def test_split_carries_density_along_with_the_tg_arm(monkeypatch):
    _mw_stub(monkeypatch)
    _patch_class_member_smiles(monkeypatch, "PACR", {"PMMA": [PACR_SMILES]})
    r = plan_arms("PACR", PACR_SMILES, "PMMA1", ["tg", "bulk_modulus", "density"])
    assert r["split"] is True
    tg_arm = next(a for a in r["arms"] if a["run_name"] == "PMMA1_tg")
    assert tg_arm["properties"] == ["density", "tg"]
    bm_arm = next(a for a in r["arms"] if a["run_name"] == "PMMA1_bm")
    assert bm_arm["properties"] == ["bulk_modulus"]


# --- split does not fire ------------------------------------------------------------

def test_no_split_for_a_single_property_request():
    r = plan_arms("PACR", PACR_SMILES, "PMMA1", ["tg"])
    assert r["split"] is False
    assert len(r["arms"]) == 1
    assert r["arms"][0]["run_name"] == "PMMA1"
    assert "not requested alongside" in r["reason"]


def test_no_split_when_bulk_modulus_floor_is_mw_floor_unknown():
    """PHYC has no documented Me -- nothing principled to size a second arm around."""
    r = plan_arms("PHYC", PHYC_SMILES, "PE_TEST", ["tg", "bulk_modulus"])
    assert r["split"] is False
    assert "MW_FLOOR_UNKNOWN" in r["reason"]
    # single arm must still cover both requested properties, unlike a real split
    assert set(r["arms"][0]["properties"]) == {"tg", "bulk_modulus"}


def test_no_split_when_divergence_is_below_threshold(monkeypatch):
    """A large Me relative to repeat-unit MW keeps DP@Me close to the tg floor."""
    _mw_stub(monkeypatch, atoms=15, mw=6300)  # DP@Me = 12500/6300 ~ 1.98 < tg floor 20
    _patch_class_member_smiles(monkeypatch, "PACR", {"PMMA": [PACR_SMILES]})
    r = plan_arms("PACR", PACR_SMILES, "PMMA1", ["tg", "bulk_modulus"])
    assert r["split"] is False
    assert "below the" in r["reason"] and "threshold" in r["reason"]


def test_no_split_arm_dp_still_raises_to_a_real_floor_violation():
    """No-split path must still apply select_system_size.py's own floor-violation rule,
    not silently keep an under-provisioned dp_typical."""
    r = plan_arms("PKTN", PKTN_SMILES, "PEEK_TEST", ["tg", "bulk_modulus"], dp_typical=32)
    assert r["split"] is False  # PKTN has no documented Me -> MW_FLOOR_UNKNOWN
    assert r["arms"][0]["dp_typical"] == 50  # PKTN's stiff Fox-Flory floor, not 32


def test_no_split_arm_dp_never_shrinks_an_over_provisioned_default():
    r = plan_arms("PHYC", PHYC_SMILES, "PE_TEST", ["tg"], dp_typical=120)
    assert r["split"] is False
    assert r["arms"][0]["dp_typical"] == 120  # not shrunk to the tg floor of 20


# --- consistency: never a second copy of the floor arithmetic ----------------------

def test_split_arm_dp_matches_property_floors_exactly(monkeypatch):
    _mw_stub(monkeypatch)
    _patch_class_member_smiles(monkeypatch, "PACR", {"PMMA": [PACR_SMILES]})
    from select_system_size import property_floors
    pf = property_floors("PACR", PACR_SMILES, ["tg", "bulk_modulus"])
    r = plan_arms("PACR", PACR_SMILES, "PMMA1", ["tg", "bulk_modulus"])
    arms = {a["run_name"]: a for a in r["arms"]}
    assert arms["PMMA1_tg"]["dp_typical"] == pf["tg"]["floor_dp"]
    assert arms["PMMA1_bm"]["dp_typical"] == pf["bulk_modulus"]["floor_dp"]


def test_custom_divergence_threshold_is_respected(monkeypatch):
    _mw_stub(monkeypatch)  # divergence 6.25x
    _patch_class_member_smiles(monkeypatch, "PACR", {"PMMA": [PACR_SMILES]})
    r = plan_arms("PACR", PACR_SMILES, "PMMA1", ["tg", "bulk_modulus"],
                 divergence_threshold=10.0)
    assert r["split"] is False


def test_no_properties_requested_is_an_error():
    r = plan_arms("PACR", PACR_SMILES, "PMMA1", [])
    assert "error" in r


# --- member resolution is via SMILES, not the arm's run_name suffix ----------------
# _target_density used to match run_name.upper().startswith(member_key) (or, further
# back, an even stricter rstrip-digits exact match) -- both broke on any run_name
# carrying characters after the member prefix, exactly the shape this script's own
# "<base>_tg" / "<base>_bm" arm names have. Member identity is now resolved from the
# run's own SMILES, so a split arm's derived run_name is irrelevant to whether the
# finite-size pre-check can find a target density.

def test_target_density_resolves_via_smiles_regardless_of_run_name(monkeypatch):
    cls = _patch_class_member_smiles(monkeypatch, "PACR", {"PMMA": [PACR_SMILES]})
    assert _target_density(cls, PACR_SMILES) is not None


def test_finite_size_pre_check_actually_runs_for_a_split_tg_arm(monkeypatch):
    """Regression test for the silent no-op: a split arm's plan must reach a real
    finite_size_min_image finding (info or structural), driven by the plan's smiles,
    regardless of what its (derived, "<base>_tg"-suffixed) run_name looks like."""
    _patch_class_member_smiles(monkeypatch, "PACR", {"PMMA": [PACR_SMILES]})
    plan = {"smiles": PACR_SMILES, "polymer_class": "PACR", "run_name": "PMMA1_tg",
           "decided_params": {"dp_typical": 20, "nchain": 10}}
    f = _finite_size_findings(plan)
    assert [x["check"] for x in f] == ["finite_size_min_image"]
