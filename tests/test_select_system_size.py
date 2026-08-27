"""D-04_system_size selection: property-scoped DP floors, and the member-generalization
bug this file locks against.

Two things easy to quietly regress:
  - a class default already above its documented floor must never be silently shrunk --
    that would invalidate an already-protocol_validated SMILES without ever consulting
    the reproducibility carve-out. Downward gaps are reported, never overridden.
  - entanglement Me is documented for ONE member of a multi-member class, not the class.
    Applying PMMA's Me to PAA (both PACR) would repeat the bug this codebase already
    found and fixed once for experimental density (stage_params.py:217-223, PE1 vs PP).

Member resolution matches on the run's own SMILES (canonicalized, stereo-stripped)
against the class's member_smiles table, not run_name. canon_smiles.canonicalize shells
into a conda env, so it's monkeypatched to identity here and member_smiles fixtures are
built from the test's own SMILES constants -- no real RDKit call in this file.
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
from select_system_size import (select_system_size, solve_system_size, _fox_flory_floor,
                                property_floors)  # noqa: E402
from validate_run_plan import (_system_size_findings,
                               _system_size_over_provisioned_findings)  # noqa: E402

PACR_SMILES = "*CC(C)(C(=O)OC)*"
PAA_SMILES = "*CC(C(=O)O)*"
PHYC_SMILES = "*CC*"
PKTN_SMILES = "*c1ccc(Oc2ccc(C(=O)c3ccc(O*)cc3)cc2)cc1"
PCBN_SMILES = "*Oc1ccc(C(C)(C)c2ccc(OC(=O)*)cc2)cc1"
OTHER_PC_SMILES = "*Oc1ccc(C(C)(C)C)cc1*"  # a different, unmatched hypothetical polycarbonate


@pytest.fixture(autouse=True)
def _clear_canon_cache():
    hw_common._canon_for_match.cache_clear()
    yield
    hw_common._canon_for_match.cache_clear()


@pytest.fixture(autouse=True)
def _identity_canonicalize(monkeypatch):
    monkeypatch.setattr(canon_smiles, "canonicalize", lambda smi, *a, **k: smi)


@pytest.fixture(autouse=True)
def _no_real_rdkit_for_rigidity_by_default(monkeypatch):
    """This file's own invariant (see module docstring) is no real RDKit call.
    solve_system_size()'s tg-only rigidity/Kuhn branch calls _monomer_atoms_and_mw and
    _backbone_rigidity unconditionally whenever "tg" is requested -- default both to
    inert stand-ins here (rigidity=None degrades to a no-op uncertainty, never touching
    recommended_dp) so every pre-existing tg-only test keeps testing only what it was
    written to test. Tests of the new rigidity/Kuhn feature itself override
    sss._backbone_rigidity (and, where relevant, sss._monomer_atoms_and_mw) explicitly."""
    monkeypatch.setattr(sss, "_monomer_atoms_and_mw", lambda smiles, is_ua: (10, 1000.0))
    monkeypatch.setattr(sss, "_backbone_rigidity", lambda smiles: None)


def _patch_class_member_smiles(monkeypatch, polymer_class, member_smiles):
    """Real class entry with member_smiles overridden to the test's own SMILES constants,
    so matching is trivial under the identity-patched canonicalizer without depending on
    guides/polymer_rules.json's real curated (truly canonical) forms."""
    cls = copy.deepcopy(hw_common.get_class_entry(hw_common.load_rules(), polymer_class))
    cls["member_smiles"] = member_smiles
    monkeypatch.setattr(sss, "load_rules", lambda: {"classes": {polymer_class: cls}})
    monkeypatch.setattr(sss, "get_class_entry",
                        lambda rules, pc, warn_on_miss=False: cls)
    return cls


# --- Fox-Flory: class-level, stiff vs flexible -------------------------------------

