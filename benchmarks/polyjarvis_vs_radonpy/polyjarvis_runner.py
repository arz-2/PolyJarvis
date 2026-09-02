"""Read-side accessor for the PolyJarvis arm.

Unlike radonpy_runner.py, this module does not *launch* a PolyJarvis campaign. The
PolyJarvis architecture's "reasoned" planning path is itself an LLM (the planning agent
in orchestration/scripts/scientific_control.py's PlanningAgent protocol) reasoning
through decision_policy.json -- in practice on this project that reasoning is done by a
live Claude Code session running the `novel-run-plan` skill (exactly how data/PE1,
data/PP, and data/a-PS were produced), which then calls agent_api.run_scientific_campaign
/ resume_campaign under the hood via orchestration/scripts/scientific_control.py. There is
no headless, model-provider-neutral command configured on this checkout for
SubprocessPlanningAgent's JsonSubprocessAgent backend, so re-implementing that call here
would just fork a second, disconnected way of doing the same thing this session already
does directly.

This module's job is narrower and honest about that: locate a PolyJarvis run's directory
and confirm it reached a terminal state, for the harness CLI to hand off to metrics/.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from config import REPO_ROOT


def run_dir_for(polymer_name: str) -> Path:
    return REPO_ROOT / "data" / polymer_name


def campaign_status(polymer_name: str) -> dict:
    """Best-effort status snapshot without importing orchestration internals (keeps this
    harness decoupled from orchestration/scripts' sys.path setup)."""
    run_dir = run_dir_for(polymer_name)
    control_path = run_dir / "raw" / "control_state.json"
    workflow_path = run_dir / "workflow_state.json"

    if not control_path.is_file() and not workflow_path.is_file():
        return {"status": "not_found", "run_name": polymer_name}

    result: dict = {"run_name": polymer_name}
    if control_path.is_file():
        control = json.loads(control_path.read_text())
        result["control_status"] = control.get("status")
    if workflow_path.is_file():
        workflow = json.loads(workflow_path.read_text())
        stage_statuses = {
            name: rec.get("status") for name, rec in (workflow.get("stages") or {}).items()
        }
        result["stage_statuses"] = stage_statuses
        result["complete"] = bool(stage_statuses) and all(
            s == "accepted" for s in stage_statuses.values()
        )
    return result
