"""The guardrails around the agents, end to end, against a mocked simulation backend.

What the LLM may do is bounded in code, not in its prompt. These tests pin the outer
boundaries that the per-module suites leave implicit:

  * a planning decision that fails validation gets exactly one retry, and two failures
    mean nothing is ever executed;
  * a recovery agent's `stop` ends the run after that one call;
  * a structurally invalid plan is refused by the real validator before the workflow
    engine is reached;
  * a resumed run must still clear the GPU-hour ceiling before execute.

Nothing here needs LAMMPS, EMC, RadonPy, a GPU or a model provider.
"""
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))

from scientific_control import (  # noqa: E402
    DeterministicScriptChain,
    PlanDecision,
    RecoveryDecision,
    ScientificControlPlane,
)
from test_scientific_control import (  # noqa: E402
    INTENT,
    SequenceWorkflow,
    SpyPlanningAgent,
    SpyRecoveryAgent,
    completed_outcome,
    failed_outcome,
)

_UNKNOWN_CLASS = PlanDecision(polymer_class="NOT_CONFIGURED", properties=("density",),
                              rationale=("Attempt an unsupported class.",))


class ScriptedPlanningAgent:
    """Returns the given decisions in order and records the context each call saw."""

    def __init__(self, *decisions):
        self.decisions = list(decisions)
        self.contexts = []

    def decide(self, intent, context):
        self.contexts.append(context)
        return self.decisions.pop(0)


# ─── planning: one retry, then refuse without executing ──────────────────────────────────

def test_an_invalid_plan_decision_is_retried_once_with_the_error_as_feedback(tmp_path):
    valid = SpyPlanningAgent().decide(INTENT, {"available_classes": {"PSTR": {}}})
    planning = ScriptedPlanningAgent(_UNKNOWN_CLASS, valid)
    workflow = SequenceWorkflow([completed_outcome()])

    result = ScientificControlPlane(planning, workflow, None, tmp_path).run(INTENT)

    assert result["status"] == "complete"
    assert len(planning.contexts) == 2
    assert "validation_feedback" not in planning.contexts[0]
    feedback = planning.contexts[1]["validation_feedback"]
    assert feedback["code"] == "PLAN_AGENT_CONTRACT_ERROR"
    assert "unknown polymer class" in feedback["error"]


def test_two_invalid_plan_decisions_stop_before_anything_executes(tmp_path):
    planning = ScriptedPlanningAgent(_UNKNOWN_CLASS, _UNKNOWN_CLASS)
    workflow = SequenceWorkflow([completed_outcome()])

    with pytest.raises(ValueError, match="PLAN_AGENT_CONTRACT_ERROR"):
        ScientificControlPlane(planning, workflow, SpyRecoveryAgent(), tmp_path).run(INTENT)

    assert workflow.calls == 0
    assert not (tmp_path / "data" / INTENT.run_name / "raw" / "run_plan.json").exists()


# ─── recovery: `stop` is final ───────────────────────────────────────────────────────────

def test_a_recovery_stop_ends_the_run_after_one_call(tmp_path):
    recovery = SpyRecoveryAgent(RecoveryDecision("stop", "Not recoverable by a retry."))
    workflow = SequenceWorkflow([failed_outcome(0), completed_outcome()])

    result = ScientificControlPlane(SpyPlanningAgent(), workflow, recovery, tmp_path).run(INTENT)

    assert result["status"] == "unresolved"
    assert result["recovery_agent_calls"] == 1
    assert recovery.calls == 1
    assert workflow.calls == 1  # the plan was never re-executed


# ─── validation: a structural finding never reaches the engine ───────────────────────────

def test_the_real_validator_refuses_a_structurally_invalid_plan(tmp_path, monkeypatch):
    plan = json.loads((REPO_ROOT / "examples" / "pstr_run_plan.json").read_text())
    del plan["planned_stages"][0]["track"]  # a required stage field
    plan_path = tmp_path / "run_plan.json"
    plan_path.write_text(json.dumps(plan))
    monkeypatch.setattr("run_campaign.run_campaign_workflow", lambda *a, **k: pytest.fail(
        "a plan with a structural finding reached the workflow engine"))

    outcome = DeterministicScriptChain(python=sys.executable).execute(plan_path)

    assert outcome.status == "issue"
    assert outcome.issue.code == "PLAN_VALIDATION_FAILED"
    assert [f["check"] for f in outcome.issue.detail["findings"]] == ["stage_schema"]
    assert [step["step"] for step in outcome.steps] == ["validate_run_plan"]


# ─── cost: a resumed run is priced again before execute ──────────────────────────────────

@pytest.fixture
def resumed_run(tmp_path):
    """data/R/ as a crash leaves it: an unfinished workflow and a priced plan."""
    raw = tmp_path / "data" / "R" / "raw"
    raw.mkdir(parents=True)
    (tmp_path / "data" / "R" / "workflow_state.json").write_text(
        json.dumps({"status": "running"}))
    (raw / "run_plan.json").write_text(json.dumps({
        "plan_mode": "reasoned", "polymer_class": "PSTR",
        "cost_estimate": {"total_gpu_hours": 41.0, "unpriced_stages": []},
    }))
    return tmp_path


def _resume(repo, monkeypatch, max_gpu_hours):
    pytest.importorskip("langgraph")
    sys.path.insert(0, str(REPO_ROOT / "orchestration" / "langgraph"))
    import nodes
    from graph import build_graph

    executed = []
    monkeypatch.setattr(nodes, "execute", lambda state: executed.append(state) or {
        "status": "accepted", "events": []})
    state = {"run_name": "R", "smiles": "*CC*", "goal": "g", "properties": ["density"],
             "repo_root": str(repo), "max_gpu_hours": max_gpu_hours, "events": []}
    return build_graph().invoke(state), executed


def test_a_resumed_run_over_the_ceiling_never_reaches_execute(resumed_run, monkeypatch):
    final, executed = _resume(resumed_run, monkeypatch, max_gpu_hours=40.0)

    assert final["status"] == "cost_exceeded"
    assert executed == []


def test_a_resumed_run_under_the_ceiling_does_reach_execute(resumed_run, monkeypatch):
    """The control for the test above: the stub is reachable, so its absence there means
    the guard stopped the run, not a broken fixture."""
    final, executed = _resume(resumed_run, monkeypatch, max_gpu_hours=50.0)

    assert len(executed) == 1
    assert final["status"] == "accepted"
