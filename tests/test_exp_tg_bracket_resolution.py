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


def test_no_run_name_or_unmatched_run_name_falls_back_to_median_not_none():
    """_exp_tg_point's own convention (already proven for the real runtime grading path):
    an absent or unmatched run_name falls back to the class median rather than staying
    unresolved -- every real call site always supplies a run_name in practice, so this
    fallback is a defensive last resort, not the common case."""
    stages = build_planned_stages(PHYC, {"tg"})
    assert _tg_stage(stages)["success_criteria"]["t_range_brackets_exp_tg"] == 205  # median

    stages = build_planned_stages(PHYC, {"tg"}, run_name="UNKNOWN99")
    assert _tg_stage(stages)["success_criteria"]["t_range_brackets_exp_tg"] == 205  # median


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
