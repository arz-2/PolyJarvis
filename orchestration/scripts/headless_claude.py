#!/usr/bin/env python3
"""One headless `claude -p` call, with structured output — the shared runner for the
LangGraph driver's two model nodes.

This is the same shape recovery_agent_cli.py has used in production since 2026-09: argv,
`structured_output` extraction, and the retry-once convention are deliberately identical,
because the property that matters is the same in all three places -- a WRAPPER failure
(crash, timeout, missing structured output) is not a considered answer and must never be
laundered into one. Callers here get an exception and decide; recovery_agent_cli maps it to
`retry`. That file is cron-wired production (campaign_watchdog.py) and is deliberately NOT
refactored to import this module: collapsing them is worth doing, but not inside a feature
change to live recovery code. See the follow-up note in the plan.

Two things this adds that the new callers need and the recovery adapter does not:

  cwd            recovery_agent_cli relies on its caller's cwd (campaign_watchdog sets it).
                 The graph may be invoked from anywhere, and a `claude -p` session resolves
                 relative paths -- including the repo's own .claude/ configuration -- from
                 its working directory, so it is pinned explicitly.
  no MCP         --strict-mcp-config with no --mcp-config means the session gets ZERO MCP
                 servers. These nodes reason over files; they must not be able to submit a
                 job, claim a GPU, or touch the simulation engines.

Every node using this is READ-ONLY by construction: no Write or Edit is ever in
allowed_tools, and python performs all file writes from the returned structured output.
That is what keeps AGENTS.md's "agents never write simulation files" true mechanically
rather than by prompt instruction, and it is why both node contracts are testable without
a model in the loop.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Callable, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

#: Read plus a read-only Bash allowlist. Matches recovery_agent_cli.READ_ONLY_TOOLS; kept as
#: its own copy so tightening one adapter cannot silently loosen the other.
#:
#: `Bash(<cmd>:*)` matches on the command PREFIX, so a pattern is only as read-only as the
#: worst invocation of that command: `Bash(find:*)` also admitted `find . -delete` and
#: `find . -exec rm -rf {} +`. Replaced by the native Glob/Grep tools, which have no exec
#: path. `Bash(grep:*)` stays -- grep can neither write nor execute, and a permitted pipeline
#: needs every one of its segments permitted.
READ_ONLY_TOOLS: tuple[str, ...] = (
    "Read", "Glob", "Grep",
    "Bash(grep:*)", "Bash(ls:*)", "Bash(ps:*)",
    "Bash(cat:*)", "Bash(tail:*)", "Bash(head:*)", "Bash(wc:*)", "Bash(jq:*)",
)


class HeadlessError(RuntimeError):
    """The invocation failed. Carries no answer -- never conflate with a model's decision."""


def invoke_once_with_meta(
        prompt: str, schema: dict, *, allowed_tools: Sequence[str] = READ_ONLY_TOOLS,
        max_budget_usd: float = 1.0, timeout_s: int = 600, model: str | None = None,
        append_system_prompt: str | None = None, fallback_model: str = "sonnet",
        cwd: Path | str = REPO_ROOT) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run one headless session; return (structured_output, the raw wrapper JSON).

    The wrapper JSON is what carries provenance -- notably which model actually answered,
    which `--fallback-model` makes a real question. Callers that only want the answer use
    invoke_once(); recovery_agent_cli needs the wrapper because a decision that changes a
    run's parameters has to record who made it.
    """
    cmd = ["claude", "-p", "--output-format", "json",
           "--allowedTools", *allowed_tools,
           "--json-schema", json.dumps(schema),
           "--max-budget-usd", str(max_budget_usd),
           "--fallback-model", fallback_model,
           "--strict-mcp-config"]
    if model:
        cmd += ["--model", model]
    if append_system_prompt:
        cmd += ["--append-system-prompt", append_system_prompt]
    cmd.append(prompt)

    completed = subprocess.run(cmd, capture_output=True, text=True,
                               timeout=timeout_s, cwd=str(cwd))
    if completed.returncode != 0:
        raise HeadlessError(
            f"headless claude exited {completed.returncode}: {completed.stderr.strip()[:2000]}")
    try:
        outer = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise HeadlessError(
            f"headless claude returned non-JSON: {completed.stdout[:500]}") from exc
    if outer.get("is_error"):
        raise HeadlessError(
            f"headless claude reported an error: {outer.get('terminal_reason')} "
            f"{outer.get('errors') or outer.get('result')}")
    structured = outer.get("structured_output")
    if not isinstance(structured, dict):
        raise HeadlessError("headless claude did not return structured_output")
    return structured, outer


def invoke_once(prompt: str, schema: dict, **kwargs: Any) -> dict[str, Any]:
    """Run one headless session and return its structured output."""
    return invoke_once_with_meta(prompt, schema, **kwargs)[0]


def retry_once(fn: Callable[[], dict], retries: int = 1) -> dict:
    """One retry on any failure before giving up.

    Matches this codebase's own retry-once convention throughout -- workflow_engine's
    transient_retry local_cap=2, scientific_control's MAX_RECOVERY_ATTEMPTS=2,
    recovery_agent_cli's own retries=1 -- and exists for the same observed reason:
    transient streaming aborts. It does not paper over a persistent failure, which still
    surfaces to the caller as the last exception.
    """
    last: Exception = HeadlessError("no attempts made")
    for _ in range(retries + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 -- re-raised below if every attempt fails
            last = exc
    raise last


def invoke(prompt: str, schema: dict, **kwargs: Any) -> dict[str, Any]:
    """invoke_once with the retry-once convention applied."""
    return retry_once(lambda: invoke_once(prompt, schema, **kwargs))


def markdown_body(path: Path | str) -> str:
    """A .claude markdown file with its YAML frontmatter stripped.

    The critic and adjudicate nodes send the EXISTING agent/skill markdown as their system
    prompt rather than carrying a paraphrase of it in python. That keeps
    .claude/agents/literature-grounding-worker.md and .claude/skills/novel-run-plan/SKILL.md
    the single source of truth for what those steps mean, so editing the skill changes the
    headless behaviour too and the two cannot drift.
    """
    text = Path(path).read_text()
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            text = text[end + 4:]
    return text.lstrip("\n")


def section(path: Path | str, start_heading: str, stop_heading: str) -> str:
    """The slice of a markdown file between two headings, start inclusive.

    Used to send just the adjudication step of SKILL.md rather than the whole skill, whose
    earlier steps instruct an interactive session to run tools the graph has already run.
    """
    body = markdown_body(path)
    try:
        begin = body.index(start_heading)
    except ValueError as exc:
        raise HeadlessError(f"{path}: heading {start_heading!r} not found") from exc
    tail = body.find(stop_heading, begin + len(start_heading))
    return body[begin:tail if tail != -1 else None].rstrip() + "\n"
