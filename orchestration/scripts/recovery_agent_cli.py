#!/usr/bin/env python3
"""Headless recovery-agent adapter for scientific_control.py's --recovery-agent-command.

Reads a PolyJarvis failure payload on stdin (the JsonSubprocessAgent contract shared by
both scientific_control.py's outer recovery loop and workflow_engine.py's inner
stage-escalation loop), runs a headless Claude session that invokes the `/recover`
slash command -- the same command a live orchestrating session uses, loading its
diagnosis playbook from this repo's own .claude/commands/recover.md (tracked in this
checkout, not the sibling PolyJarvis worktree -- that sibling's recover.md is for the
prior plan_mode-based multi-agent architecture and does not apply here; see CLAUDE.md)
-- and returns exactly one JSON object on stdout.

The session may return `action: retry` (unchanged params -- a confirmed transient
cause) or `revise_plan` (concrete `modifications`), not just `stop`. This adapter never
gains write/execute authority to act on that decision itself -- tool access stays Read
plus a read-only Bash allowlist, same as before. Whatever `action`/`modifications` are
returned are only ever applied by the calling engine's own already-bounded, already-
validated machinery (forbidden-key check, `plan_validator`, `_validate_overrides`,
`_validate_protocol_relationships`, `MAX_AGENT_DECISIONS`/`MAX_RECOVERY_ATTEMPTS` caps)
-- this adapter just stops silently discarding the decision. A wrapper/session failure
(the headless call itself crashing, timing out, or returning unusable output -- not a
considered decision) is not a diagnosis, so it is never conflated with an agent's real
`stop`: it maps to `retry` instead, still bounded by the same MAX_AGENT_DECISIONS/
MAX_RECOVERY_ATTEMPTS=2 caps, so a persistent (non-transient) failure still reaches a
human -- see `diagnose()`.
"""

import json
import subprocess
import sys

# A CHECKED COPY of track_registry.STAGE_TRACK, not derived from it: the values are
# (track, step) and the step is not always the key -- equil-check reports as step "equil", and
# the macro name "equilibration" is accepted as an alias. This is prompt text for /recover, so a
# derivation carrying two special cases would be less readable than the table. Agreement with
# the registry is asserted by tests/test_track_registry_lockstep.py.
STAGE_TRACK = {
    "build": ("foundation", "build"),
    "equilibration": ("foundation", "equil"),
    "equil": ("foundation", "equil"),
    "equil-check": ("foundation", "equil"),
    "cooling": ("cooling", "cool"),
    "cool": ("cooling", "cool"),
    "cool-check": ("cooling", "cool"),
    "tg": ("thermal", "tg"),
    "analyze-tg": ("thermal", "analyze-tg"),
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

DEFAULT_ACTIONS = ("retry", "revise_plan", "stop")


def _output_schema(actions) -> dict:
    return {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": sorted(actions),
                       "description": "retry = re-attempt with unchanged params (confirmed "
                                      "transient cause); revise_plan = apply modifications; "
                                      "stop = no safe automatic fix, needs human review"},
            "modifications": {"type": "object",
                              "description": "decided_params overrides; only when action=="
                                             "revise_plan, else {}"},
            "rationale": {"type": "string",
                          "description": "root cause and why this action, citing the specific "
                                         "recover.md row or evidence"},
        },
        "required": ["action", "rationale", "modifications"],
    }


def _trim_payload(payload: dict) -> dict:
    """Only the problem -- not the full intent/plan dump the outer contract carries."""
    issue = payload.get("issue") or {}
    plan_summary = payload.get("plan_summary") or {}
    contract = payload.get("output_contract") or {}
    problem = {
        "run_name": plan_summary.get("run_name"),
        "stage": issue.get("stage"),
        "code": issue.get("code"),
        "detail": issue.get("detail", issue.get("details")),
        "severity": issue.get("severity"),
        "recovery_history": plan_summary.get("recovery_history"),
        "valid_actions": contract.get("action"),
        "modification_contract": contract.get("modifications"),
    }
    return {k: v for k, v in problem.items() if v not in (None, [], {})}


