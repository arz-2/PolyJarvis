"""build_planned_stages' t_range_brackets_exp_tg must resolve per-member via run_name, and
validate_run_plan's Check C must actually be reachable.

Previously _exp_tg_bracket(cls) always returned None for ANY multi-member experimental_tg_K
dict (no run_name parameter existed to resolve it), and validate_run_plan's companion check
tested `is True` against a field that only ever holds a number or None -- so it could never
fire for any plan, single- or multi-member. Both are fixed: the field now reuses
stage_params._exp_tg_point's proven run_name-member resolver (the same one that correctly
grades PE1's runtime Tg target), and Check C now flags a genuinely-unresolved (None) bracket.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "orchestration" / "scripts"))

import stage_params  # noqa: E402
from make_deterministic_plan import build_planned_stages  # noqa: E402
from validate_run_plan import _exp_tg_companion_findings  # noqa: E402

PHYC = {"experimental_tg_K": {"PE": 195, "PP": 258, "PIB": 205}}
SINGLE_MEMBER = {"experimental_tg_K": 373}


def _tg_stage(stages):
    return next(s for s in stages if s["stage"] == "tg")


def test_run_name_resolves_the_correct_member():
    stages = build_planned_stages(PHYC, {"tg"}, run_name="PE1")
    assert _tg_stage(stages)["success_criteria"]["t_range_brackets_exp_tg"] == 195

    stages = build_planned_stages(PHYC, {"tg"}, run_name="PP3")
    assert _tg_stage(stages)["success_criteria"]["t_range_brackets_exp_tg"] == 258


def test_no_run_name_or_unmatched_run_name_stays_unresolved_without_smiles():
    """_exp_tg_point no longer borrows another class member's measured value when run_name
    doesn't resolve -- that used to silently substitute an unrelated polymer's real
    experimental Tg (e.g. run_name='a-PS' against PSTR's {PS:373, P2VP:374} inherited P2VP's
    374K, because the 'a-' prefix breaks the 'PS' startswith match). Absent a smiles to
    estimate from, the bracket now stays genuinely unresolved (None), which Check C flags."""
    stages = build_planned_stages(PHYC, {"tg"})
    assert _tg_stage(stages)["success_criteria"]["t_range_brackets_exp_tg"] is None

    stages = build_planned_stages(PHYC, {"tg"}, run_name="UNKNOWN99")
    assert _tg_stage(stages)["success_criteria"]["t_range_brackets_exp_tg"] is None


def test_unmatched_run_name_uses_group_contribution_estimate_when_smiles_given(monkeypatch):
    """No sibling member's value is borrowed; instead a SMILES-derived estimate for THIS
    molecule is used. _estimate_tg_group_contribution shells into the radonpy conda env
    (RDKit isn't in `base`) so it's monkeypatched here rather than actually invoked."""
    monkeypatch.setattr(stage_params, "_estimate_tg_group_contribution",
                         lambda smiles, timeout=30: {"tg_estimated_K": 342, "confidence": "low",
                                                       "motifs_matched": ["phenylene"]})
    stages = build_planned_stages(PHYC, {"tg"}, run_name="UNKNOWN99", smiles="*CC*")
    assert _tg_stage(stages)["success_criteria"]["t_range_brackets_exp_tg"] == 342


def test_unmatched_run_name_with_smiles_but_failed_estimate_stays_none(monkeypatch):
    """The estimator itself is advisory-only and may fail (bad SMILES, no rdkit, timeout) --
    that must degrade to None, never raise and never fall back to a sibling member's value."""
    monkeypatch.setattr(stage_params, "_estimate_tg_group_contribution",
                         lambda smiles, timeout=30: None)
    stages = build_planned_stages(PHYC, {"tg"}, run_name="UNKNOWN99", smiles="not a smiles")
    assert _tg_stage(stages)["success_criteria"]["t_range_brackets_exp_tg"] is None


def test_class_with_no_experimental_tg_key_uses_group_contribution_estimate(monkeypatch):
    """The actual 'novel run' case: a class/SMILES with NO experimental_tg_K field at all
    (not a dict, not a scalar -- genuinely never characterized), not just a multi-member dict
    with an unmatched run_name. Must also reach the estimator, not just return None."""
    monkeypatch.setattr(stage_params, "_estimate_tg_group_contribution",
                         lambda smiles, timeout=30: {"tg_estimated_K": 250, "confidence": "low",
                                                       "motifs_matched": ["backbone_CH2"]})
    stages = build_planned_stages({}, {"tg"}, run_name="X1", smiles="*CC*")
    assert _tg_stage(stages)["success_criteria"]["t_range_brackets_exp_tg"] == 250


def test_scalar_experimental_tg_k_override_wins_outright():
    """overrides.experimental_tg_K (OVERRIDE_RANGES) replaces the class's experimental_tg_K
    wholesale via apply_plan's {**cls, **decided_params}, landing here as a plain scalar --
    must win immediately, without touching run_name matching or the estimator at all."""
    stages = build_planned_stages({"experimental_tg_K": 373.0}, {"tg"}, run_name="a-PS",
                                   smiles="*CC(c1ccccc1)*")
    assert _tg_stage(stages)["success_criteria"]["t_range_brackets_exp_tg"] == 373.0


def test_class_with_no_experimental_tg_at_all_stays_unresolved():
    stages = build_planned_stages({}, {"tg"}, run_name="X1")
    assert _tg_stage(stages)["success_criteria"]["t_range_brackets_exp_tg"] is None


def test_single_member_class_unaffected():
    stages = build_planned_stages(SINGLE_MEMBER, {"tg"}, run_name="PC1")
    assert _tg_stage(stages)["success_criteria"]["t_range_brackets_exp_tg"] == 373


def test_check_c_fires_when_class_has_no_experimental_tg_at_all():
    plan = {"planned_stages": build_planned_stages({}, {"tg"}, run_name="X1")}
    findings = _exp_tg_companion_findings(plan)
    assert len(findings) == 1
    assert findings[0]["check"] == "exp_tg_companion"


def test_check_c_silent_when_resolved():
    plan = {"planned_stages": build_planned_stages(PHYC, {"tg"}, run_name="PE1")}
    assert _exp_tg_companion_findings(plan) == []


def test_check_c_never_fired_under_the_old_is_true_test():
    """Regression guard: the old check compared against a sentinel this field never holds."""
    plan = {"planned_stages": [{"stage": "tg", "success_criteria": {"t_range_brackets_exp_tg": None}}]}
    assert any(f["check"] == "exp_tg_companion" for f in _exp_tg_companion_findings(plan))
