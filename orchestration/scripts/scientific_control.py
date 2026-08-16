#!/usr/bin/env python3
"""Agentic scientific decisions over a deterministic PolyJarvis script chain."""

from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Protocol, Sequence


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

from hw_common import get_class_entry, load_rules  # noqa: E402
from make_deterministic_plan import build_decisions, build_planned_stages, make_plan  # noqa: E402


VALID_PROPERTIES = frozenset({"density", "tg", "bulk_modulus"})
VALID_CONFIDENCE = frozenset({"low", "medium", "high"})
VALID_RECOVERY_ACTIONS = frozenset({"retry", "revise_plan", "stop"})
MAX_RECOVERY_ATTEMPTS = 2

# Agents may select scientific values, never paths, commands, generated files, or raw decks.
OVERRIDE_RANGES: dict[str, tuple[Optional[float], Optional[float]]] = {
    "dp_typical": (20, 1000),
    "nchain": (1, 500),
    "density_initial_gcm3": (0.05, 3.0),
    "dt_fs": (0.1, 5.0),
    "T_equil_K": (100, 1500),
    "annealing_T_high_K": (100, 2000),
    "T_workflow_K": (100, 1500),
    "npt_prod_ns": (0.05, 1000),
    "npt_cool_steps": (1, 2_000_000_000),
    "npt_cool300_steps": (1, 2_000_000_000),
    "melt_hold_ns": (0.01, 1000),
    "melt_only_continuation_ns": (0.01, 1000),
    "tg_t_high_K": (100, 2000),
    "tg_t_low_K": (1, 1500),
    "tg_t_step_K": (1, 200),
    "tg_min_steps_per_T": (1, 2_000_000_000),
    "tg_steps_per_t": (1, 2_000_000_000),
    "K_strain_max": (0.001, 0.25),
    "K_deform_rate_inv_s": (1e3, 1e12),
    "K_deform_rate_slow_inv_s": (1e3, 1e12),
    "cutoff_A": (3, 30),
    "gpu_per_run": (0, 16),
    "mpi_ranks": (1, 256),
}
ENUM_OVERRIDES = {
    "preferred_builder": frozenset({"emc", "radonpy"}),
    "preferred_ff": frozenset({"pcff", "pcff_ore", "compass", "opls/2024/opls-aa", "trappe", "gaff2", "gaff2_mod"}),
    "charge_method": frozenset({"none", "embedded", "gasteiger", "am1bcc", "resp"}),
    "electrostatics": frozenset({"pppm", "lj_cut"}),
    "engine": frozenset({"gpu", "kokkos", "cpu"}),
}
SEQUENCE_OVERRIDES = frozenset({"tg_rates_K_per_ns", "bm_pressures_atm", "backbone_types"})
ALLOWED_OVERRIDES = frozenset(OVERRIDE_RANGES) | frozenset(ENUM_OVERRIDES) | SEQUENCE_OVERRIDES


@dataclass(frozen=True)
class ScientificIntent:
    run_name: str
    goal: str
    smiles: str
    requested_properties: tuple[str, ...] = ()
    polymer_class_hint: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class PlanDecision:
    polymer_class: str
    properties: tuple[str, ...]
    rationale: tuple[str, ...]
    overrides: dict[str, Any] = field(default_factory=dict)
    decision_evaluations: dict[str, dict[str, Any]] = field(default_factory=dict)
    assumptions: tuple[str, ...] = ()
    dominant_uncertainty: str = "protocol_transferability"
    confidence: str = "medium"

    @classmethod
    def from_dict(cls, value: dict) -> "PlanDecision":
        return cls(
            polymer_class=str(value["polymer_class"]).upper(),
            properties=tuple(value.get("properties") or ()),
            rationale=tuple(value.get("rationale") or ()),
            overrides=dict(value.get("overrides") or {}),
            decision_evaluations=dict(value.get("decision_evaluations") or {}),
            assumptions=tuple(value.get("assumptions") or ()),
            dominant_uncertainty=str(value.get("dominant_uncertainty") or "protocol_transferability"),
            confidence=str(value.get("confidence") or "medium").lower(),
        )


