"""D-04_system_size selection: property-scoped DP floors, and the member-generalization
bug this file locks against.

Two things easy to quietly regress:
  - a class default already above its documented floor must never be silently shrunk --
    that would invalidate an already-protocol_validated SMILES without ever consulting
    the reproducibility carve-out. Downward gaps are reported, never overridden.
  - entanglement Me is documented for ONE member of a multi-member class, not the class.
    Applying PMMA's Me to PAA (both PACR) would repeat the bug this codebase already
    found and fixed once for experimental density (stage_params.py:217-223, PE1 vs PP).
"""
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))

import select_system_size as sss  # noqa: E402
from select_system_size import select_system_size, _fox_flory_floor  # noqa: E402
from validate_run_plan import _system_size_findings  # noqa: E402

PACR_SMILES = "*CC(C)(C(=O)OC)*"
PHYC_SMILES = "*CC*"
PKTN_SMILES = "*c1ccc(Oc2ccc(C(=O)c3ccc(O*)cc3)cc2)cc1"
PCBN_SMILES = "*Oc1ccc(C(C)(C)c2ccc(OC(=O)*)cc2)cc1"


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
    monkeypatch.setattr(sss, "_monomer_atoms_and_mw", lambda smiles, is_ua: (15, 100.12))
    result = select_system_size("PACR", PACR_SMILES, properties=["bulk_modulus"],
                                run_name="PMMA1")
    assert result["decided_params_override"] == {"dp_typical": 125}
    assert result["decision"]["required_dp_floor"] == 125


def test_entanglement_floor_refuses_an_unmatched_sibling_member(monkeypatch):
    """PACR documents Me for PMMA only. A PAA run must NOT inherit PMMA's floor --
    regression test for the member-generalization bug (see module docstring)."""
    monkeypatch.setattr(sss, "_monomer_atoms_and_mw",
                        lambda *a, **k: pytest.fail("must not reach RDKit for an unmatched member"))
    result = select_system_size("PACR", PACR_SMILES, properties=["bulk_modulus"],
                                run_name="PAA1")
    assert result["decided_params_override"] == {}
    assert result["decision"]["required_dp_floor"] is None
    unc = next(u for u in result["uncertainties"] if u["name"] == "MW_FLOOR_UNKNOWN")
    assert "PMMA" in unc["detail"]


def test_entanglement_floor_refuses_without_a_run_name_for_a_multimember_class():
    result = select_system_size("PACR", PACR_SMILES, properties=["bulk_modulus"],
                                run_name=None)
    assert result["decided_params_override"] == {}
    assert any(u["name"] == "MW_FLOOR_UNKNOWN" for u in result["uncertainties"])


def test_undocumented_class_bulk_modulus_is_mw_floor_unknown():
    result = select_system_size("PHYC", PHYC_SMILES, properties=["bulk_modulus"])
    assert result["decided_params_override"] == {}
    assert any(u["name"] == "MW_FLOOR_UNKNOWN" for u in result["uncertainties"])


def test_single_member_class_resolves_without_a_run_name(monkeypatch):
    """PCBN has exactly one member (BPA_PC) -- no sibling to confuse it with, so it
    resolves unconditionally, mirroring validate_run_plan.py:_target_density's
    single-member-dict exception."""
    monkeypatch.setattr(sss, "_monomer_atoms_and_mw", lambda smiles, is_ua: (22, 254.0))
    result = select_system_size("PCBN", PCBN_SMILES, properties=["bulk_modulus"],
                                run_name=None)
    assert result["decision"]["required_dp_floor"] is not None
    assert not any(u["name"] == "MW_FLOOR_UNKNOWN" for u in result["uncertainties"])


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


# --- validator: floor violation must be raised or acknowledged, never silent -------

def _plan(**kw):
    d = {"id": "D-04_system_size", "required_dp_floor": kw.get("floor", 50),
         "floor_sources": []}
    return {"decisions": [d], "decided_params": {"dp_typical": kw.get("dp", 32)},
            "uncertainties": kw.get("uncertainties", [])}


def test_floor_violation_unacknowledged_is_structural():
    f = _system_size_findings(_plan(dp=32, floor=50))
    assert [x["check"] for x in f] == ["system_size_dp_floor_unacknowledged"]
    assert f[0]["severity"] == "structural"


def test_floor_violation_acknowledged_clears():
    f = _system_size_findings(_plan(dp=32, floor=50,
                                    uncertainties=[{"name": "system_size_dp_floor"}]))
    assert f == []


def test_floor_satisfied_no_finding():
    f = _system_size_findings(_plan(dp=50, floor=50))
    assert f == []


def test_plan_without_a_d04_row_is_unaffected():
    assert _system_size_findings({"decisions": [{"id": "D-08_hardware"}]}) == []


def test_plan_without_a_measured_floor_is_unaffected():
    """required_dp_floor absent (e.g. density-only run) -- nothing to check."""
    plan = {"decisions": [{"id": "D-04_system_size", "required_dp_floor": None}],
            "decided_params": {"dp_typical": 5}, "uncertainties": []}
    assert _system_size_findings(plan) == []
