#!/usr/bin/env python3
"""Headless recovery-agent adapter for scientific_control.py's --recovery-agent-command.

Diagnose-only: reads a PolyJarvis failure payload on stdin (the JsonSubprocessAgent
contract shared by both scientific_control.py's outer recovery loop and
workflow_engine.py's inner stage-escalation loop), runs a headless Claude session that
invokes the `/recover` slash command -- the same command a live orchestrating session
uses, which loads its diagnosis playbook regardless of which checkout it physically
lives in (verified: `/recover.md` is not in this repo at all, only in the sibling
worktree, yet `/recover ...` still loads it headlessly) -- and returns exactly one
JSON object on stdout.

The returned action is ALWAYS "stop". This adapter never authorizes either caller to
auto-apply a fix -- it only records a diagnosis (decision/remedies_prescribed/rationale)
for a human to read and act on, mirroring the recovery-agent subagent's own boundary
("never re-spawns a worker, never claims/releases resources"). Tool access is
restricted to Read plus a read-only Bash allowlist as a second, mechanical guarantee
of that boundary -- not just a prompted one.
"""

import json
import subprocess
import sys

STAGE_TRACK = {
    "build": ("foundation", "build"),
    "equilibration": ("foundation", "equil"),
    "equil": ("foundation", "equil"),
    "equil-check": ("foundation", "equil"),
    "tg": ("thermal", "tg"),
    "analyze-tg": ("thermal", "analyze-tg"),
    "analyze-tg-multirate": ("thermal", "analyze-tg"),
    "deform": ("mechanical", "deform"),
    "murnaghan": ("mechanical", "murnaghan"),
    "analyze-bm": ("mechanical", "analyze-bm"),
    "run-summary": ("summary", "run-summary"),
}

READ_ONLY_TOOLS = [
    "Read",
    "Bash(find:*)", "Bash(grep:*)", "Bash(ls:*)", "Bash(ps:*)",
    "Bash(cat:*)", "Bash(tail:*)", "Bash(head:*)", "Bash(wc:*)", "Bash(jq:*)",
]

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "decision": {"type": "string", "description": "one-line diagnosis of the root cause"},
        "remedies_prescribed": {"type": "string",
                                 "description": "the recover.md remedy/ladder rung to apply, verbatim"},
        "rationale": {"type": "string",
                      "description": "why, citing the specific recover.md row or evidence"},
    },
    "required": ["decision", "remedies_prescribed", "rationale"],
}


def _trim_payload(payload: dict) -> dict:
    """Only the problem -- not the full intent/plan dump the outer contract carries."""
    issue = payload.get("issue") or {}
    plan_summary = payload.get("plan_summary") or {}
    problem = {
        "run_name": plan_summary.get("run_name"),
        "stage": issue.get("stage"),
        "code": issue.get("code"),
        "detail": issue.get("detail", issue.get("details")),
        "severity": issue.get("severity"),
        "recovery_history": plan_summary.get("recovery_history"),
    }
    return {k: v for k, v in problem.items() if v not in (None, [], {})}


def _build_prompt(problem: dict) -> str:
    run_name = problem.get("run_name") or "unknown"
    stage = problem.get("stage") or problem.get("code") or "unknown"
    track, step = STAGE_TRACK.get(stage, ("unknown", stage))
    symptom = json.dumps({k: v for k, v in problem.items()
                          if k not in ("run_name", "stage")}, default=str)
    return (
        f'/recover run_name={run_name} track={track} step={step} symptom={json.dumps(symptom)}\n\n'
        "Diagnose only -- never write, edit, resubmit, or claim/release any resource; "
        "a human applies whatever you recommend. Follow recover.md's procedure with the "
        "Read/Bash tools available (no MCP tools here -- reason from files/logs directly, "
        "the same way a live session would when they are unavailable). Conclude with "
        "exactly one JSON object matching the required schema."
    )


def _run_headless_claude_once(prompt: str, timeout_s: int) -> dict:
    cmd = [
        "claude", "-p", "--output-format", "json",
        "--allowedTools", *READ_ONLY_TOOLS,
        "--json-schema", json.dumps(OUTPUT_SCHEMA),
        "--max-budget-usd", "1.0",
        "--fallback-model", "sonnet",
        prompt,
    ]
    completed = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
    if completed.returncode != 0:
        raise RuntimeError(
            f"headless claude exited {completed.returncode}: {completed.stderr.strip()[:2000]}"
        )
    outer = json.loads(completed.stdout)
    if outer.get("is_error"):
        raise RuntimeError(
            f"headless claude reported an error: {outer.get('terminal_reason')} "
            f"{outer.get('errors') or outer.get('result')}"
        )
    structured = outer.get("structured_output")
    if not isinstance(structured, dict):
        raise RuntimeError("headless claude did not return structured_output")
    return structured


def _run_headless_claude(prompt: str, timeout_s: int = 600, retries: int = 1) -> dict:
    """One retry on any failure (transient streaming aborts observed in testing) before
    giving up -- matches this codebase's own retry-once convention (workflow_engine.py's
    transient_retry local_cap=2, scientific_control.py's MAX_RECOVERY_ATTEMPTS=2)."""
    last_exc: Exception = RuntimeError("no attempts made")
    for _ in range(retries + 1):
        try:
            return _run_headless_claude_once(prompt, timeout_s)
        except Exception as exc:
            last_exc = exc
    raise last_exc


def diagnose(payload: dict) -> dict:
    """Returns a RecoveryDecision-shaped dict. action is always 'stop' -- diagnose only."""
    problem = _trim_payload(payload)
    try:
        structured = _run_headless_claude(_build_prompt(problem))
        rationale = (
            f"[recovery-agent diagnosis] {structured.get('decision', '')}\n"
            f"Remedies prescribed: {structured.get('remedies_prescribed', '')}\n"
            f"Rationale: {structured.get('rationale', '')}"
        )
    except Exception as exc:  # fail closed: still a valid decision, never crash the caller
        rationale = f"[recovery-agent wrapper failed, no diagnosis available] {exc}"
    return {"action": "stop", "rationale": rationale, "modifications": {}}


def main() -> None:
    payload = json.loads(sys.stdin.read())
    print(json.dumps(diagnose(payload)))


if __name__ == "__main__":
    main()