@dataclass(frozen=True)
class RecoveryDecision:
    action: str
    rationale: str
    modifications: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: dict) -> "RecoveryDecision":
        return cls(
            action=str(value["action"]).lower(),
            rationale=str(value.get("rationale") or ""),
            modifications=dict(value.get("modifications") or {}),
        )


@dataclass(frozen=True)
class WorkflowIssue:
    stage: str
    code: str
    detail: dict[str, Any]
    attempt: int

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class WorkflowOutcome:
    status: str
    result: dict[str, Any]
    issue: Optional[WorkflowIssue] = None
    steps: tuple[dict[str, Any], ...] = ()


class PlanningAgent(Protocol):
    def decide(self, intent: ScientificIntent, context: dict[str, Any]) -> PlanDecision: ...


class RecoveryAgent(Protocol):
    def diagnose(self, intent: ScientificIntent, plan: dict, issue: WorkflowIssue) -> RecoveryDecision: ...


class Workflow(Protocol):
    def execute(self, plan_path: Path, dry_run: bool = False, attempt: int = 0) -> WorkflowOutcome: ...


class JsonSubprocessAgent:
    """Model-provider-neutral agent adapter using JSON stdin/stdout and no shell."""

    def __init__(self, command: Sequence[str]):
        if not command:
            raise ValueError("agent command cannot be empty")
        self.command = tuple(command)

    def invoke(self, payload: dict) -> dict:
        completed = subprocess.run(
            self.command,
            input=json.dumps(payload),
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                f"agent command failed ({completed.returncode}): {completed.stderr.strip()}"
            )
        try:
            result = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError("agent command did not return one JSON object") from exc
        if not isinstance(result, dict):
            raise RuntimeError("agent command result must be a JSON object")
        return result


class SubprocessPlanningAgent:
    def __init__(self, backend: JsonSubprocessAgent):
        self.backend = backend

    def decide(self, intent: ScientificIntent, context: dict[str, Any]) -> PlanDecision:
        result = self.backend.invoke({
            "task": "plan_polymer_simulation",
            "intent": intent.to_dict(),
            "context": context,
            "output_contract": {
                "polymer_class": "configured class id",
                "properties": sorted(VALID_PROPERTIES),
                "rationale": ["scientific decision rationale"],
                "overrides": {"allowed_keys": sorted(ALLOWED_OVERRIDES)},
                "decision_evaluations": {
                    "D-01_ff": {
                        "criteria_evaluated": ["policy criterion"],
                        "evidence": [{"claim": "support", "source_doi": "DOI"}],
                        "alternatives": ["considered alternative"],
                    }
                },
                "assumptions": ["explicit assumption"],
                "dominant_uncertainty": "one short name",
                "confidence": sorted(VALID_CONFIDENCE),
            },
        })
        return PlanDecision.from_dict(result)


class SubprocessRecoveryAgent:
    def __init__(self, backend: JsonSubprocessAgent):
        self.backend = backend

    def diagnose(self, intent: ScientificIntent, plan: dict, issue: WorkflowIssue) -> RecoveryDecision:
        result = self.backend.invoke({
            "task": "diagnose_polymer_simulation_issue",
            "intent": intent.to_dict(),
            "plan_summary": _plan_summary(plan),
            "issue": issue.to_dict(),
            "output_contract": {
                "action": sorted(VALID_RECOVERY_ACTIONS),
                "rationale": "diagnosis and justification",
                "modifications": {"allowed_keys": sorted(ALLOWED_OVERRIDES)},
            },
        })
        return RecoveryDecision.from_dict(result)


class FilePlanningAgent:
    """Replays a captured scientific-agent decision for testing or audited execution."""

    def __init__(self, path: Path):
        self.path = path

    def decide(self, intent: ScientificIntent, context: dict[str, Any]) -> PlanDecision:
        return PlanDecision.from_dict(json.loads(self.path.read_text()))