def test_stiff_classes_get_the_higher_fox_flory_floor():
    floor_stiff, _ = _fox_flory_floor("PKTN")
    floor_flex, _ = _fox_flory_floor("PHYC")
    assert floor_stiff == 50
    assert floor_flex == 20


def test_stiff_class_dp_below_its_own_floor_overrides():
    """A stiff-backbone dp_typical below 50 is a real floor violation, not an efficiency
    question -- must override upward. dp_typical is passed explicitly (rather than relying
    on PKTN's current class default, which this same validation pass already corrected to
    50) so the mechanism stays covered even after the data fix."""
    result = select_system_size("PKTN", PKTN_SMILES, properties=["tg"], dp_typical=32)
    assert result["decided_params_override"] == {"dp_typical": 50}
    assert result["decision"]["required_dp_floor"] == 50


def test_flexible_class_at_default_clears_tg_floor_no_override():
    result = select_system_size("PHYC", PHYC_SMILES, properties=["tg"])
    assert result["decided_params_override"] == {}
    assert result["decision"]["required_dp_floor"] == 20


def test_over_provisioned_gap_is_reported_never_overridden():
    """PHYC's dp_typical=120 is 6x its Tg floor -- efficiency gap, not a violation.
    Shrinking DP for an already-validated SMILES is a protocol change this script does
    not have standing to make."""
    result = select_system_size("PHYC", PHYC_SMILES, properties=["tg"])
    assert result["decided_params_override"] == {}
    names = [u["name"] for u in result["uncertainties"]]
    assert "size_over_provisioned" in names


# --- entanglement Me: per-member, never generalized across a class -----------------

def test_entanglement_floor_resolves_the_matched_member(monkeypatch):
    """Entanglement Me is still resolved and reported (DP@Me=125), but is advisory only for
    bulk_modulus -- user-directed benchmark criterion, 2026-08-25: Me gates plateau shear
    modulus/viscoelastic relaxation, not the isothermal bulk modulus. It must never feed
    required_dp_floor/decided_params_override."""
    monkeypatch.setattr(sss, "_monomer_atoms_and_mw", lambda smiles, is_ua: (15, 100.12))
    _patch_class_member_smiles(monkeypatch, "PACR", {"PMMA": [PACR_SMILES]})
    result = select_system_size("PACR", PACR_SMILES, properties=["bulk_modulus"])
    assert result["decided_params_override"] == {}
    assert result["decision"]["required_dp_floor"] is None
    advisory = next(u for u in result["uncertainties"] if u["name"] == "entanglement_dp_advisory")
    assert advisory["dp_at_me"] == 125


def test_entanglement_floor_refuses_an_unmatched_sibling_member(monkeypatch):
    """PACR documents Me for PMMA only. A PAA run must NOT inherit PMMA's floor --
    regression test for the member-generalization bug (see module docstring)."""
    monkeypatch.setattr(sss, "_monomer_atoms_and_mw",
                        lambda *a, **k: pytest.fail("must not reach RDKit for an unmatched member"))
    _patch_class_member_smiles(monkeypatch, "PACR", {"PMMA": [PACR_SMILES]})
    result = select_system_size("PACR", PAA_SMILES, properties=["bulk_modulus"])
    assert result["decided_params_override"] == {}
    assert result["decision"]["required_dp_floor"] is None
    unc = next(u for u in result["uncertainties"] if u["name"] == "MW_FLOOR_UNKNOWN")
    assert "PMMA" in unc["detail"]


def test_entanglement_floor_refuses_an_unresolvable_smiles_for_a_multimember_class(monkeypatch):
    _patch_class_member_smiles(monkeypatch, "PACR", {"PMMA": [PACR_SMILES]})
    result = select_system_size("PACR", PAA_SMILES, properties=["bulk_modulus"])
    assert result["decided_params_override"] == {}
    assert any(u["name"] == "MW_FLOOR_UNKNOWN" for u in result["uncertainties"])


