"""headless_claude — the argv and failure contract of a `claude -p` node.

The property worth protecting is the one recovery_agent_cli.py already documents at length:
a WRAPPER failure -- crash, timeout, missing structured_output -- carries no answer, and
must never be laundered into one. Here that means an exception, so each caller decides
what a failed critique or adjudication means for its own step.

Also asserted: these sessions cannot reach the simulation engines. No MCP servers, and no
Write or Edit in the tool allowlist, which is what makes AGENTS.md's "agents never write
simulation files" mechanically true rather than a prompt instruction.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))

import headless_claude as hc  # noqa: E402

SCHEMA = {"type": "object", "properties": {"verdict": {"type": "string"}}}

# This file tests the runner itself, with subprocess.run stubbed in every case, so it opts
# out of conftest's blanket refusal -- otherwise it would be asserting against the guard.
pytestmark = pytest.mark.allow_headless_claude


class _Completed:
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout, self.stderr, self.returncode = stdout, stderr, returncode


def _patch(monkeypatch, completed, seen=None):
    def fake(cmd, **kwargs):
        if seen is not None:
            seen["cmd"], seen["kwargs"] = cmd, kwargs
        return completed
    monkeypatch.setattr(hc.subprocess, "run", fake)


def test_returns_structured_output(monkeypatch):
    _patch(monkeypatch, _Completed(json.dumps({"structured_output": {"verdict": "agrees"}})))
    assert hc.invoke_once("p", SCHEMA) == {"verdict": "agrees"}


def test_argv_carries_the_schema_budget_and_fallback(monkeypatch):
    seen = {}
    _patch(monkeypatch, _Completed(json.dumps({"structured_output": {}})), seen)
    hc.invoke_once("prompt text", SCHEMA, max_budget_usd=2.5, model="sonnet")
    cmd = seen["cmd"]
    assert cmd[:4] == ["claude", "-p", "--output-format", "json"]
    assert json.loads(cmd[cmd.index("--json-schema") + 1]) == SCHEMA
    assert cmd[cmd.index("--max-budget-usd") + 1] == "2.5"
    assert cmd[cmd.index("--fallback-model") + 1] == "sonnet"
    assert cmd[cmd.index("--model") + 1] == "sonnet"
    assert cmd[-1] == "prompt text", "the prompt is the final positional argument"


def test_the_session_gets_no_mcp_servers(monkeypatch):
    """These nodes reason over files. They must not be able to submit a job, claim a GPU,
    or reach the LAMMPS/EMC engines."""
    seen = {}
    _patch(monkeypatch, _Completed(json.dumps({"structured_output": {}})), seen)
    hc.invoke_once("p", SCHEMA)
    assert "--strict-mcp-config" in seen["cmd"]
    assert "--mcp-config" not in seen["cmd"]


def test_no_write_tool_is_ever_granted_by_default(monkeypatch):
    seen = {}
    _patch(monkeypatch, _Completed(json.dumps({"structured_output": {}})), seen)
    hc.invoke_once("p", SCHEMA)
    granted = seen["cmd"][seen["cmd"].index("--allowedTools") + 1:]
    assert not any(t.startswith(("Write", "Edit")) for t in granted)


def test_cwd_is_pinned_to_the_repo(monkeypatch):
    """A `claude -p` session resolves relative paths -- including .claude/ configuration --
    from its working directory, and the graph may be launched from anywhere."""
    seen = {}
    _patch(monkeypatch, _Completed(json.dumps({"structured_output": {}})), seen)
    hc.invoke_once("p", SCHEMA)
    assert seen["kwargs"]["cwd"] == str(hc.REPO_ROOT)


@pytest.mark.parametrize("completed,match", [
    (_Completed("", "boom", 1), "exited 1"),
    (_Completed("not json"), "non-JSON"),
    (_Completed(json.dumps({"is_error": True, "terminal_reason": "budget"})), "reported an error"),
    (_Completed(json.dumps({"result": "prose, no schema"})), "did not return structured_output"),
])
def test_every_wrapper_failure_raises_rather_than_returning_an_answer(monkeypatch, completed, match):
    _patch(monkeypatch, completed)
    with pytest.raises(hc.HeadlessError, match=match):
        hc.invoke_once("p", SCHEMA)


def test_retry_once_then_gives_up():
    calls = []

    def flaky():
        calls.append(1)
        raise hc.HeadlessError("transient")
    with pytest.raises(hc.HeadlessError):
        hc.retry_once(flaky)
    assert len(calls) == 2, "one retry, matching this codebase's retry-once convention"


def test_retry_returns_the_second_attempt_when_the_first_aborts():
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) == 1:
            raise hc.HeadlessError("streaming abort")
        return {"verdict": "agrees"}
    assert hc.retry_once(flaky) == {"verdict": "agrees"}


def test_timeout_propagates_so_a_caller_can_distinguish_it():
    def fake(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd="claude", timeout=1)
    import unittest.mock as m
    with m.patch.object(hc.subprocess, "run", fake):
        with pytest.raises(subprocess.TimeoutExpired):
            hc.invoke_once("p", SCHEMA)


# --- prompt sourcing --------------------------------------------------------
def test_markdown_body_strips_yaml_frontmatter(tmp_path):
    path = tmp_path / "a.md"
    path.write_text("---\nname: x\ntools: Read\n---\n\nThe body.\n")
    assert hc.markdown_body(path) == "The body.\n"


def test_markdown_body_leaves_a_file_without_frontmatter_alone(tmp_path):
    path = tmp_path / "a.md"
    path.write_text("# Heading\n\nbody\n")
    assert hc.markdown_body(path).startswith("# Heading")


def test_section_slices_between_two_headings(tmp_path):
    path = tmp_path / "s.md"
    path.write_text("## 4. before\nno\n\n## 5. wanted\nyes\n\n## 6. after\nno\n")
    out = hc.section(path, "## 5.", "## 6.")
    assert "wanted" in out and "before" not in out and "after" not in out


def test_section_raises_when_the_heading_moved(tmp_path):
    """The prompts are slices of live .claude markdown, so a renamed heading must fail
    loudly rather than silently sending the model the wrong instructions."""
    path = tmp_path / "s.md"
    path.write_text("## 1. only\n")
    with pytest.raises(hc.HeadlessError, match="not found"):
        hc.section(path, "## 5.", "## 6.")


def test_the_real_skill_and_agent_files_still_slice():
    """Guards against a rename in .claude/ silently degrading both model nodes."""
    skill = REPO_ROOT / ".claude" / "skills" / "novel-run-plan" / "SKILL.md"
    agent = REPO_ROOT / ".claude" / "agents" / "literature-grounding-worker.md"
    if not skill.is_file() or not agent.is_file():
        pytest.skip(".claude sources not present")
    assert len(hc.section(skill, "## 5.", "## 6.")) > 500
    body = hc.markdown_body(agent)
    assert body and not body.startswith("---")
