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
    FilePlanningAgent,
    JsonSubprocessAgent,
    PlanningAgent,
    RecoveryAgent,
    ScientificControlPlane,
    ScientificIntent,
    SubprocessPlanningAgent,
    SubprocessRecoveryAgent,
)
from run_campaign import run_campaign_workflow  # noqa: E402
from workflow_engine import inspect_workflow  # noqa: E402


AVAILABLE_ACTIONS = ("start", "resume", "inspect", "run_scientific_campaign")
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
        workflow=DeterministicScriptChain(repo_root=repo_root, recovery_agent=recovery_agent),
        # Recovery is owned by WorkflowEngine; the outer control plane must not make a
        # second, unrecorded agent call for the same finding.
        recovery_agent=None,
        repo_root=repo_root,
    ).run(intent, dry_run=dry_run)


def resume_campaign(run_name: str, recovery_agent: Optional[RecoveryAgent] = None,
                    dry_run: bool = False, repo_root: Path = REPO_ROOT) -> dict:
    """Resume from the earliest stale or incomplete stage in durable workflow state."""
    plan_path = repo_root / "data" / run_name / "raw" / "run_plan.json"
    if not plan_path.exists():
        # New engine-native callers may keep the immutable plan at the run root.
        plan_path = repo_root / "data" / run_name / "run_plan.json"
    if not plan_path.exists():
        return {"status": "not_found", "run_name": run_name, "plan_path": str(plan_path)}
    return run_campaign_workflow(plan_path, dry_run=dry_run, repo_root=repo_root,
                                 recovery_agent=recovery_agent)


def inspect_run(run_name: str, repo_root: Path = REPO_ROOT) -> dict:
    """Read structured control and executor state without parsing prose logs."""
    run_dir = repo_root / "data" / run_name
    workflow_result = inspect_workflow(run_dir)
    raw_dir = run_dir / "raw"
    control_path = raw_dir / "control_state.json"
    executor_path = raw_dir / "executor_state.json"
    if (workflow_result["status"] == "not_found" and not control_path.exists()
            and not executor_path.exists()):
        return {
            "status": "not_found",
            "run_name": run_name,
            "control_state_path": str(control_path),
            "executor_state_path": str(executor_path),
        }
    control = json.loads(control_path.read_text()) if control_path.exists() else None
    executor = json.loads(executor_path.read_text()) if executor_path.exists() else None
    if workflow_result["status"] != "not_found":
        status = workflow_result["status"]
    elif control:
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
        "workflow": workflow_result.get("state"),
        "workflow_state_path": workflow_result["state_path"],
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
    start_parser = subparsers.add_parser("start")
    start_parser.add_argument("--run-name", required=True)
    start_parser.add_argument("--goal", required=True)
    start_parser.add_argument("--smiles", required=True)
    start_parser.add_argument("--properties", required=True)
    start_parser.add_argument("--polymer-class-hint")
    start_source = start_parser.add_mutually_exclusive_group(required=True)
    start_source.add_argument("--scientific-agent-command")
    start_source.add_argument("--decision-file", type=Path)
    start_parser.add_argument("--recovery-agent-command")
    start_parser.add_argument("--dry-run", action="store_true")
    resume_parser = subparsers.add_parser("resume")
    resume_parser.add_argument("run_name")
    resume_parser.add_argument("--recovery-agent-command")
    resume_parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.action == "contract":
        result = interface_contract()
    elif args.action == "inspect":
        result = inspect_run(args.run_name)
    elif args.action == "resume":
        recovery = (SubprocessRecoveryAgent(JsonSubprocessAgent(args.recovery_agent_command.split()))
                    if args.recovery_agent_command else None)
        result = resume_campaign(args.run_name, recovery, args.dry_run)
    else:
        intent = ScientificIntent(
            run_name=args.run_name, goal=args.goal, smiles=args.smiles,
            requested_properties=tuple(item.strip() for item in args.properties.split(",")
                                       if item.strip()),
            polymer_class_hint=args.polymer_class_hint,
        )
        planning = (FilePlanningAgent(args.decision_file) if args.decision_file else
                    SubprocessPlanningAgent(JsonSubprocessAgent(
                        args.scientific_agent_command.split())))
        recovery = (SubprocessRecoveryAgent(JsonSubprocessAgent(args.recovery_agent_command.split()))
                    if args.recovery_agent_command else None)
        result = run_scientific_campaign(intent, planning, recovery, args.dry_run)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
