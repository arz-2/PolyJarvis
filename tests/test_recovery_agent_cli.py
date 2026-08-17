import json
import sys
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))

import recovery_agent_cli as rac  # noqa: E402


OUTER_PAYLOAD = {
    "task": "diagnose_polymer_simulation_issue",
    "intent": {"run_name": "PP", "goal": "test"},
    "plan_summary": {"run_name": "PP", "polymer_class": "PHYC", "recovery_history": []},
    "issue": {"stage": "equilibration", "code": "PROCESS_FAILED",
              "detail": {"error": "boom"}, "attempt": 0},
    "output_contract": {"action": ["retry", "revise_plan", "stop"], "rationale": "...",
                         "modifications": {}},
}

INNER_PAYLOAD = {
    "task": "diagnose_polymer_simulation_issue",
    "intent": {"run_name": "PP", "goal": "test"},
    "plan_summary": {"run_name": "PP", "polymer_class": "PHYC"},
    "issue": {"code": "PROCESS_FAILED", "stage": "equilibration", "severity": "blocking",
              "confidence": "high", "details": {"error": "boom"}, "remedy_id": None},
    "output_contract": {"action": ["retry", "revise_plan", "stop"], "rationale": "...",
                         "modifications": {}},
}


def test_trim_payload_handles_outer_shape():
    trimmed = rac._trim_payload(OUTER_PAYLOAD)
    assert trimmed["stage"] == "equilibration"
    assert trimmed["code"] == "PROCESS_FAILED"
    assert trimmed["detail"] == {"error": "boom"}
    assert "recovery_history" not in trimmed  # empty list dropped


def test_trim_payload_handles_inner_finding_shape():
    trimmed = rac._trim_payload(INNER_PAYLOAD)
    assert trimmed["stage"] == "equilibration"
    assert trimmed["code"] == "PROCESS_FAILED"
    assert trimmed["detail"] == {"error": "boom"}
    assert trimmed["severity"] == "blocking"


def test_diagnose_always_returns_stop_on_success():
    with patch.object(rac, "_run_headless_claude", return_value={
        "decision": "params_file not threaded", "remedies_prescribed": "thread emc_params_path",
        "rationale": "cell.data has no embedded Coeffs sections",
    }):
        decision = rac.diagnose(OUTER_PAYLOAD)
    assert decision["action"] == "stop"
    assert decision["modifications"] == {}
    assert "params_file not threaded" in decision["rationale"]


def test_run_headless_claude_retries_once_then_succeeds():
    calls = {"n": 0}

    def flaky(prompt, timeout_s):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("aborted_streaming")
        return {"decision": "d", "remedies_prescribed": "r", "rationale": "x"}

    with patch.object(rac, "_run_headless_claude_once", side_effect=flaky):
        result = rac._run_headless_claude("prompt", retries=1)
    assert calls["n"] == 2
    assert result["decision"] == "d"


def test_run_headless_claude_gives_up_after_retries_exhausted():
    with patch.object(rac, "_run_headless_claude_once",
                       side_effect=RuntimeError("aborted_streaming")):
        try:
            rac._run_headless_claude("prompt", retries=1)
            assert False, "expected RuntimeError"
        except RuntimeError as exc:
            assert "aborted_streaming" in str(exc)


def test_diagnose_fails_closed_on_headless_error():
    with patch.object(rac, "_run_headless_claude", side_effect=RuntimeError("timed out")):
        decision = rac.diagnose(OUTER_PAYLOAD)
    assert decision["action"] == "stop"
    assert "wrapper failed" in decision["rationale"]
    assert "timed out" in decision["rationale"]


def test_main_reads_stdin_writes_one_json_line(capsys, monkeypatch):
    monkeypatch.setattr(sys, "stdin", __import__("io").StringIO(json.dumps(OUTER_PAYLOAD)))
    with patch.object(rac, "_run_headless_claude", return_value={
        "decision": "d", "remedies_prescribed": "r", "rationale": "x",
    }):
        rac.main()
    out = capsys.readouterr().out.strip()
    decision = json.loads(out)
    assert decision["action"] == "stop"
    assert set(decision.keys()) == {"action", "rationale", "modifications"}