def _build_prompt(problem: dict) -> str:
    run_name = problem.get("run_name") or "unknown"
    stage = problem.get("stage") or problem.get("code") or "unknown"
    track, step = STAGE_TRACK.get(stage, ("unknown", stage))
    symptom = json.dumps({k: v for k, v in problem.items()
                          if k not in ("run_name", "stage", "valid_actions",
                                       "modification_contract")}, default=str)
    valid_actions = problem.get("valid_actions") or list(DEFAULT_ACTIONS)
    modification_contract = problem.get("modification_contract") or {}
    return (
        f'/recover run_name={run_name} track={track} step={step} symptom={json.dumps(symptom)}\n\n'
        "Follow recover.md's procedure with the Read/Bash tools available (no MCP tools "
        "here -- reason from files/logs directly, the same way a live session would when "
        "they are unavailable). You never write, edit, resubmit, or claim/release any "
        "resource yourself -- the calling engine re-validates and applies whatever you "
        f"decide. Choose one action from {valid_actions}: `retry` re-attempts with "
        "unchanged params (only when you've confirmed the cause was transient and is now "
        "resolved); `revise_plan` applies `modifications` (decided_params overrides "
        f"constrained to this contract: {json.dumps(modification_contract, default=str)}) "
        "-- only when you're confident of both the root cause and the fix; `stop` when the "
        "failure is novel, ambiguous, or needs a human judgment call recover.md's ladder "
        "doesn't cover. Conclude with exactly one JSON object matching the required schema."
    )


def _run_headless_claude_once(prompt: str, schema: dict, timeout_s: int) -> dict:
    cmd = [
        "claude", "-p", "--output-format", "json",
        "--allowedTools", *READ_ONLY_TOOLS,
        "--json-schema", json.dumps(schema),
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


def _run_headless_claude(prompt: str, schema: dict, timeout_s: int = 600, retries: int = 1) -> dict:
    """One retry on any failure (transient streaming aborts observed in testing) before
    giving up -- matches this codebase's own retry-once convention (workflow_engine.py's
    transient_retry local_cap=2, scientific_control.py's MAX_RECOVERY_ATTEMPTS=2)."""
    last_exc: Exception = RuntimeError("no attempts made")
    for _ in range(retries + 1):
        try:
            return _run_headless_claude_once(prompt, schema, timeout_s)
        except Exception as exc:
            last_exc = exc
    raise last_exc


def diagnose(payload: dict) -> dict:
    """Returns a RecoveryDecision-shaped dict: {action, rationale, modifications}."""
    problem = _trim_payload(payload)
    valid_actions = problem.get("valid_actions") or list(DEFAULT_ACTIONS)
    try:
        structured = _run_headless_claude(_build_prompt(problem), _output_schema(valid_actions))
        action = structured.get("action")
        if action not in valid_actions:
            action = "stop"
        modifications = dict(structured.get("modifications") or {}) if action == "revise_plan" else {}
        rationale = f"[recovery-agent diagnosis] {structured.get('rationale', '')}"
    except Exception as exc:
        # The invocation itself failed (subprocess crash, timeout, malformed/missing
        # structured output) -- this carries no diagnosis of the underlying issue, so it
        # must not be conflated with an agent's considered `stop`. Ask the caller to
        # retry the stage instead: WorkflowEngine._escalate/ScientificControlPlane
        # already bound this at MAX_AGENT_DECISIONS/MAX_RECOVERY_ATTEMPTS=2, so a
        # persistent (non-transient) underlying failure still reaches
        # escalation_required/unresolved for a human -- this only spares a human from
        # unsticking a one-off invocation blip. Falls back to "stop" if the caller's own
        # contract doesn't offer "retry" as a valid action.
        action = "retry" if "retry" in valid_actions else "stop"
        modifications = {}
        rationale = f"[recovery-agent invocation failed, retrying the stage] {exc}"
    return {"action": action, "rationale": rationale, "modifications": modifications}


def main() -> None:
    payload = json.loads(sys.stdin.read())
    print(json.dumps(diagnose(payload)))


if __name__ == "__main__":
    main()
