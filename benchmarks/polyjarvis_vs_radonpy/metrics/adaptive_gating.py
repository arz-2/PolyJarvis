"""Extracts the adaptive-gating / recovery-yield axis for the PolyJarvis arm.

Reads (field shapes verified live against data/PE1, data/PP, data/a-PS on this checkout):

- data/<run>/raw/control_state.json: top-level `recovery_agent_calls` (int) and `status`.

- data/<run>/workflow_state.json: `remedy_counters.total` (deterministic auto-remedy count,
  confirmed shape `{"by_id": {...}, "by_route": {...}, "total": N}` from data/a-PS) and
  `agent_escalations` (list, each entry an LLM recovery-agent call with `decision.action`).
  `stages.<stage>.attempts[]` gives each attempt's terminal `status` -- first-attempt-pass
  vs final-pass is read directly off this list, no synthetic "recovery disabled" arm needed:
  first_attempt_pass = attempts[0].status == "accepted"; final_pass = the stage's own
  `status` field (the workflow's own terminal verdict) == "accepted", checked across all
  stages present (a run with any non-accepted stage is not a final pass).

IMPORTANT, discovered by reading real data/a-PS output rather than assumed from schema:
`control_state.json.recovery_agent_calls` can be STALE on a resumed run -- a-PS shows
`recovery_agent_calls: 0` there even though `workflow_state.json.agent_escalations` records
2 real LLM recovery calls (per agent_api.py's own comment, recovery is owned by WorkflowEngine
on the resume path; the outer control plane's counter is not necessarily re-touched). So the
authoritative call count is `max(control_state.recovery_agent_calls, len(agent_escalations))`,
and cap-hit is derived from that count plus whether the run actually finished (`final_pass`),
not from control_state's own possibly-stale `status` string.
"""
from __future__ import annotations

import json
from pathlib import Path

from .schema import AdaptiveGatingBlock

MAX_RECOVERY_ATTEMPTS = 2


def extract_adaptive_gating(run_dir: Path) -> AdaptiveGatingBlock:
    block = AdaptiveGatingBlock()

    control_calls = 0
    control_path = run_dir / "raw" / "control_state.json"
    if control_path.is_file():
        control = json.loads(control_path.read_text())
        control_calls = control.get("recovery_agent_calls", 0)
    else:
        block.note = f"no control_state.json at {control_path}"

    workflow_path = run_dir / "workflow_state.json"
    if not workflow_path.is_file():
        block.note += f" (no workflow_state.json at {workflow_path})"
        return block

    workflow = json.loads(workflow_path.read_text())
    block.auto_remedy_total = (workflow.get("remedy_counters") or {}).get("total", 0)
    block.escalation_total = len(workflow.get("agent_escalations") or [])
    # control_state's counter can be stale on a resumed run (see module docstring) -- the
    # escalation list itself is the ground truth when it disagrees.
    block.recovery_agent_calls = max(control_calls, block.escalation_total)

    stages = workflow.get("stages") or {}
    if stages:
        first_attempt_statuses = []
        final_statuses = []
        for stage_record in stages.values():
            attempts = stage_record.get("attempts") or []
            if attempts:
                first_attempt_statuses.append(attempts[0].get("status") == "accepted")
            final_statuses.append(stage_record.get("status") == "accepted")
        if first_attempt_statuses:
            block.first_attempt_pass = all(first_attempt_statuses)
        block.final_pass = all(final_statuses) if final_statuses else None

    block.cap_hit = block.recovery_agent_calls >= MAX_RECOVERY_ATTEMPTS and block.final_pass is False

    return block