def test_undocumented_class_bulk_modulus_is_mw_floor_unknown():
    result = select_system_size("PHYC", PHYC_SMILES, properties=["bulk_modulus"])
    assert result["decided_params_override"] == {}
    assert any(u["name"] == "MW_FLOOR_UNKNOWN" for u in result["uncertainties"])


def test_single_member_class_resolves_via_its_own_smiles(monkeypatch):
    """PCBN has exactly one documented member (BPA_PC), but resolution still goes through
    a real SMILES match against member_smiles -- not a bare "only one key exists" shortcut,
    which would silently swallow a different polycarbonate chemistry planned under PCBN.
    Me resolving successfully is reported via entanglement_dp_advisory (never
    MW_FLOOR_UNKNOWN) -- but stays advisory, never required_dp_floor, for bulk_modulus."""
    monkeypatch.setattr(sss, "_monomer_atoms_and_mw", lambda smiles, is_ua: (22, 254.0))
    _patch_class_member_smiles(monkeypatch, "PCBN", {"BPA_PC": [PCBN_SMILES]})
    result = select_system_size("PCBN", PCBN_SMILES, properties=["bulk_modulus"])
    assert result["decision"]["required_dp_floor"] is None
    assert not any(u["name"] == "MW_FLOOR_UNKNOWN" for u in result["uncertainties"])
    assert any(u["name"] == "entanglement_dp_advisory" for u in result["uncertainties"])


def test_single_member_class_still_refuses_an_unmatched_smiles(monkeypatch):
    """Regression for the deleted single-member carve-out: a class with exactly one
    documented member must still come back MW_FLOOR_UNKNOWN for a SMILES that isn't it,
    not resolve unconditionally just because there was only one key to pick from."""
    monkeypatch.setattr(sss, "_monomer_atoms_and_mw",
                        lambda *a, **k: pytest.fail("must not reach RDKit for an unmatched member"))
    _patch_class_member_smiles(monkeypatch, "PCBN", {"BPA_PC": [PCBN_SMILES]})
    result = select_system_size("PCBN", OTHER_PC_SMILES, properties=["bulk_modulus"])
    assert result["decided_params_override"] == {}
    assert any(u["name"] == "MW_FLOOR_UNKNOWN" for u in result["uncertainties"])


def test_density_only_request_has_no_dp_floor():
    result = select_system_size("PHYC", PHYC_SMILES, properties=["density"])
    assert result["decided_params_override"] == {}
    assert result["decision"]["required_dp_floor"] is None


# --- nchain: advisory only, PCFF production-minimum fact ---------------------------

def test_nchain_below_pcff_production_minimum_is_advisory():
    result = select_system_size("PACR", PACR_SMILES, properties=["tg"])
    names = [u["name"] for u in result["uncertainties"]]
    assert "nchain_below_production_minimum" in names
    # never a decided_params_override -- L>=2*Rg is the binding constraint, elsewhere
    assert "nchain" not in result["decided_params_override"]


def test_nchain_advisory_does_not_fire_for_non_pcff_classes():
    result = select_system_size("PHYC", PHYC_SMILES, properties=["tg"])
    names = [u["name"] for u in result["uncertainties"]]
    assert "nchain_below_production_minimum" not in names


# --- property_floors: the per-property piece select_system_size() collapses via max() --
# select_system_size()'s own tests above already exercise these mechanisms end-to-end
# through the collapsed max(); these confirm the standalone per-property dict shape a
# multi-arm planner needs (one arm sized off "tg" alone, another off "bulk_modulus" alone).

def test_property_floors_returns_one_entry_per_requested_property():
    pf = property_floors("PKTN", PKTN_SMILES, ["tg", "density"])
    assert set(pf) == {"tg", "density"}
    assert pf["tg"]["floor_dp"] == 50 and pf["tg"]["source"] == "fox_flory_tg"
    assert pf["density"]["floor_dp"] is None and pf["density"]["unmet"] is None