def planning_context(intent: ScientificIntent) -> dict[str, Any]:
    rules = load_rules()
    classes = rules.get("classes", {})
    summaries = {}
    for class_id, entry in classes.items():
        summaries[class_id] = {
            "name": entry.get("name") or entry.get("polymer_name"),
            "preferred_builder": entry.get("preferred_builder", "emc"),
            "preferred_ff": entry.get("preferred_ff"),
            "experimental_tg_K": entry.get("experimental_tg_K"),
            "supported_properties": sorted(VALID_PROPERTIES),
        }
    policy = json.loads((REPO_ROOT / "orchestration" / "decision_policy.json").read_text())
    cache_path = REPO_ROOT / "guides" / "system_characterization_cache.json"
    characterization_cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    characterization = characterization_cache.get(intent.smiles)
    decision_framework = {}
    for policy_entry in policy.get("policies", {}).values():
        decision_id = policy_entry.get("decision_id")
        if decision_id:
            decision_framework[decision_id] = {
                "criteria": policy_entry.get("evaluate", []),
                "evidence_required": bool(policy_entry.get("evidence_required")),
                "default_source": policy_entry.get("default_source"),
            }
    return {
        "available_classes": summaries,
        "class_hint": intent.polymer_class_hint,
        "exact_smiles_characterization": characterization,
        "decision_framework": decision_framework,
        "rules": [
            "Choose scientific protocol values only; never produce scripts or file paths.",
            "Prefer class defaults unless the goal or chemistry justifies an override.",
            "Name assumptions and one dominant uncertainty.",
        ],
    }


def materialize_plan(intent: ScientificIntent, decision: PlanDecision) -> dict:
    """Convert a narrow agent decision into a complete executable run plan."""
    _validate_decision(decision)
    properties = set(decision.properties or intent.requested_properties)
    plan = make_plan(intent.run_name, decision.polymer_class, intent.smiles, properties)
    rules = load_rules()
    class_entry = dict(get_class_entry(rules, decision.polymer_class, warn_on_miss=False))
    effective_class = {**class_entry, **decision.overrides}
    plan["decided_params"].update(decision.overrides)
    if "T_equil_K" in decision.overrides and "T_workflow_K" not in decision.overrides:
        plan["decided_params"]["T_workflow_K"] = decision.overrides["T_equil_K"]
        effective_class["T_workflow_K"] = decision.overrides["T_equil_K"]
    plan["planned_stages"] = build_planned_stages(effective_class, properties)
    plan["decisions"] = build_decisions(effective_class)
    for row in plan["decisions"]:
        row["confidence"] = decision.confidence
        evaluation = decision.decision_evaluations.get(row["id"])
        if evaluation:
            if "criteria_evaluated" in evaluation:
                row["criteria_evaluated"] = list(evaluation["criteria_evaluated"])
            if "evidence" in evaluation:
                row["evidence"] = list(evaluation["evidence"])
            if "alternatives" in evaluation:
                row["alternatives"] = list(evaluation["alternatives"])
    plan.update({
        "goal": intent.goal,
        "properties": sorted(properties),
        "confidence": decision.confidence,
        "plan_mode": "reasoned",
        "assumptions": list(decision.assumptions),
        "uncertainties": [{
            "name": decision.dominant_uncertainty,
            "dominant": True,
            "reduction_probe": "none",
        }],
        "critique": {
            "status": "scientific_agent_decision",
            "rounds": 1,
            "findings": list(decision.rationale),
        },
    })
    decision_payload = asdict(decision)
    plan["provenance"] = {
        "generator": "scientific_control.py",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "decision_sha256": hashlib.sha256(
            json.dumps(decision_payload, sort_keys=True, default=list).encode()
        ).hexdigest(),
        "agent_rationale": list(decision.rationale),
    }
    return plan


