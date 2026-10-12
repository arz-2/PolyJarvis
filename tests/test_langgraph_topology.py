"""The graph's SHAPE — which is the thing most likely to be wrong in an unattended driver.

Two structural properties are asserted here, and both cost real GPU time if they break:

  execute runs at most once.  It is tempting to loop execute -> recover -> execute. It
      would be wrong. agent_escalations is a RUN-GLOBAL list in workflow_state.json and
      WorkflowEngine._escalate returns early once it hits MAX_AGENT_DECISIONS, so by the
      time run() returns `escalation_required` both agent calls are spent. Re-entering
      would re-execute the failing stage -- real hardware -- and escalate-fail again against
      the same exhausted cap.

  every path into execute passes the cost guard.  A resumed run enters at `execute`, and
      routing it there directly silently disarms --max-gpu-hours on every invocation after
      the first. That was a real bug, caught by running the thing; this is its regression.
"""
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "langgraph"))
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))

pytest.importorskip("langgraph", reason="langgraph not installed in this interpreter")

import nodes  # noqa: E402
from graph import build_graph  # noqa: E402


@pytest.fixture(scope="module")
def compiled():
    return build_graph().get_graph()


def test_graph_is_acyclic(compiled):
    """A DAG, not a loop. See the module docstring for why a retry loop here burns GPUs."""
    adjacency: dict[str, set[str]] = {}
    for edge in compiled.edges:
        adjacency.setdefault(edge.source, set()).add(edge.target)

    visiting, done = set(), set()

    def walk(node: str, trail: list[str]) -> None:
        if node in visiting:
            raise AssertionError(f"cycle: {' -> '.join(trail + [node])}")
        if node in done:
            return
        visiting.add(node)
        for nxt in adjacency.get(node, ()):
            walk(nxt, trail + [node])
        visiting.discard(node)
        done.add(node)

    walk("__start__", [])


def test_execute_is_never_reachable_from_itself(compiled):
    outgoing = {e.target for e in compiled.edges if e.source == "execute"}
    assert outgoing <= {"__end__"}, f"execute must terminate, not continue to {outgoing}"


def test_every_edge_into_execute_comes_through_the_cost_guard(compiled):
    """--max-gpu-hours must bind on the resume path too, not only on a first run."""
    sources = {e.source for e in compiled.edges if e.target == "execute"}
    assert sources == {"cost_guard_post"}, (
        f"execute is reachable from {sources}; every path in must clear the cost ceiling"
    )


def test_entry_resolve_can_reach_every_restartable_stage(compiled):
    targets = {e.target for e in compiled.edges if e.source == "entry_resolve"}
    assert {"cache_probe", "classify", "critique", "adjudicate", "materialize"} <= targets
    # ...and its execute branch is the guarded one.
    assert "cost_guard_post" in targets and "execute" not in targets


def _state(tmp_path, **over):
    base = {"run_name": "R", "smiles": "*CC*", "goal": "g", "properties": ["density"],
            "repo_root": str(tmp_path), "events": []}
    base.update(over)
    return base


def _write(tmp_path, rel, payload):
    path = tmp_path / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))
    return path


def test_entry_resolve_starts_from_scratch_when_nothing_exists(tmp_path):
    assert nodes.entry_resolve(_state(tmp_path))["entry_node"] == "cache_probe"


def test_entry_resolve_resumes_execution_when_a_campaign_is_already_underway(tmp_path):
    _write(tmp_path, "data/R/workflow_state.json", {"status": "escalation_required"})
    assert nodes.entry_resolve(_state(tmp_path))["entry_node"] == "execute"


def test_entry_resolve_sends_an_unsigned_plan_to_the_critic(tmp_path):
    _write(tmp_path, "data/R/raw/run_plan.json", {"confidence": "unreviewed"})
    assert nodes.entry_resolve(_state(tmp_path))["entry_node"] == "critique"


def test_entry_resolve_skips_the_critic_when_grounding_already_exists(tmp_path):
    _write(tmp_path, "data/R/raw/run_plan.json", {"confidence": "unreviewed"})
    _write(tmp_path, "data/R/raw/literature_grounding.json", {"md_studies": []})
    assert nodes.entry_resolve(_state(tmp_path))["entry_node"] == "adjudicate"


def test_entry_resolve_materializes_a_signed_but_unmaterialized_plan(tmp_path):
    """plan_mode is the discriminator, NOT system_size.resolved_by.

    run-plan already sets resolved_by on a scaffold, so testing that would send a
    never-materialized plan straight to execute -- with no resolved stage parameters.
    """
    _write(tmp_path, "data/R/raw/run_plan.json", {
        "confidence": "low", "plan_mode": "scaffold",
        "system_size": {"resolved_by": "select_system_size.solve_system_size"}})
    assert nodes.entry_resolve(_state(tmp_path))["entry_node"] == "materialize"


@pytest.mark.parametrize("plan_mode", ["reasoned", "deterministic"])
def test_entry_resolve_executes_a_materialized_plan(tmp_path, plan_mode):
    _write(tmp_path, "data/R/raw/run_plan.json",
           {"confidence": "medium", "plan_mode": plan_mode, "polymer_class": "PHYC"})
    result = nodes.entry_resolve(_state(tmp_path))
    assert result["entry_node"] == "execute"
    # The plan must travel with it, or the cost guard has nothing to price.
    assert result["plan_path"].endswith("run_plan.json")
    assert result["polymer_class"] == "PHYC"


def test_entry_resolve_replans_rather_than_crashing_on_a_corrupt_plan(tmp_path):
    path = tmp_path / "data/R/raw/run_plan.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json")
    assert nodes.entry_resolve(_state(tmp_path))["entry_node"] == "cache_probe"


def test_an_accepted_campaign_does_not_resume_into_execute(tmp_path):
    """A finished run must fall through to the plan-state checks, not re-enter execution."""
    _write(tmp_path, "data/R/workflow_state.json", {"status": "accepted"})
    _write(tmp_path, "data/R/raw/run_plan.json", {"confidence": "high", "plan_mode": "reasoned"})
    assert nodes.entry_resolve(_state(tmp_path))["entry_node"] == "execute"