def test_property_floors_entanglement_matches_select_system_size(monkeypatch):
    monkeypatch.setattr(sss, "_monomer_atoms_and_mw", lambda smiles, is_ua: (15, 100.12))
    cls = _patch_class_member_smiles(monkeypatch, "PACR", {"PMMA": [PACR_SMILES]})
    pf = property_floors("PACR", PACR_SMILES, ["bulk_modulus"], cls=cls)
    assert pf["bulk_modulus"]["floor_dp"] == 125
    assert pf["bulk_modulus"]["source"] == "entanglement_bm"
    assert pf["bulk_modulus"]["unmet"] is None


def test_property_floors_unmet_carries_the_mw_floor_unknown_reason():
    pf = property_floors("PHYC", PHYC_SMILES, ["bulk_modulus"])
    assert pf["bulk_modulus"]["floor_dp"] is None
    assert pf["bulk_modulus"]["unmet"]["name"] == "MW_FLOOR_UNKNOWN"


def test_property_floors_order_is_canonical_not_set_iteration_order():
    """dict key order must be tg, bulk_modulus, density regardless of input order --
    select_system_size()'s reason text joins floors in this order for reproducibility."""
    pf = property_floors("PKTN", PKTN_SMILES, {"density", "bulk_modulus", "tg"})
    assert list(pf) == ["tg", "bulk_modulus", "density"]


# --- validator: floor violation must be raised or acknowledged, never silent -------
#
# _system_size_findings re-runs select_system_size.py live against the plan's own
# smiles/properties (mirrors _hardware_findings' pattern for D-08) rather than trusting a
# required_dp_floor the plan's own decisions[] row may never carry -- make_deterministic_
# plan.py's build_decisions() never populates that key today, which made the old
# fake-plan-dict version of this test suite vacuously pass on every real plan (confirmed
# against data/PE1, data/PP, data/a-PS). These tests build real (smiles, polymer_class,
# properties) plans instead. None of them touch bulk_modulus, so no SMILES canonicalization
# ever runs for them (Fox-Flory is class-level, not member-resolved).

def _plan(polymer_class="PKTN", smiles=PKTN_SMILES, properties=None,
          dp=32, nchain=None, uncertainties=None):
    return {"smiles": smiles, "polymer_class": polymer_class,
            "properties": properties if properties is not None else ["tg"],
            "decided_params": {"dp_typical": dp, "nchain": nchain},
            "uncertainties": uncertainties or []}


def test_floor_violation_unacknowledged_is_structural():
    """PKTN is stiff-backbone (Fox-Flory floor 50); dp=32 violates it even though the
    live class default (also 50, post D-04 data fix) would not."""
    f = _system_size_findings(_plan(dp=32))
    assert [x["check"] for x in f] == ["system_size_dp_floor_unacknowledged"]
    assert f[0]["severity"] == "structural"
    assert "required_dp_floor=50" in f[0]["detail"]


def test_floor_violation_acknowledged_clears():
    f = _system_size_findings(_plan(dp=32, uncertainties=[{"name": "system_size_dp_floor"}]))
    assert f == []


def test_floor_satisfied_no_finding():
    f = _system_size_findings(_plan(dp=50))
    assert f == []


def test_plan_missing_smiles_or_class_is_unaffected():
    assert _system_size_findings({"decided_params": {"dp_typical": 5}}) == []
    assert _system_size_findings({"smiles": PKTN_SMILES,
                                  "decided_params": {"dp_typical": 5}}) == []


def test_plan_without_a_measured_floor_is_unaffected():
    """density-only request -- no Fox-Flory or entanglement floor applies at all."""
    plan = _plan(polymer_class="PHYC", smiles=PHYC_SMILES, properties=["density"], dp=5)
    assert _system_size_findings(plan) == []