def apply_recovery(plan: dict, decision: RecoveryDecision) -> dict:
    """Apply only validated protocol modifications; agents never edit run files."""
    if decision.action not in VALID_RECOVERY_ACTIONS:
        raise ValueError(f"invalid recovery action {decision.action!r}")
    _validate_overrides(decision.modifications)
    revised = json.loads(json.dumps(plan))
    revised["decided_params"].update(decision.modifications)
    by_id = {row.get("id"): row for row in revised.get("decisions", [])}
    decided_params = revised["decided_params"]
    if "preferred_ff" in decision.modifications and "D-01_ff" in by_id:
        by_id["D-01_ff"]["choice"] = decided_params["preferred_ff"]
    if "charge_method" in decision.modifications and "D-02_charges" in by_id:
        by_id["D-02_charges"]["choice"] = decided_params["charge_method"]
    if "electrostatics" in decision.modifications and "D-03_electrostatics" in by_id:
        by_id["D-03_electrostatics"]["choice"] = decided_params["electrostatics"]
    if {"dp_typical", "nchain"} & set(decision.modifications) and "D-04_system_size" in by_id:
        by_id["D-04_system_size"]["choice"] = (
            f"DP={decided_params.get('dp_typical')}, nchain={decided_params.get('nchain')}"
        )
    class_entry = dict(get_class_entry(load_rules(), revised["polymer_class"], warn_on_miss=False))
    effective_class = {**class_entry, **decided_params}
    revised["planned_stages"] = build_planned_stages(
        effective_class, set(revised.get("properties", []))
    )
    revised.setdefault("recovery_history", []).append({
        "action": decision.action,
        "rationale": decision.rationale,
        "modifications": decision.modifications,
        "at": datetime.now(timezone.utc).isoformat(),
    })
    return revised


class DeterministicScriptChain:
    """Validate a plan, then run the in-process durable workflow engine."""

    def __init__(self, python: str = sys.executable, repo_root: Path = REPO_ROOT,
                 recovery_agent: Optional[RecoveryAgent] = None):
        self.python = python
        self.repo_root = repo_root
        self.recovery_agent = recovery_agent
        self.validator = SCRIPT_DIR / "validate_run_plan.py"

    def execute(self, plan_path: Path, dry_run: bool = False, attempt: int = 0) -> WorkflowOutcome:
        plan = json.loads(plan_path.read_text())
        steps = []
        validation = subprocess.run(
            [self.python, str(self.validator), "--run_plan", str(plan_path)],
            capture_output=True,
            text=True,
        )
        validation_result = _last_json_value(validation.stdout) or {}
        steps.append({"step": "validate_run_plan", "returncode": validation.returncode,
                      "result": validation_result})
        structural = [finding for finding in validation_result.get("findings", [])
                      if finding.get("severity") == "structural"]
        if validation.returncode != 0 or structural:
            issue = WorkflowIssue(
                stage="validate_run_plan",
                code="PLAN_VALIDATION_FAILED",
                detail={"findings": structural, "stderr": validation.stderr.strip()},
                attempt=attempt,
            )
            return WorkflowOutcome("issue", validation_result, issue, tuple(steps))

        from run_campaign import run_campaign_workflow

        execution_result = run_campaign_workflow(
            plan_path, dry_run=dry_run, repo_root=self.repo_root,
            recovery_agent=self.recovery_agent,
        )
        steps.append({"step": "resolve_stage_params" if dry_run else "workflow_engine",
                      "result": execution_result})
        if dry_run or execution_result.get("status") == "accepted":
            return WorkflowOutcome("complete", execution_result, None, tuple(steps))
        finding = execution_result.get("finding") or {}
        issue = WorkflowIssue(
            stage=execution_result.get("stage", "workflow"),
            code=finding.get("code", execution_result.get("reason", "CAMPAIGN_FAILED")),
            detail={"result": execution_result, "finding": finding},
            attempt=attempt,
        )
        return WorkflowOutcome("issue", execution_result, issue, tuple(steps))


