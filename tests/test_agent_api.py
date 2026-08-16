import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))

import agent_api  # noqa: E402


def test_contract_enforces_scientific_planning_and_conditional_recovery():
    contract = agent_api.interface_contract()

    assert contract["available_actions"] == ("run_scientific_campaign", "inspect_run")
    assert any("planning agent must decide" in rule for rule in contract["rules"])
    assert any("only after a structured issue" in rule for rule in contract["rules"])


def test_inspect_run_combines_control_and_executor_state(tmp_path):
    raw_dir = tmp_path / "data" / "RUN1" / "raw"
    raw_dir.mkdir(parents=True)
    (raw_dir / "control_state.json").write_text(json.dumps({
        "status": "unresolved",
        "recovery_agent_calls": 1,
    }))
    (raw_dir / "executor_state.json").write_text(json.dumps({
        "halted": {"stage": "mechanical", "reason": "TENSION_RUN_FAILED"},
        "stages": {"equil_check": {"status": "done"}},
    }))

    result = agent_api.inspect_run("RUN1", repo_root=tmp_path)

    assert result["status"] == "unresolved"
    assert result["control"]["recovery_agent_calls"] == 1
    assert result["executor"]["halted"]["reason"] == "TENSION_RUN_FAILED"


def test_inspect_unknown_run_is_structured(tmp_path):
    result = agent_api.inspect_run("missing", repo_root=tmp_path)

    assert result["status"] == "not_found"
    assert result["run_name"] == "missing"