def test_select_system_size_exception_is_a_structural_finding(monkeypatch):
    """Mirrors _hardware_findings: a broken check must not silently pass a plan."""
    import validate_run_plan as vrp
    def _raise(*a, **k):
        raise RuntimeError("boom")
    monkeypatch.setattr(vrp, "select_system_size", _raise)
    f = vrp._system_size_findings(_plan(dp=32))
    assert [x["check"] for x in f] == ["system_size_safety"]
    assert f[0]["severity"] == "structural"


def test_live_check_catches_a_previously_vacuous_real_plan():
    """Regression test for the historical gap: a plan with no required_dp_floor on its
    D-04 row (every real committed plan, pre-fix) must still be checked live."""
    plan = _plan(dp=32)
    assert "decisions" not in plan  # no D-04 row to read required_dp_floor off of at all
    f = _system_size_findings(plan)
    assert [x["check"] for x in f] == ["system_size_dp_floor_unacknowledged"]


# --- solve_system_size: the cost-minimizing companion, additive -- select_system_size()
# above is completely unchanged (still what _system_size_findings checks every plan,
# replay or reasoned, against). solve_system_size() is only ever meant to be called from
# scientific_control.py:materialize_plan(), which only ever produces plan_mode="reasoned"
# plans -- so shrinking an over-provisioned DP here carries no replay-safety risk. ------

def test_solve_shrinks_an_over_provisioned_class_default_to_the_floor():
    """Mirrors test_over_provisioned_gap_is_reported_never_overridden's PHYC case, but
    solve_system_size() recommends the floor-clearing minimum instead of only reporting."""
    r = solve_system_size("PHYC", PHYC_SMILES, properties=["tg"])
    assert r["recommended_params"] == {"dp_typical": 20}
    # the base select_system_size() uncertainty is still carried through for provenance --
    # solve_system_size() adds the fix, it doesn't erase the record of the original gap
    assert "size_over_provisioned" in [u["name"] for u in r["uncertainties"]]


def test_solve_raises_an_under_provisioned_dp_to_the_floor():
    r = solve_system_size("PKTN", PKTN_SMILES, properties=["tg"], dp_typical=32)
    assert r["recommended_params"]["dp_typical"] == 50


def test_solve_recommends_pcff_nchain_minimum():
    r = solve_system_size("PACR", PACR_SMILES, properties=["tg"], nchain=10)
    assert r["recommended_params"]["nchain"] == 20


def test_solve_no_change_when_class_default_already_at_the_floor():
    r = solve_system_size("PHYC", PHYC_SMILES, properties=["tg"], dp_typical=20, nchain=20)
    assert r["recommended_params"] == {}


# --- literature grounding: makes the recommendation vary by molecule, not just class -----

_LIT_GROUNDING_SCHEMA = {  # matches .claude/agents/system-size-literature-worker.md's schema
    "system_size": {"dp_typical": 200, "nchain": 12,
                    "convergence_basis": "entanglement_mw", "confidence": "medium"},
}


def test_literature_grounding_provides_the_bulk_modulus_recommendation(monkeypatch):
    """bulk_modulus has no mechanized DP floor (entanglement Me is advisory only, user-
    directed benchmark criterion 2026-08-25) -- a real per-molecule convergence-DP citation
    now IS the recommendation outright, not merely something that can raise an existing
    floor."""
    monkeypatch.setattr(sss, "_monomer_atoms_and_mw", lambda smiles, is_ua: (15, 100.12))
    _patch_class_member_smiles(monkeypatch, "PACR", {"PMMA": [PACR_SMILES]})
    r = solve_system_size("PACR", PACR_SMILES, properties=["bulk_modulus"],
                          dp_typical=50, literature_grounding=_LIT_GROUNDING_SCHEMA)
    assert r["decision"]["required_dp_floor"] is None  # entanglement Me is advisory, not a floor
    assert r["recommended_params"]["dp_typical"] == 200
    assert any("entanglement Me is documented but advisory" in reason
              for reason in r["recommendation_reasons"])