class ScientificControlPlane:
    def __init__(
        self,
        planning_agent: PlanningAgent,
        workflow: Workflow,
        recovery_agent: Optional[RecoveryAgent] = None,
        repo_root: Path = REPO_ROOT,
    ):
        self.planning_agent = planning_agent
        self.workflow = workflow
        self.recovery_agent = recovery_agent
        self.repo_root = repo_root

    def run(self, intent: ScientificIntent, dry_run: bool = False) -> dict:
        events = []
        context = planning_context(intent)
        for planning_attempt in range(2):
            try:
                decision = self.planning_agent.decide(intent, context)
                events.append({"event": "scientific_agent_called",
                               "attempt": planning_attempt + 1})
                plan = materialize_plan(intent, decision)
                break
            except Exception as exc:
                events.append({"event": "scientific_agent_contract_error",
                               "attempt": planning_attempt + 1, "error": str(exc)})
                if planning_attempt:
                    raise ValueError(
                        "PLAN_AGENT_CONTRACT_ERROR: planning agent failed validation twice"
                    ) from exc
                context = {**context, "validation_feedback": {
                    "code": "PLAN_AGENT_CONTRACT_ERROR", "error": str(exc),
                    "instruction": "Return one JSON decision satisfying the output contract.",
                }}
        run_dir = self.repo_root / "data" / intent.run_name / "raw"
        run_dir.mkdir(parents=True, exist_ok=True)
        plan_path = run_dir / "run_plan.json"
        _write_json(plan_path, plan)
        events.append({"event": "plan_materialized", "path": str(plan_path)})

        for attempt in range(MAX_RECOVERY_ATTEMPTS + 1):
            outcome = self.workflow.execute(plan_path, dry_run=dry_run, attempt=attempt)
            events.append({"event": "deterministic_chain_finished", "attempt": attempt,
                           "status": outcome.status, "steps": list(outcome.steps)})
            if outcome.issue is None:
                engine_calls = 0
                state_path = outcome.result.get("state_path") if isinstance(outcome.result, dict) else None
                if state_path and Path(state_path).exists():
                    try:
                        engine_calls = len(json.loads(Path(state_path).read_text()).get(
                            "agent_escalations", []))
                    except (OSError, json.JSONDecodeError):
                        pass
                result = {
                    "status": "complete",
                    "run_name": intent.run_name,
                    "plan_path": str(plan_path),
                    "result": outcome.result,
                    "events": events,
                    "recovery_agent_calls": engine_calls,
                }
                self._save_control_state(intent.run_name, result)
                return result

            events.append({"event": "issue_detected", "issue": outcome.issue.to_dict()})
            if self.recovery_agent is None:
                engine_calls = 0
                state_path = outcome.result.get("state_path") if isinstance(outcome.result, dict) else None
                if state_path and Path(state_path).exists():
                    try:
                        engine_calls = len(json.loads(Path(state_path).read_text()).get(
                            "agent_escalations", []))
                    except (OSError, json.JSONDecodeError):
                        pass
                engine_terminal = outcome.result.get("status") in {"failed", "escalation_required"}
                result = {
                    "status": ("unresolved" if engine_calls and engine_terminal
                               else "needs_recovery_agent"),
                    "run_name": intent.run_name,
                    "plan_path": str(plan_path),
                    "issue": outcome.issue.to_dict(),
                    "events": events,
                    "recovery_agent_calls": engine_calls,
                }
                self._save_control_state(intent.run_name, result)
                return result
            if attempt >= MAX_RECOVERY_ATTEMPTS:
                result = {
                    "status": "unresolved",
                    "run_name": intent.run_name,
                    "plan_path": str(plan_path),
                    "issue": outcome.issue.to_dict(),
                    "events": events,
                    "recovery_agent_calls": MAX_RECOVERY_ATTEMPTS,
                }
                self._save_control_state(intent.run_name, result)
                return result

            recovery = self.recovery_agent.diagnose(intent, plan, outcome.issue)
            events.append({"event": "recovery_agent_called", "attempt": attempt + 1,
                           "decision": asdict(recovery)})
            if recovery.action == "stop":
                result = {
                    "status": "unresolved",
                    "run_name": intent.run_name,
                    "plan_path": str(plan_path),
                    "issue": outcome.issue.to_dict(),
                    "events": events,
                    "recovery_agent_calls": attempt + 1,
                }
                self._save_control_state(intent.run_name, result)
                return result
            plan = apply_recovery(plan, recovery)
            _write_json(plan_path, plan)

        raise AssertionError("recovery loop exhausted without terminal result")

    def _save_control_state(self, run_name: str, result: dict) -> None:
        path = self.repo_root / "data" / run_name / "raw" / "control_state.json"
        _write_json(path, result)


