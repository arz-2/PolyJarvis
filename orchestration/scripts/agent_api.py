#!/usr/bin/env python3
"""Public PolyJarvis agent API; execution cannot bypass scientific planning."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

from scientific_control import (  # noqa: E402
    DeterministicScriptChain,
    PlanningAgent,
    RecoveryAgent,
    ScientificControlPlane,
    ScientificIntent,
)


AVAILABLE_ACTIONS = ("run_scientific_campaign", "inspect_run")
RULES = (
    "A scientific planning agent must decide the run plan before execution.",
    "Agents never modify simulation files, commands, or output paths.",
    "All simulation operations run through the deterministic stage chain.",
    "The recovery agent is called only after a structured issue is detected.",
    "Recovery stops after two failed attempts.",
)


def run_scientific_campaign(
    intent: ScientificIntent,
    planning_agent: PlanningAgent,
    recovery_agent: Optional[RecoveryAgent] = None,
    dry_run: bool = False,
    repo_root: Path = REPO_ROOT,
) -> dict:
    """Run the enforced agent-plan → deterministic-chain → conditional-recovery flow."""
    return ScientificControlPlane(
        planning_agent=planning_agent,
        workflow=DeterministicScriptChain(),
        recovery_agent=recovery_agent,
        repo_root=repo_root,
    ).run(intent, dry_run=dry_run)


def inspect_run(run_name: str, repo_root: Path = REPO_ROOT) -> dict:
    """Read structured control and executor state without parsing prose logs."""
    raw_dir = repo_root / "data" / run_name / "raw"
    control_path = raw_dir / "control_state.json"
    executor_path = raw_dir / "executor_state.json"
    if not control_path.exists() and not executor_path.exists():
        return {
            "status": "not_found",
            "run_name": run_name,
            "control_state_path": str(control_path),
            "executor_state_path": str(executor_path),
        }
    control = json.loads(control_path.read_text()) if control_path.exists() else None
    executor = json.loads(executor_path.read_text()) if executor_path.exists() else None
    if control:
        status = control.get("status", "unknown")
    elif executor and executor.get("halted"):
        status = "halted"
    else:
        status = "active_or_complete"
    return {
        "status": status,
        "run_name": run_name,
        "control": control,
        "executor": executor,
        "control_state_path": str(control_path),
        "executor_state_path": str(executor_path),
    }


def interface_contract() -> dict:
    return {"available_actions": AVAILABLE_ACTIONS, "rules": RULES}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)
    subparsers.add_parser("contract")
    inspect_parser = subparsers.add_parser("inspect")
    inspect_parser.add_argument("run_name")
    args = parser.parse_args()
    result = interface_contract() if args.action == "contract" else inspect_run(args.run_name)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