def test_literature_grounding_used_even_at_low_confidence_when_no_floor_stands(monkeypatch):
    """Unlike a genuine mechanized floor (Fox-Flory for tg, which gates literature grounding
    to medium/high confidence before letting it raise the recommendation), bulk_modulus has
    no floor to protect against being undercut -- any confidence beats no recommendation."""
    monkeypatch.setattr(sss, "_monomer_atoms_and_mw", lambda smiles, is_ua: (15, 100.12))
    _patch_class_member_smiles(monkeypatch, "PACR", {"PMMA": [PACR_SMILES]})
    low_conf = {"system_size": {**_LIT_GROUNDING_SCHEMA["system_size"], "confidence": "low"}}
    r = solve_system_size("PACR", PACR_SMILES, properties=["bulk_modulus"],
                          dp_typical=50, literature_grounding=low_conf)
    assert r["recommended_params"]["dp_typical"] == 200


def test_literature_grounding_resolves_mw_floor_unknown_at_any_confidence(monkeypatch):
    """PAA has no documented Me (PACR only documents PMMA) -- MW_FLOOR_UNKNOWN today. Even
    a low-confidence literature grounding is strictly better than outright refusal."""
    monkeypatch.setattr(sss, "_monomer_atoms_and_mw",
                        lambda *a, **k: pytest.fail("must not reach RDKit for a direct-DP grounding"))
    _patch_class_member_smiles(monkeypatch, "PACR", {"PMMA": [PACR_SMILES]})
    low_conf = {"system_size": {"dp_typical": 90, "nchain": None,
                                "convergence_basis": "class_analogy", "confidence": "low"}}
    r = solve_system_size("PACR", PAA_SMILES, properties=["bulk_modulus"],
                          dp_typical=50, literature_grounding=low_conf)
    assert r["decision"]["required_dp_floor"] is None  # base check still refuses
    assert r["floor_was_unknown"] is True
    assert r["recommended_params"]["dp_typical"] == 90
    assert any("otherwise-unassessed" in reason for reason in r["recommendation_reasons"])


def test_literature_grounding_never_lowers_a_recommendation():
    """A literature dp_typical below the mechanized floor must not undercut it -- a single
    per-molecule study is not licensed to undercut Fox-Flory/entanglement-Me evidence."""
    low_dp = {"system_size": {"dp_typical": 10, "nchain": None,
                              "convergence_basis": "class_analogy", "confidence": "high"}}
    r = solve_system_size("PKTN", PKTN_SMILES, properties=["tg"], dp_typical=32,
                          literature_grounding=low_dp)
    assert r["recommended_params"]["dp_typical"] == 50  # the Fox-Flory stiff floor, not 10


# --- validate_run_plan._system_size_over_provisioned_findings: symmetric to the
# under-provision check, gated on plan_mode -- a replay must never be flagged. -------------

def _reasoned_plan(polymer_class="PHYC", smiles=PHYC_SMILES, properties=None,
                   dp=120, nchain=None, uncertainties=None, plan_mode="reasoned"):
    return {"smiles": smiles, "polymer_class": polymer_class,
            "properties": properties if properties is not None else ["tg"],
            "decided_params": {"dp_typical": dp, "nchain": nchain},
            "uncertainties": uncertainties or [], "plan_mode": plan_mode}


def test_over_provisioned_unacknowledged_is_structural_for_a_reasoned_plan():
    """PHYC dp=120 is 6x its Fox-Flory floor (20) -- flagged when reasoned and unacknowledged."""
    f = _system_size_over_provisioned_findings(_reasoned_plan(dp=120))
    assert [x["check"] for x in f] == ["system_size_over_provisioned_unacknowledged"]
    assert f[0]["severity"] == "structural"


def test_over_provisioned_acknowledged_clears():
    f = _system_size_over_provisioned_findings(_reasoned_plan(
        dp=120, uncertainties=[{"name": "system_size_over_provisioned"}]))
    assert f == []


