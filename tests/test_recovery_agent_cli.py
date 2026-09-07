import json
import sys
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))

import recovery_agent_cli as rac  # noqa: E402


MODIFICATION_CONTRACT = {"nchain": {"type": "integer", "minimum": 1, "maximum": 500}}

OUTER_PAYLOAD = {
    "task": "diagnose_polymer_simulation_issue",
    "intent": {"run_name": "PP", "goal": "test"},
    "plan_summary": {"run_name": "PP", "polymer_class": "PHYC", "recovery_history": []},
    "issue": {"stage": "equilibration", "code": "PROCESS_FAILED",
              "detail": {"error": "boom"}, "attempt": 0},
    "output_contract": {"action": ["retry", "revise_plan", "stop"], "rationale": "...",
                         "modifications": MODIFICATION_CONTRACT},
}

INNER_PAYLOAD = {
    "task": "diagnose_polymer_simulation_issue",
    "intent": {"run_name": "PP", "goal": "test"},
    "plan_summary": {"run_name": "PP", "polymer_class": "PHYC"},
    "issue": {"code": "PROCESS_FAILED", "stage": "equilibration", "severity": "blocking",
              "confidence": "high", "details": {"error": "boom"}, "remedy_id": None},
    "output_contract": {"action": ["retry", "revise_plan", "stop"], "rationale": "...",
                         "modifications": MODIFICATION_CONTRACT},
}


def test_trim_payload_handles_outer_shape():
    trimmed = rac._trim_payload(OUTER_PAYLOAD)
    assert trimmed["stage"] == "equilibration"
    assert trimmed["code"] == "PROCESS_FAILED"
    assert trimmed["detail"] == {"error": "boom"}
    assert "recovery_history" not in trimmed  # empty list dropped
    assert trimmed["valid_actions"] == ["retry", "revise_plan", "stop"]
    assert trimmed["modification_contract"] == MODIFICATION_CONTRACT


def test_trim_payload_handles_inner_finding_shape():
    trimmed = rac._trim_payload(INNER_PAYLOAD)
    assert trimmed["stage"] == "equilibration"
    assert trimmed["code"] == "PROCESS_FAILED"
    assert trimmed["detail"] == {"error": "boom"}
    assert trimmed["severity"] == "blocking"
    assert trimmed["valid_actions"] == ["retry", "revise_plan", "stop"]
    assert trimmed["modification_contract"] == MODIFICATION_CONTRACT


def test_diagnose_passes_through_revise_plan_with_modifications():
    with patch.object(rac, "_run_headless_claude", return_value={
        "action": "revise_plan", "modifications": {"nchain": 320},
        "rationale": "finite-size violation, rebuilding larger",
    }):
        decision = rac.diagnose(OUTER_PAYLOAD)
    assert decision["action"] == "revise_plan"
    assert decision["modifications"] == {"nchain": 320}
    assert "finite-size violation" in decision["rationale"]


def test_diagnose_passes_through_retry():
    with patch.object(rac, "_run_headless_claude", return_value={
        "action": "retry", "modifications": {},
        "rationale": "stale orphan process confirmed killed",
    }):
        decision = rac.diagnose(OUTER_PAYLOAD)
    assert decision["action"] == "retry"
    assert decision["modifications"] == {}
    assert "stale orphan" in decision["rationale"]


def test_diagnose_stop_still_works():
    with patch.object(rac, "_run_headless_claude", return_value={
        "action": "stop", "modifications": {},
        "rationale": "novel failure mode, needs human review",
    }):
        decision = rac.diagnose(OUTER_PAYLOAD)
    assert decision["action"] == "stop"
    assert decision["modifications"] == {}
    assert "novel failure mode" in decision["rationale"]


def test_diagnose_zeroes_modifications_when_action_not_revise_plan():
    with patch.object(rac, "_run_headless_claude", return_value={
        "action": "retry", "modifications": {"nchain": 320},
        "rationale": "misbehaving model sent modifications with retry",
    }):
        decision = rac.diagnose(OUTER_PAYLOAD)
    assert decision["action"] == "retry"
    assert decision["modifications"] == {}


def test_diagnose_falls_back_to_stop_on_invalid_action():
    with patch.object(rac, "_run_headless_claude", return_value={
        "action": "do_something_unlisted", "modifications": {"nchain": 320},
        "rationale": "model invented an action",
    }):
        decision = rac.diagnose(OUTER_PAYLOAD)
    assert decision["action"] == "stop"
    assert decision["modifications"] == {}


def test_run_headless_claude_retries_once_then_succeeds():
    calls = {"n": 0}

    def flaky(prompt, schema, timeout_s):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("aborted_streaming")
        return {"action": "stop", "modifications": {}, "rationale": "x"}

    with patch.object(rac, "_run_headless_claude_once", side_effect=flaky):
        result = rac._run_headless_claude("prompt", rac._output_schema(rac.DEFAULT_ACTIONS), retries=1)
    assert calls["n"] == 2
    assert result["action"] == "stop"


