"""build_planned_stages' t_range_brackets_exp_tg must resolve per-member via the run's own
SMILES, and validate_run_plan's Check C must actually be reachable.

Member resolution (which class member a SMILES is) matches on the run's own SMILES
(canonicalized, stereo-stripped) against the class's member_smiles table, never run_name.
canon_smiles.canonicalize shells into a conda env, so it's monkeypatched to identity here;
local fixture classes carry placeholder member_smiles tokens (not real chemistry) so
matching stays deterministic without real RDKit.
"""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "orchestration" / "scripts"))

import canon_smiles  # noqa: E402
import hw_common  # noqa: E402
import stage_params  # noqa: E402
from make_deterministic_plan import build_planned_stages, make_plan  # noqa: E402
from validate_run_plan import _exp_tg_companion_findings  # noqa: E402

PHYC = {"experimental_tg_K": {"PE": 195, "PP": 258, "PIB": 205},
        "member_smiles": {"PE": ["PE_SMI"], "PP": ["PP_SMI"], "PIB": ["PIB_SMI"]}}
SINGLE_MEMBER = {"experimental_tg_K": 373}


@pytest.fixture(autouse=True)
def _clear_canon_cache():
    hw_common._canon_for_match.cache_clear()
    yield
    hw_common._canon_for_match.cache_clear()


@pytest.fixture(autouse=True)
def _identity_canonicalize(monkeypatch):
    monkeypatch.setattr(canon_smiles, "canonicalize", lambda smi, *a, **k: smi)


def _tg_stage(stages):
    return next(s for s in stages if s["stage"] == "tg")


def test_smiles_resolves_the_correct_member():
    stages = build_planned_stages(PHYC, {"tg"}, smiles="PE_SMI")
    assert _tg_stage(stages)["success_criteria"]["t_range_brackets_exp_tg"] == 195

    stages = build_planned_stages(PHYC, {"tg"}, smiles="PP_SMI")
    assert _tg_stage(stages)["success_criteria"]["t_range_brackets_exp_tg"] == 258


def test_no_smiles_or_unmatched_smiles_stays_unresolved():
    """_exp_tg_point no longer borrows another class member's measured value when the
    SMILES doesn't resolve -- that used to silently substitute an unrelated polymer's real
    experimental Tg. Absent a smiles to estimate from, the bracket stays genuinely
    unresolved (None), which Check C flags."""
    stages = build_planned_stages(PHYC, {"tg"})
    assert _tg_stage(stages)["success_criteria"]["t_range_brackets_exp_tg"] is None

    stages = build_planned_stages(PHYC, {"tg"}, smiles="NOT_A_MEMBER")
    assert _tg_stage(stages)["success_criteria"]["t_range_brackets_exp_tg"] is None


def test_unmatched_smiles_uses_group_contribution_estimate_when_smiles_given(monkeypatch):
    """No sibling member's value is borrowed; instead a SMILES-derived estimate for THIS
    molecule is used. _estimate_tg_group_contribution shells into the radonpy conda env
    (RDKit isn't in `base`) so it's monkeypatched here rather than actually invoked."""
    monkeypatch.setattr(stage_params, "_estimate_tg_group_contribution",
                         lambda smiles, timeout=30: {"tg_estimated_K": 342, "confidence": "low",
                                                       "motifs_matched": ["phenylene"]})
    stages = build_planned_stages(PHYC, {"tg"}, smiles="NOT_A_MEMBER")
    assert _tg_stage(stages)["success_criteria"]["t_range_brackets_exp_tg"] == 342


def test_unmatched_smiles_with_failed_estimate_stays_none(monkeypatch):
    """The estimator itself is advisory-only and may fail (bad SMILES, no rdkit, timeout) --
    that must degrade to None, never raise and never fall back to a sibling member's value."""
    monkeypatch.setattr(stage_params, "_estimate_tg_group_contribution",
                         lambda smiles, timeout=30: None)
    stages = build_planned_stages(PHYC, {"tg"}, smiles="not a smiles")
    assert _tg_stage(stages)["success_criteria"]["t_range_brackets_exp_tg"] is None


def test_class_with_no_experimental_tg_key_uses_group_contribution_estimate(monkeypatch):
    """The actual 'novel run' case: a class/SMILES with NO experimental_tg_K field at all
    (not a dict, not a scalar -- genuinely never characterized), not just a multi-member dict
    with an unmatched SMILES. Must also reach the estimator, not just return None."""
    monkeypatch.setattr(stage_params, "_estimate_tg_group_contribution",
                         lambda smiles, timeout=30: {"tg_estimated_K": 250, "confidence": "low",
                                                       "motifs_matched": ["backbone_CH2"]})
    stages = build_planned_stages({}, {"tg"}, smiles="*CC*")
    assert _tg_stage(stages)["success_criteria"]["t_range_brackets_exp_tg"] == 250


def test_scalar_experimental_tg_k_override_wins_outright():
    """overrides.experimental_tg_K (OVERRIDE_RANGES) replaces the class's experimental_tg_K
    wholesale via apply_plan's {**cls, **decided_params}, landing here as a plain scalar --
    must win immediately, without touching member matching or the estimator at all."""
    stages = build_planned_stages({"experimental_tg_K": 373.0}, {"tg"},
                                   smiles="*CC(c1ccccc1)*")
    assert _tg_stage(stages)["success_criteria"]["t_range_brackets_exp_tg"] == 373.0