def test_over_provisioned_check_never_fires_on_a_replay():
    """Structural belt-and-suspenders: a protocol_validated replay's plan_mode is
    "deterministic", never "reasoned" -- this check must not touch it even if its DP
    happens to look over-provisioned by the same threshold."""
    f = _system_size_over_provisioned_findings(_reasoned_plan(dp=120, plan_mode="deterministic"))
    assert f == []


def test_over_provisioned_check_no_finding_when_dp_already_at_the_floor():
    f = _system_size_over_provisioned_findings(_reasoned_plan(dp=20))
    assert f == []


def test_me_estimated_gmol_computes_dp_at_me_the_same_way_a_documented_table_me_does(monkeypatch):
    """Priority-3 fallback: a packing-length-derived Me estimate, reduced to the same
    DP@Me = Me/repeat-unit-MW arithmetic a curated table Me already uses -- never a second,
    invented formula in this script."""
    monkeypatch.setattr(sss, "_monomer_atoms_and_mw",
                        lambda smiles, is_ua: (10, 74.15))  # PDMS-scale repeat unit
    packing_length_grounding = {
        "system_size": {"dp_typical": None, "nchain": None,
                        "convergence_basis": "packing_length_estimate",
                        "confidence": "low", "me_estimated_gmol": 7415.0},
    }
    r = solve_system_size("PHYC", PHYC_SMILES, properties=["bulk_modulus"], dp_typical=50,
                          literature_grounding=packing_length_grounding)
    # PHYC has no documented entanglement Me at all -> base floor is None (MW_FLOOR_UNKNOWN)
    assert r["decision"]["required_dp_floor"] is None
    assert r["recommended_params"]["dp_typical"] == round(7415.0 / 74.15)  # == 100
    assert any("packing-length Me estimate" in reason for reason in r["recommendation_reasons"])


# --- rigidity/Kuhn-based DP recommendation (tg only) -------------------------------
#
# _backbone_rigidity/_monomer_atoms_and_mw default to inert stand-ins for every test in
# this file (see the autouse fixture above) -- these tests explicitly override them to
# exercise the new feature. Real backbone_rigidity.py classification correctness (does a
# given SMILES actually come out flexible/semi_rigid/stiff) is tested separately in
# test_backbone_rigidity.py against real RDKit; these tests only cover
# solve_system_size()'s arithmetic given a rigidity result.

_FLEXIBLE = {"rigidity_class": "flexible", "classification_note": "flexible (stub)"}
_STIFF = {"rigidity_class": "stiff", "classification_note": "stiff (stub)"}


def test_rigidity_flexible_uses_dp_mw_alone(monkeypatch):
    monkeypatch.setattr(sss, "_monomer_atoms_and_mw", lambda smiles, is_ua: (2, 100.0))
    monkeypatch.setattr(sss, "_backbone_rigidity", lambda smiles: _FLEXIBLE)
    r = solve_system_size("PACR", PACR_SMILES, properties=["tg"], dp_typical=10, nchain=20)
    # DP_MW = ceil(5000/100) = 50; PACR's Fox-Flory floor for tg is 20 -- DP_MW dominates.
    assert r["recommended_params"]["dp_typical"] == 50
    assert any("DP_MW=50" in reason for reason in r["recommendation_reasons"])


def test_rigidity_stiff_with_literature_kuhn_raises_above_dp_mw(monkeypatch):
    monkeypatch.setattr(sss, "_monomer_atoms_and_mw", lambda smiles, is_ua: (2, 100.0))
    monkeypatch.setattr(sss, "_backbone_rigidity", lambda smiles: _STIFF)
    lit = {"system_size": {"kuhn_molar_mass_gmol": 3000.0, "kuhn_length_A": 25.0}}
    r = solve_system_size("PACR", PACR_SMILES, properties=["tg"], dp_typical=10, nchain=20,
                          literature_grounding=lit)
    # DP_MW = ceil(5000/100) = 50; DP_Kuhn = ceil(7*3000/100) = 210 -- Kuhn dominates.
    assert r["recommended_params"]["dp_typical"] == 210
    assert any("DP_Kuhn=210" in reason for reason in r["recommendation_reasons"])