def test_run_headless_claude_gives_up_after_retries_exhausted():
    with patch.object(rac, "_run_headless_claude_once",
                       side_effect=RuntimeError("aborted_streaming")):
        try:
            rac._run_headless_claude("prompt", rac._output_schema(rac.DEFAULT_ACTIONS), retries=1)
            assert False, "expected RuntimeError"
        except RuntimeError as exc:
            assert "aborted_streaming" in str(exc)


def test_diagnose_retries_stage_on_headless_invocation_failure():
    """A crashed/timed-out headless call carries no diagnosis -- it must not be conflated
    with an agent's considered `stop`. It should ask the caller to retry the stage
    instead, bounded by the caller's own MAX_AGENT_DECISIONS/MAX_RECOVERY_ATTEMPTS caps."""
    with patch.object(rac, "_run_headless_claude", side_effect=RuntimeError("timed out")):
        decision = rac.diagnose(OUTER_PAYLOAD)
    assert decision["action"] == "retry"
    assert decision["modifications"] == {}
    assert "invocation failed" in decision["rationale"]
    assert "timed out" in decision["rationale"]


def test_diagnose_falls_back_to_stop_on_invocation_failure_when_retry_not_offered():
    """If the caller's own contract doesn't offer "retry" as a valid action, an
    invocation failure must still fail closed to "stop" rather than return an action
    the caller never sanctioned."""
    payload = json.loads(json.dumps(OUTER_PAYLOAD))
    payload["output_contract"]["action"] = ["revise_plan", "stop"]
    with patch.object(rac, "_run_headless_claude", side_effect=RuntimeError("timed out")):
        decision = rac.diagnose(payload)
    assert decision["action"] == "stop"
    assert "invocation failed" in decision["rationale"]


def test_main_reads_stdin_writes_one_json_line(capsys, monkeypatch):
    monkeypatch.setattr(sys, "stdin", __import__("io").StringIO(json.dumps(OUTER_PAYLOAD)))
    with patch.object(rac, "_run_headless_claude", return_value={
        "action": "stop", "modifications": {}, "rationale": "x",
    }):
        rac.main()
    out = capsys.readouterr().out.strip()
    decision = json.loads(out)
    assert decision["action"] == "stop"
    assert set(decision.keys()) == {"action", "rationale", "modifications"}


def test_engine_context_reaches_the_prompt_with_the_spent_rungs():
    """_escalate used to hand the agent only finding.to_dict(), and the agent read its
    history from plan_summary.recovery_history -- which the inner engine path never writes.
    The prompt claimed nothing had been tried on a run that had spent both rungs."""
    payload = {
        "plan_summary": {"run_name": "PEG1", "recovery_history": []},
        "issue": {
            "code": "PROCESS_FAILED", "stage": "equilibration", "severity": "blocking",
            "confidence": "low", "details": {"error": "boom"},
            "engine_context": {
                "confidence": "low", "escalation_attempt": 2, "max_agent_decisions": 2,
                "run_dir": "/abs/data/PEG1", "failed_attempt_manifest": "attempt-7",
                "remedy_history": [{"remedy_id": "transient_retry", "code": "PROCESS_FAILED",
                                    "stage": "equilibration", "application": 1}],
            },
        },
        "output_contract": {"action": ["retry", "revise_plan", "stop"], "modifications": {}},
    }
    problem = rac._trim_payload(payload)
    assert problem["confidence"] == "low"
    assert problem["run_dir"] == "/abs/data/PEG1"
    # The engine's real history wins over the empty plan-level one.
    assert problem["recovery_history"][0]["remedy_id"] == "transient_retry"

    prompt = rac._build_prompt(problem)
    assert "escalation 2 of 2" in prompt
    assert "transient_retry x1 on PROCESS_FAILED@equilibration" in prompt
    assert "/abs/data/PEG1" in prompt
    # details must survive: `detail` would have shadowed it, losing gate_output.
    assert "boom" in prompt


def test_outer_control_plane_payload_without_engine_context_still_trims():
    """The outer loop sends a real WorkflowIssue.to_dict() carrying none of the new keys."""
    payload = {
        "plan_summary": {"run_name": "PEG1", "recovery_history": []},
        "issue": {"code": "TG_REVIEW", "stage": "thermal", "detail": {"gap": 31.0}},
        "output_contract": {"action": ["retry", "stop"], "modifications": {}},
    }
    problem = rac._trim_payload(payload)
    assert problem["code"] == "TG_REVIEW"
    assert "engine_context" not in problem and "run_dir" not in problem
    prompt = rac._build_prompt(problem)
    assert "No automatic remedy has been applied" in prompt


def test_outer_loop_agent_decisions_render_as_decisions_not_empty_rungs():
    """apply_recovery's history entries are {action, rationale, modifications}, not
    {remedy_id, code, stage, application}. Rendering one shape's keys against the other
    printed "None x None on None@None" -- a spent rung that never happened."""
    problem = {"recovery_history": [{"action": "revise_plan", "rationale": "cell too small",
                                     "modifications": {"nchain": 60}}]}
    rendered = rac._spent_rungs(problem)
    assert "revise_plan" in rendered and "nchain" in rendered
    assert "None" not in rendered
