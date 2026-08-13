"""Dry-run tests for the compaction / output-discipline hooks.

Each hook is exercised as a subprocess with synthetic hook JSON on stdin, matching how the hooks
are actually invoked.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS = REPO_ROOT / ".claude" / "hooks"

PRECOMPACT = HOOKS / "precompact_summary_directive.py"
SUBAGENT_START = HOOKS / "subagent_output_contract.py"
SUBAGENT_STOP = HOOKS / "subagent_memory_reminder.py"

MAX_CHARS = 3000


def run_hook(script: Path, payload: dict, cwd: Path = REPO_ROOT) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(script)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(cwd),
        env={"CLAUDE_PROJECT_DIR": str(REPO_ROOT), "PATH": "/usr/bin:/bin"},
    )


# ── PreCompact ────────────────────────────────────────────────────────────────


def existing_runs():
    return sorted(
        p.parent.name for p in (REPO_ROOT / "data").glob("*/run_log.md")
        if p.parent.name != "TEMPLATE"
    )


def transcript(tmp_path, *run_names) -> str:
    """A stand-in transcript referencing the given runs the way a real session would."""
    path = tmp_path / "transcript.jsonl"
    lines = [json.dumps({"text": "copied data/TEMPLATE/run_log.md"})]
    lines += [json.dumps({"text": f"wrote data/{n}/raw/run_plan.json"}) for n in run_names]
    path.write_text("\n".join(lines))
    return str(path)


def test_precompact_orchestrator_directive():
    r = run_hook(PRECOMPACT, {"hook_event_name": "PreCompact", "trigger": "auto"})
    assert r.returncode == 0
    out = r.stdout
    for token in ("chain_id", "monitor_command", "run_log.md", "plan_mode", "gpu_ids",
                  "ORCHESTRATOR.md"):
        assert token in out, f"missing {token!r} in directive"
    assert len(out) <= MAX_CHARS


def test_precompact_resolves_the_session_own_run(tmp_path):
    runs = existing_runs()
    if not runs:
        pytest.skip("no run under data/ to snapshot")
    r = run_hook(PRECOMPACT, {
        "hook_event_name": "PreCompact", "trigger": "auto",
        "transcript_path": transcript(tmp_path, runs[0]),
    })
    assert "AUTHORITATIVE STATE" in r.stdout
    assert f"data/{runs[0]}/run_log.md" in r.stdout
    for other in runs[1:]:
        assert f"data/{other}/run_log.md" not in r.stdout


def test_precompact_refuses_state_block_when_run_is_ambiguous(tmp_path):
    """Concurrent campaigns share this host — a state block naming the wrong run is worse
    than none."""
    runs = existing_runs()
    if len(runs) < 2:
        pytest.skip("needs two runs under data/")
    r = run_hook(PRECOMPACT, {
        "hook_event_name": "PreCompact", "trigger": "auto",
        "transcript_path": transcript(tmp_path, *runs[:2]),
    })
    assert "AUTHORITATIVE STATE" not in r.stdout
    assert "could not be resolved" in r.stdout


def test_precompact_no_state_block_without_transcript():
    r = run_hook(PRECOMPACT, {"hook_event_name": "PreCompact", "trigger": "auto"})
    assert "AUTHORITATIVE STATE" not in r.stdout


def test_precompact_state_block_strips_template_comments(tmp_path):
    """run_log.md's HTML comments are template scaffolding, not state."""
    runs = existing_runs()
    if not runs:
        pytest.skip("no run under data/ to snapshot")
    r = run_hook(PRECOMPACT, {
        "hook_event_name": "PreCompact", "trigger": "auto",
        "transcript_path": transcript(tmp_path, runs[0]),
    })
    state = r.stdout.split("AUTHORITATIVE STATE", 1)[1]
    assert "<!--" not in state and "-->" not in state


def test_precompact_output_is_plain_text_not_json():
    """stdout is consumed raw as compaction custom instructions — JSON would be passed through."""
    r = run_hook(PRECOMPACT, {"hook_event_name": "PreCompact", "trigger": "manual"})
    with pytest.raises(ValueError):
        json.loads(r.stdout)


def test_precompact_worker_directive_has_no_state_block(tmp_path):
    runs = existing_runs()
    r = run_hook(PRECOMPACT, {
        "hook_event_name": "PreCompact", "trigger": "auto",
        "agent_id": "abc123", "agent_type": "murnaghan-worker",
        "transcript_path": transcript(tmp_path, *runs[:1]),
    })
    assert r.returncode == 0
    assert "RESULT:" in r.stdout
    assert "AUTHORITATIVE STATE" not in r.stdout
    assert "GPU claims" not in r.stdout


