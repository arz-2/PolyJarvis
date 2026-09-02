"""Validates the metrics extractors against real, already-completed run directories
(data/PE1, data/PP, data/a-PS) rather than synthetic fixtures -- every field asserted
here was read directly off the live JSON on this checkout before being encoded.
"""
from pathlib import Path

import pytest

from benchmarks.polyjarvis_vs_radonpy.metrics.llm_contribution import extract_llm_contribution
from benchmarks.polyjarvis_vs_radonpy.metrics.adaptive_gating import extract_adaptive_gating
from benchmarks.polyjarvis_vs_radonpy.metrics.accuracy import extract_polyjarvis_accuracy
from benchmarks.polyjarvis_vs_radonpy.metrics.wall_time import extract_polyjarvis_wall_time

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DATA = REPO_ROOT / "data"

pytestmark = pytest.mark.skipif(
    not (DATA / "PE1").is_dir(), reason="requires data/PE1 fixture on this checkout"
)


def test_llm_contribution_pe1_clean_pass():
    block = extract_llm_contribution(DATA / "PE1")
    assert block.plan_mode == "reasoned"
    assert block.llm_authored_decisions_total == 4  # D-01..D-04 on PE1's decision.json vintage
    assert block.note == ""


def test_llm_contribution_pp_awaiting_recovery():
    block = extract_llm_contribution(DATA / "PP")
    assert block.plan_mode == "reasoned"
    assert block.llm_authored_decisions_total == 4


def test_adaptive_gating_pe1_deterministic_remedy_only():
    block = extract_adaptive_gating(DATA / "PE1")
    assert block.recovery_agent_calls == 0
    assert block.auto_remedy_total == 1  # tg_sampling, per remedy_counters.total
    assert block.escalation_total == 0
    assert block.cap_hit is False
    # thermal's attempt-0001 was remedy_required -> first-attempt pass is False campaign-wide
    assert block.first_attempt_pass is False
    # every stage ultimately shows status == "accepted"
    assert block.final_pass is True


def test_adaptive_gating_pp_awaiting_first_recovery_call():
    block = extract_adaptive_gating(DATA / "PP")
    assert block.recovery_agent_calls == 0
    assert block.auto_remedy_total == 2  # transient_retry x2, per remedy_counters.total
    assert block.escalation_total == 0
    assert block.cap_hit is False
    assert block.first_attempt_pass is False  # equilibration's attempt-0001 failed
    assert block.final_pass is False  # equilibration still "running", others "pending"


def test_adaptive_gating_a_ps_cap_hit_via_stale_control_state():
    block = extract_adaptive_gating(DATA / "a-PS")
    # control_state.json.recovery_agent_calls is stale (0) on this resumed run; the real
    # count comes from workflow_state.json.agent_escalations (2: one revise_plan, one stop).
    assert block.escalation_total == 2
    assert block.recovery_agent_calls == 2
    assert block.auto_remedy_total == 2
    assert block.final_pass is False  # equilibration stage status == "failed"
    assert block.cap_hit is True


def test_accuracy_pe1_reports_murnaghan_method():
    block = extract_polyjarvis_accuracy(DATA / "PE1")
    assert block.density_g_cm3 is not None
    assert block.bulk_modulus_method == "murnaghan"
    assert "murnaghan" in block.method_note.lower()


def test_wall_time_pe1_orchestration_span_is_positive():
    block = extract_polyjarvis_wall_time(DATA / "PE1")
    # PE1 ran from 2026-08-17T04:33 to 2026-08-17T23:06 per workflow_state.json
    assert block.orchestration_wall_time_s is not None
    assert block.orchestration_wall_time_s > 3600 * 10  # sanity: this campaign took hours