def _validate_decision(decision: PlanDecision) -> None:
    if not decision.rationale:
        raise ValueError("scientific agent must provide at least one rationale")
    if decision.confidence not in VALID_CONFIDENCE:
        raise ValueError(f"invalid confidence {decision.confidence!r}")
    properties = set(decision.properties)
    if not properties or not properties <= VALID_PROPERTIES:
        raise ValueError(f"properties must be a non-empty subset of {sorted(VALID_PROPERTIES)}")
    rules = load_rules()
    if decision.polymer_class not in rules.get("classes", {}):
        raise ValueError(f"unknown polymer class {decision.polymer_class!r}")
    _validate_overrides(decision.overrides)
    known_decisions = {row["id"] for row in build_decisions(
        get_class_entry(rules, decision.polymer_class, warn_on_miss=False)
    )}
    unknown_decisions = set(decision.decision_evaluations) - known_decisions
    if unknown_decisions:
        raise ValueError(f"unknown decision evaluations: {sorted(unknown_decisions)}")


def _validate_overrides(overrides: dict[str, Any]) -> None:
    unknown = set(overrides) - ALLOWED_OVERRIDES
    if unknown:
        raise ValueError(f"agent attempted unsupported overrides: {sorted(unknown)}")
    for key, value in overrides.items():
        if key in OVERRIDE_RANGES:
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise ValueError(f"{key} must be numeric")
            lower, upper = OVERRIDE_RANGES[key]
            if lower is not None and value < lower or upper is not None and value > upper:
                raise ValueError(f"{key}={value} outside allowed range [{lower}, {upper}]")
        elif key in ENUM_OVERRIDES and value not in ENUM_OVERRIDES[key]:
            raise ValueError(f"{key}={value!r} not in {sorted(ENUM_OVERRIDES[key])}")
        elif key in SEQUENCE_OVERRIDES:
            if not isinstance(value, list) or not value:
                raise ValueError(f"{key} must be a non-empty JSON list")
            if not all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in value):
                raise ValueError(f"{key} values must be numeric")


def _plan_summary(plan: dict) -> dict:
    return {
        "run_name": plan.get("run_name"),
        "polymer_class": plan.get("polymer_class"),
        "properties": plan.get("properties"),
        "decided_params": plan.get("decided_params"),
        "recovery_history": plan.get("recovery_history", []),
    }


def _last_json_value(text: str):
    decoder = json.JSONDecoder()
    for index in reversed([i for i, char in enumerate(text) if char in "[{"]):
        try:
            value, end = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if not text[index + end:].strip():
            return value
    return None


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, default=list) + "\n")
    temporary.replace(path)


def _read_executor_state(run_name: str) -> dict:
    path = REPO_ROOT / "data" / run_name / "raw" / "executor_state.json"
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-name", required=True)
    parser.add_argument("--goal", required=True)
    parser.add_argument("--smiles", required=True)
    parser.add_argument("--properties", default="")
    parser.add_argument("--polymer-class-hint")
    planning = parser.add_mutually_exclusive_group(required=True)
    planning.add_argument("--scientific-agent-command")
    planning.add_argument("--decision-file")
    parser.add_argument("--recovery-agent-command")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    intent = ScientificIntent(
        run_name=args.run_name,
        goal=args.goal,
        smiles=args.smiles,
        requested_properties=tuple(p.strip() for p in args.properties.split(",") if p.strip()),
        polymer_class_hint=args.polymer_class_hint,
    )
    if args.decision_file:
        planning_agent: PlanningAgent = FilePlanningAgent(Path(args.decision_file))
    else:
        planning_agent = SubprocessPlanningAgent(
            JsonSubprocessAgent(shlex.split(args.scientific_agent_command))
        )
    recovery_agent: Optional[RecoveryAgent] = None
    if args.recovery_agent_command:
        recovery_agent = SubprocessRecoveryAgent(
            JsonSubprocessAgent(shlex.split(args.recovery_agent_command))
        )
    result = ScientificControlPlane(
        planning_agent=planning_agent,
        workflow=DeterministicScriptChain(),
        recovery_agent=recovery_agent,
    ).run(intent, dry_run=args.dry_run)
    print(json.dumps(result, indent=2, default=list))


if __name__ == "__main__":
    main()