def test_precompact_survives_missing_repo_state(tmp_path):
    """No data/ runs and no pick_gpu.py reachable — still exits 0 with the directive alone."""
    stub_root = tmp_path / "repo"
    (stub_root / ".claude" / "hooks").mkdir(parents=True)
    (stub_root / "data").mkdir()
    stub = stub_root / ".claude" / "hooks" / PRECOMPACT.name
    stub.write_text(PRECOMPACT.read_text())

    r = subprocess.run(
        [sys.executable, str(stub)],
        input=json.dumps({"hook_event_name": "PreCompact", "trigger": "auto"}),
        capture_output=True, text=True, timeout=60, cwd=str(stub_root),
        env={"CLAUDE_PROJECT_DIR": str(stub_root), "PATH": "/usr/bin:/bin"},
    )
    assert r.returncode == 0
    assert "AUTHORITATIVE STATE" not in r.stdout
    assert "run_log.md" in r.stdout


def test_precompact_tolerates_malformed_stdin():
    r = subprocess.run(
        [sys.executable, str(PRECOMPACT)],
        input="not json", capture_output=True, text=True, timeout=60, cwd=str(REPO_ROOT),
        env={"CLAUDE_PROJECT_DIR": str(REPO_ROOT), "PATH": "/usr/bin:/bin"},
    )
    assert r.returncode == 0


# ── SubagentStart ─────────────────────────────────────────────────────────────


def test_subagent_start_worker_gets_result_block_invariant():
    r = run_hook(SUBAGENT_START, {
        "hook_event_name": "SubagentStart", "agent_id": "x", "agent_type": "murnaghan-worker",
    })
    assert r.returncode == 0
    payload = json.loads(r.stdout)
    assert payload["suppressOutput"] is True
    hso = payload["hookSpecificOutput"]
    assert hso["hookEventName"] == "SubagentStart"
    assert "RESULT:" in hso["additionalContext"]
    assert "memory save is never the last action" in hso["additionalContext"]


def test_subagent_start_builtin_gets_report_budget():
    r = run_hook(SUBAGENT_START, {
        "hook_event_name": "SubagentStart", "agent_id": "x", "agent_type": "Explore",
    })
    ctx = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "15 lines" in ctx
    assert "file:line" in ctx
    assert "RESULT:" not in ctx


@pytest.mark.parametrize("agent_type", ["", "not-a-real-agent"])
def test_subagent_start_silent_for_unknown_agent(agent_type):
    r = run_hook(SUBAGENT_START, {"hook_event_name": "SubagentStart", "agent_type": agent_type})
    assert r.returncode == 0
    assert r.stdout.strip() == ""


def test_every_project_agent_resolves_to_the_worker_contract():
    for md in sorted((REPO_ROOT / ".claude" / "agents").glob("*.md")):
        r = run_hook(SUBAGENT_START, {
            "hook_event_name": "SubagentStart", "agent_id": "x", "agent_type": md.stem,
        })
        ctx = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]
        assert "RESULT:" in ctx, md.stem


# ── SubagentStop ──────────────────────────────────────────────────────────────


def agent_transcript(tmp_path, *entries) -> str:
    """Subagent transcript in the on-disk shape: tool results are themselves type='user'."""
    path = tmp_path / "agent.jsonl"
    path.write_text("\n".join(json.dumps(e) for e in entries))
    return str(path)


def user_text(text):
    return {"type": "user", "message": {"content": text}}


def tool_result(is_error=False):
    return {"type": "user", "message": {"content": [
        {"type": "tool_result", "content": "output", "is_error": is_error},
    ]}}


def stop_payload(tmp_path, *entries, **over):
    payload = {
        "hook_event_name": "SubagentStop", "agent_type": "equilibration-worker",
        "stop_hook_active": False,
        "agent_transcript_path": agent_transcript(tmp_path, user_text("do the thing"), *entries),
    }
    payload.update(over)
    return payload


def test_subagent_stop_fires_on_tool_error(tmp_path):
    r = run_hook(SUBAGENT_STOP, stop_payload(tmp_path, tool_result(), tool_result(is_error=True)))
    ctx = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "MEMORY:" in ctx
    assert "RESULT:" in ctx


def test_subagent_stop_fires_on_coordinator_correction(tmp_path):
    r = run_hook(SUBAGENT_STOP, stop_payload(
        tmp_path, tool_result(), user_text("you dropped the RESULT block — re-emit it")))
    assert "MEMORY:" in json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]


def test_subagent_stop_silent_on_a_clean_run(tmp_path):
    """Many successful tool results are not friction — they are type='user' records too."""
    r = run_hook(SUBAGENT_STOP, stop_payload(tmp_path, *[tool_result() for _ in range(6)]))
    assert r.returncode == 0
    assert r.stdout.strip() == ""


@pytest.mark.parametrize("path", ["", "/nonexistent/agent.jsonl"])
def test_subagent_stop_silent_without_a_readable_transcript(path):
    r = run_hook(SUBAGENT_STOP, {
        "hook_event_name": "SubagentStop", "agent_type": "equilibration-worker",
        "stop_hook_active": False, "agent_transcript_path": path,
    })
    assert r.returncode == 0
    assert r.stdout.strip() == ""


def test_subagent_stop_still_silent_when_already_active(tmp_path):
    r = run_hook(SUBAGENT_STOP, stop_payload(
        tmp_path, tool_result(is_error=True), stop_hook_active=True))
    assert r.returncode == 0
    assert r.stdout.strip() == ""
