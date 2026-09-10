"""--no-llm must be LLM-free end to end, not just at planning time.

The deterministic arm exists to measure the LLM's incremental contribution (reviewer
comment 3). Until 2026-09-09 `nodes.execute` passed --recovery-agent-command
unconditionally: `no_llm` reached critique() and adjudicate() but never workflow_engine,
scientific_control or agent_api, so the "LLM-free" arm still consulted a model up to
MAX_AGENT_DECISIONS=2 times on any escalation. An ablation measured that way understates
the LLM's contribution by exactly the amount the recovery agent supplied.

These tests are the enforcement. They run no model and claim no GPU: `execute` is driven
with a stubbed `_run`, and the assertion is on the argv it builds.
"""
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "langgraph"))
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))

import nodes  # noqa: E402


class _Result:
    returncode = 0
    stdout = '{"status": "accepted"}'
    stderr = ""


@pytest.fixture
def captured(monkeypatch):
    """Run execute() against a stubbed subprocess and hand back the argv it built."""
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = [str(part) for part in cmd]
        return _Result()

    monkeypatch.setattr(nodes, "_run", fake_run)
    return seen


def _state(tmp_path, **extra):
    return {"run_name": "R", "goal": "g", "smiles": "*CC*", "properties": ["density"],
            "plan_path": str(tmp_path / "run_plan.json"), "repo_root": str(tmp_path),
            **extra}


@pytest.mark.parametrize("resuming", [False, True])
def test_no_llm_passes_no_recovery_agent_command(tmp_path, captured, resuming):
    if resuming:
        (tmp_path / "data" / "R").mkdir(parents=True)
        (tmp_path / "data" / "R" / "workflow_state.json").write_text("{}")
    nodes.execute(_state(tmp_path, no_llm=True))
    assert "--recovery-agent-command" not in captured["cmd"], (
        "the deterministic arm must not hand WorkflowEngine a recovery agent -- with one, "
        "escalations still consult a model and the arm is not a baseline")
    assert "recovery_agent_cli.py" not in " ".join(captured["cmd"])


@pytest.mark.parametrize("resuming", [False, True])
def test_llm_arm_still_gets_the_recovery_agent(tmp_path, captured, resuming):
    """The ablation needs BOTH arms intact: suppressing recovery everywhere would measure
    nothing at all."""
    if resuming:
        (tmp_path / "data" / "R").mkdir(parents=True)
        (tmp_path / "data" / "R" / "workflow_state.json").write_text("{}")
    nodes.execute(_state(tmp_path))
    assert "--recovery-agent-command" in captured["cmd"]
    command = captured["cmd"][captured["cmd"].index("--recovery-agent-command") + 1]
    assert command.endswith("recovery_agent_cli.py")


def test_engine_halts_rather_than_calling_out_when_no_agent_is_configured():
    """The other half of the contract: with no agent, escalation is terminal and says why.

    Asserted against the engine's own source rather than a live escalation, which would need
    a GPU -- the point is that the None branch exists and is distinguishable in the record
    from a spent cap, so the harvest can tell 'the arm had no agent' from 'the agent ran out'.
    """
    source = (REPO_ROOT / "orchestration" / "scripts" / "workflow_engine.py").read_text()
    assert "no_recovery_agent_configured" in source
    assert "max_agent_decisions_reached" in source