def test_class_with_no_experimental_tg_at_all_stays_unresolved():
    stages = build_planned_stages({}, {"tg"})
    assert _tg_stage(stages)["success_criteria"]["t_range_brackets_exp_tg"] is None


def test_single_member_class_unaffected():
    stages = build_planned_stages(SINGLE_MEMBER, {"tg"})
    assert _tg_stage(stages)["success_criteria"]["t_range_brackets_exp_tg"] == 373


def test_check_c_fires_when_class_has_no_experimental_tg_at_all():
    plan = {"planned_stages": build_planned_stages({}, {"tg"})}
    findings = _exp_tg_companion_findings(plan)
    assert len(findings) == 1
    assert findings[0]["check"] == "exp_tg_companion"


def test_check_c_silent_when_resolved():
    plan = {"planned_stages": build_planned_stages(PHYC, {"tg"}, smiles="PE_SMI")}
    assert _exp_tg_companion_findings(plan) == []


def test_check_c_never_fired_under_the_old_is_true_test():
    """Regression guard: the old check compared against a sentinel this field never holds."""
    plan = {"planned_stages": [{"stage": "tg", "success_criteria": {"t_range_brackets_exp_tg": None}}]}
    assert any(f["check"] == "exp_tg_companion" for f in _exp_tg_companion_findings(plan))


def test_make_plan_t_workflow_k_follows_group_contribution_estimate_when_confidently_rubbery(monkeypatch):
    """150K stays rubbery even after the +/-80K margin (150+80=230 < 300). Uses a smiles
    that matches none of real PHYC's curated members, so this genuinely exercises the
    estimate path rather than resolving PE's real (and also rubbery) Tg by coincidence."""
    monkeypatch.setattr(stage_params, "_estimate_tg_group_contribution",
                         lambda smiles, timeout=30: {"tg_estimated_K": 150, "confidence": "low",
                                                       "motifs_matched": ["backbone_CH2"]})
    plan = make_plan("UNKNOWN99", "PHYC", "UNKNOWN_TG_SMILES", {"density"})
    assert plan["decided_params"]["T_workflow_K"] == 300.0


def test_make_plan_t_workflow_k_defaults_glassy_when_estimate_is_uncertain(monkeypatch):
    """250K < 300 on its own, but +80K uncertainty could put it at 330K -- defaults glassy."""
    monkeypatch.setattr(stage_params, "_estimate_tg_group_contribution",
                         lambda smiles, timeout=30: {"tg_estimated_K": 250, "confidence": "low",
                                                       "motifs_matched": ["backbone_CH2"]})
    plan = make_plan("UNKNOWN99", "PHYC", "UNKNOWN_TG_SMILES", {"density"})
    assert plan["decided_params"]["T_workflow_K"] == plan["decided_params"]["T_equil_K"]


def test_make_plan_t_workflow_k_stays_glassy_default_when_estimate_above_300(monkeypatch):
    monkeypatch.setattr(stage_params, "_estimate_tg_group_contribution",
                         lambda smiles, timeout=30: {"tg_estimated_K": 350, "confidence": "low",
                                                       "motifs_matched": ["phenylene"]})
    plan = make_plan("UNKNOWN99", "PHYC", "UNKNOWN_TG_SMILES", {"density"})
    assert plan["decided_params"]["T_workflow_K"] == plan["decided_params"]["T_equil_K"]


def test_make_plan_t_workflow_k_matched_member_unaffected():
    """Curated member data is exact and unpadded, unlike an estimate. Real PHYC data:
    member_smiles["PE"] == "*CC*", resolved purely from the smiles argument -- run_name
    ("PE1") plays no role in the resolution at all."""
    plan = make_plan("PE1", "PHYC", "*CC*", {"density"})
    assert plan["decided_params"]["T_workflow_K"] == 300.0  # PE's exp Tg 195K < 300 -> rubbery


def test_glassy_hint_agrees_with_t_workflow_k_regime_for_curated_data():
    """Bracket (_exp_tg_point) and regime hint (_regime_exp_tg) differ only for an estimate;
    for curated data both must still agree."""
    stages = build_planned_stages(
        {"experimental_tg_K": {"PE": 195}, "member_smiles": {"PE": ["PE_TOKEN"]}},
        {"bulk_modulus"}, smiles="PE_TOKEN")
    murnaghan = next(s for s in stages if s["stage"] == "murnaghan")
    assert "fallback" not in murnaghan  # rubbery: no deform fallback annotation

    stages = build_planned_stages(
        {"experimental_tg_K": {"PS": 373}, "member_smiles": {"PS": ["PS_TOKEN"]}},
        {"bulk_modulus"}, smiles="PS_TOKEN")
    murnaghan = next(s for s in stages if s["stage"] == "murnaghan")
    assert murnaghan.get("fallback") == "deform"  # glassy: deform fallback present


def test_glassy_hint_defaults_glassy_when_estimate_is_uncertain(monkeypatch):
    """Same borderline estimate as the T_workflow_K test, applied to the murnaghan hint."""
    monkeypatch.setattr(stage_params, "_estimate_tg_group_contribution",
                         lambda smiles, timeout=30: {"tg_estimated_K": 250, "confidence": "low",
                                                       "motifs_matched": ["backbone_CH2"]})
    stages = build_planned_stages({}, {"bulk_modulus"}, smiles="*CC*")
    murnaghan = next(s for s in stages if s["stage"] == "murnaghan")
    assert murnaghan.get("fallback") == "deform"  # glassy: uncertain estimate defaults glassy