def test_rigidity_stiff_without_literature_kuhn_falls_back_to_dp_min(monkeypatch):
    """Refuse-rather-than-fabricate: no literature Kuhn value -> KUHN_LENGTH_UNKNOWN,
    fall back to max(DP_MW, dp_min), never an invented structural estimate."""
    monkeypatch.setattr(sss, "_monomer_atoms_and_mw", lambda smiles, is_ua: (2, 100.0))
    monkeypatch.setattr(sss, "_backbone_rigidity", lambda smiles: _STIFF)
    r = solve_system_size("PACR", PACR_SMILES, properties=["tg"], dp_typical=10, nchain=20)
    # DP_MW=50, PACR dp_min=30 -> max(50,30)=50; PACR's own Fox-Flory floor (20) is lower.
    assert r["recommended_params"]["dp_typical"] == 50
    assert any(u["name"] == "KUHN_LENGTH_UNKNOWN" for u in r["uncertainties"])


def test_rigidity_estimate_failure_is_advisory_only(monkeypatch):
    """backbone_rigidity.py subprocess failing (missing rdkit/conda, timeout) must not
    crash the solve or silently change the recommendation -- just note it."""
    monkeypatch.setattr(sss, "_monomer_atoms_and_mw", lambda smiles, is_ua: (2, 100.0))
    monkeypatch.setattr(sss, "_backbone_rigidity", lambda smiles: None)
    r = solve_system_size("PACR", PACR_SMILES, properties=["tg"], dp_typical=10, nchain=20)
    assert any(u["name"] == "backbone_rigidity_estimate_failed" for u in r["uncertainties"])
    # Falls back to the plain Fox-Flory floor (20), unaffected by the rigidity check.
    assert r["recommended_params"]["dp_typical"] == 20


def test_rigidity_skipped_entirely_for_a_bulk_modulus_only_request(monkeypatch):
    """The rigidity/Kuhn branch is tg-specific -- it must not fire (or call RDKit at all)
    for a bulk_modulus-only request."""
    calls = []
    monkeypatch.setattr(sss, "_backbone_rigidity", lambda smiles: calls.append(smiles) or _STIFF)
    solve_system_size("PHYC", PHYC_SMILES, properties=["bulk_modulus"], dp_typical=50)
    assert calls == []


def test_dp_from_mw_baseline_is_5000_gmol():
    assert sss._dp_from_mw(100.0) == 50  # ceil(5000/100)
    assert sss._dp_from_mw(28.05) == 179  # PE's real repeat-unit MW


def test_dp_from_kuhn_uses_the_named_target_constant():
    assert sss.KUHN_SEGMENTS_PER_CHAIN_TARGET == 7
    assert sss._dp_from_kuhn(kuhn_molar_mass_gmol=1500.0, m_repeat_gmol=288.3) == 37


def test_kuhn_floor_refuses_without_fabricating_when_no_literature_value(monkeypatch):
    cls = {"dp_min": 42}
    dp, uncertainty = sss._kuhn_floor(_STIFF, literature_grounding=None,
                                      m_repeat_gmol=100.0, cls=cls)
    assert dp is None
    assert uncertainty["name"] == "KUHN_LENGTH_UNKNOWN"
    assert "42" in uncertainty["detail"]  # names the dp_min it will fall back to


def test_kuhn_floor_computes_dp_kuhn_from_a_grounded_value():
    lit = {"system_size": {"kuhn_molar_mass_gmol": 1500.0, "kuhn_length_A": 20.0}}
    dp, note = sss._kuhn_floor(_STIFF, lit, m_repeat_gmol=288.3, cls={"dp_min": 50})
    assert dp == 37
    assert "DP_Kuhn=37" in note
