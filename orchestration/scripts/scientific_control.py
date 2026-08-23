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
import canon_smiles  # noqa: E402  -- module import so tests can monkeypatch canon_smiles.canonicalize


VALID_PROPERTIES = frozenset({"density", "tg", "bulk_modulus"})
VALID_CONFIDENCE = frozenset({"low", "medium", "high"})
VALID_RECOVERY_ACTIONS = frozenset({"retry", "revise_plan", "stop"})
MAX_RECOVERY_ATTEMPTS = 2

# Agents may select scientific values, never paths, commands, generated files, or raw decks.
OVERRIDE_RANGES: dict[str, tuple[Optional[float], Optional[float]]] = {
    "dp_typical": (20, 1000),
    "nchain": (1, 500),
    "density_initial_gcm3": (0.05, 3.0),
    "build_temperature_K": (1, 2000),
    "dt_fs": (0.1, 5.0),
    "T_equil_K": (100, 1500),
    "annealing_T_high_K": (100, 2000),
    "T_workflow_K": (100, 1500),
    # A scalar replaces the class's (possibly multi-member-dict, possibly absent)
    # experimental_tg_K wholesale via apply_plan's {**cls, **decided_params} overlay --
    # _exp_tg_point already has an isinstance(tg, (int, float)) passthrough for exactly this
    # shape. Lets the planning agent pin the correct experimental target when
    # it has reasoned one out (multi-member disambiguation by substituent, a literature value,
    # or an accepted group-contribution estimate for a genuinely novel SMILES) instead of
    # relying on run_name-prefix matching against the class dict.
    "experimental_tg_K": (1, 1500),
    # Same rationale as experimental_tg_K: a scalar replaces the class's (possibly
    # multi-member-dict, possibly absent) experimental_density_gcm3 wholesale.
    "experimental_density_gcm3": (0.05, 3.0),
    # exp_K_GPa is a flat {min,max} PER CLASS, not per-member -- e.g. PACR's is scoped to PMMA
    # specifically even though PACR also covers PMA (see the class's own note). There is no
    # existing per-member resolution to fix; these let the agent pin the correct range for
    # whichever member this SMILES actually is.
    "exp_K_min_GPa": (0.001, 200),
    "exp_K_max_GPa": (0.001, 200),
    "P_equil_atm": (0.01, 100000),
    "final_T_K": (1, 1500),
    "anneal_margin_K": (1, 1000),
    "compression_max_pressure_atm": (1, 1_000_000),
    "warmup_steps": (1, 2_000_000_000),
    "densify_ramp_steps": (1, 2_000_000_000),
    "densify_check_every_steps": (1, 2_000_000_000),
    "densify_steps_cap": (1, 2_000_000_000),
    "ff_activate_npt_steps": (1, 2_000_000_000),
    "anneal_heat_steps": (1, 2_000_000_000),
    "anneal_check_every_steps": (1, 2_000_000_000),
    "anneal_cap_steps": (1, 2_000_000_000),
    "cool_block_dT_K": (1, 500),
    "cool_block_hold_steps": (1, 2_000_000_000),
    "cool_block_hold_cap_steps": (1, 2_000_000_000),
    "stage7_min_steps": (1, 2_000_000_000),
    "stage7_cap_steps": (1, 2_000_000_000),
    "stage8_min_steps": (1, 2_000_000_000),
    "stage8_cap_steps": (1, 2_000_000_000),
    "melt_hold_ns": (0.01, 1000),
    "melt_only_continuation_ns": (0.01, 1000),
    "thermostat_damp_fs": (1, 100000),
    "barostat_damp_fs": (1, 1_000_000),
    "alpha_glass_per_K": (0.0, 0.1),
    "alpha_melt_per_K": (0.0, 0.1),
    "ct_min_decay_melt": (0.0, 1.0),
    "tg_t_high_K": (100, 2000),
    "tg_t_low_K": (1, 1500),
    "tg_t_step_K": (1, 200),
    "tg_min_steps_per_T": (1, 2_000_000_000),
    "tg_steps_per_t": (1, 2_000_000_000),
    "tg_primary_rate_index": (0, 100),
    "K_strain_max": (0.001, 0.25),
    "K_deform_rate_inv_s": (1e3, 1e12),
    "K_deform_rate_slow_inv_s": (1e3, 1e12),
    "deform_eq_steps": (0, 2_000_000_000),
    "deform_strain_start": (0.0, 0.25),
    "deform_avg_window": (1, 10_000_000),
    "bm_npt_steps": (1, 2_000_000_000),
    "bm_temperature_K": (1, 2000),
    "bm_thermo_freq": (1, 10_000_000),
    "cutoff_A": (3, 30),
    "emc_seed": (1, 999_999_999),
    "velocity_seed": (1, 999_999_999),
    "gpu_per_run": (0, 16),
    "mpi_ranks": (1, 256),
    # Recovery-only levers the automatic remedy ladder itself writes (workflow_engine.py's
    # _continue_npt/_murnaghan_resample) -- an agent picking a different value for the same
    # lever needs the same bounds the ladder is held to.
    "npt_continuation_ns": (0.01, 1000),
    "mechanical_sampling_factor": (1, 10),
}
ENUM_OVERRIDES = {
    "preferred_builder": frozenset({"emc", "radonpy"}),
    "preferred_ff": frozenset({"pcff", "pcff_ore", "compass", "opls/2024/opls-aa", "trappe", "gaff2", "gaff2_mod"}),
    "charge_method": frozenset({"none", "embedded", "bond-increment", "opls-library",
                                  "gasteiger", "am1bcc", "am1-bcc", "resp"}),
    "electrostatics": frozenset({"pppm", "lj_cut"}),
    "engine": frozenset({"gpu", "kokkos", "cpu"}),
    "tg_slope_gate_fallback": frozenset({"highest_rate", "slowest_rate"}),
    "mechanical_method": frozenset({"murnaghan", "deformation"}),
    # The only values workflow_engine.py's _melt_hold/_cooling/_melt_homogeneity remedies
    # themselves ever set -- an agent has no sanctioned reason to pick a different one.
    "equilibration_phase": frozenset({"melt_then_cool", "melt_only"}),
    "cooling_resume_source": frozenset({"accepted_melt", "remedied_melt"}),
}
SEQUENCE_OVERRIDES = frozenset({"tg_rates_K_per_ns", "bm_pressures_atm", "backbone_types",
                                "mechanical_resample_points"})
BOOLEAN_OVERRIDES = frozenset({"add_melt_npt", "ct_gate_reliable"})
INTEGER_OVERRIDES = frozenset({
    "dp_typical", "nchain",
    "warmup_steps", "densify_ramp_steps", "densify_check_every_steps", "densify_steps_cap",
    "ff_activate_npt_steps", "anneal_heat_steps", "anneal_check_every_steps",
    "anneal_cap_steps", "cool_block_hold_steps", "cool_block_hold_cap_steps",
    "stage7_min_steps", "stage7_cap_steps", "stage8_min_steps", "stage8_cap_steps",
    "tg_min_steps_per_T", "tg_steps_per_t",
    "deform_eq_steps", "deform_avg_window", "bm_npt_steps", "bm_thermo_freq",
    "emc_seed", "velocity_seed", "gpu_per_run", "mpi_ranks", "tg_primary_rate_index",
    "mechanical_sampling_factor",
})
# Ladder bookkeeping (baseline_*, *_attempt, rerun_homogeneity_gate) is deliberately excluded
# from every table above: an agent may pick a lever's value, never rewrite the ladder's own
# accounting of what it already spent.
ALLOWED_OVERRIDES = (frozenset(OVERRIDE_RANGES) | frozenset(ENUM_OVERRIDES) |
                     SEQUENCE_OVERRIDES | BOOLEAN_OVERRIDES)


def planning_parameter_contract() -> dict[str, dict[str, Any]]:
    """Machine-readable scientific knobs available to planning and recovery agents."""
    contract = {
        key: {"type": "integer" if key in INTEGER_OVERRIDES else "number",
              "minimum": bounds[0], "maximum": bounds[1]}
        for key, bounds in OVERRIDE_RANGES.items()
    }
    contract.update({key: {"type": "enum", "values": sorted(values)}
                     for key, values in ENUM_OVERRIDES.items()})
    contract.update({key: {"type": "number_list", "nonempty": True}
                     for key in SEQUENCE_OVERRIDES})
    contract.update({key: {"type": "boolean"} for key in BOOLEAN_OVERRIDES})
    return contract


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
                "overrides": planning_parameter_contract(),
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
                "modifications": planning_parameter_contract(),
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
    canonical_smiles = None
    if intent.smiles:
        try:
            canonical_smiles = canon_smiles.canonicalize(intent.smiles, isomeric=True)
        except (RuntimeError, subprocess.TimeoutExpired):
            pass
    characterization = characterization_cache.get(canonical_smiles or intent.smiles)
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
        "planning_parameters": planning_parameter_contract(),
    }


def materialize_plan(intent: ScientificIntent, decision: PlanDecision) -> dict:
    """Convert a narrow agent decision into a complete executable run plan."""
    _validate_decision(decision)
    properties = set(decision.properties or intent.requested_properties)
    plan = make_plan(intent.run_name, decision.polymer_class, intent.smiles, properties)
    rules = load_rules()
    class_entry = dict(get_class_entry(rules, decision.polymer_class, warn_on_miss=False))
    effective_class = {**class_entry, **decision.overrides}
    _validate_protocol_relationships(effective_class, set(decision.overrides))
    plan["decided_params"].update(decision.overrides)
    if "T_equil_K" in decision.overrides and "T_workflow_K" not in decision.overrides:
        plan["decided_params"]["T_workflow_K"] = decision.overrides["T_equil_K"]
        effective_class["T_workflow_K"] = decision.overrides["T_equil_K"]
    plan["planned_stages"] = build_planned_stages(effective_class, properties, intent.smiles)
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
    validate_overrides(decision.modifications)
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
    _validate_protocol_relationships(effective_class, set(decision.modifications))
    revised["planned_stages"] = build_planned_stages(
        effective_class, set(revised.get("properties", [])), revised.get("smiles")
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
    validate_overrides(decision.overrides)
    known_decisions = {row["id"] for row in build_decisions(
        get_class_entry(rules, decision.polymer_class, warn_on_miss=False)
    )}
    unknown_decisions = set(decision.decision_evaluations) - known_decisions
    if unknown_decisions:
        raise ValueError(f"unknown decision evaluations: {sorted(unknown_decisions)}")


def validate_overrides(overrides: dict[str, Any]) -> None:
    unknown = set(overrides) - ALLOWED_OVERRIDES
    if unknown:
        raise ValueError(f"agent attempted unsupported overrides: {sorted(unknown)}")
    for key, value in overrides.items():
        if key in OVERRIDE_RANGES:
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise ValueError(f"{key} must be numeric")
            if key in INTEGER_OVERRIDES and not isinstance(value, int):
                raise ValueError(f"{key} must be an integer")
            lower, upper = OVERRIDE_RANGES[key]
            if lower is not None and value < lower or upper is not None and value > upper:
                raise ValueError(f"{key}={value} outside allowed range [{lower}, {upper}]")
        elif key in ENUM_OVERRIDES and value not in ENUM_OVERRIDES[key]:
            raise ValueError(f"{key}={value!r} not in {sorted(ENUM_OVERRIDES[key])}")
        elif key in BOOLEAN_OVERRIDES and not isinstance(value, bool):
            raise ValueError(f"{key} must be boolean")
        elif key in SEQUENCE_OVERRIDES:
            if not isinstance(value, list) or not value:
                raise ValueError(f"{key} must be a non-empty JSON list")
            if not all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in value):
                raise ValueError(f"{key} values must be numeric")
            if key in {"tg_rates_K_per_ns", "backbone_types"} and any(item <= 0 for item in value):
                raise ValueError(f"{key} values must be positive")


def _validate_protocol_relationships(parameters: dict[str, Any], changed: set[str]) -> None:
    """Reject internally inconsistent plans before any files or jobs are created."""
    t_low = parameters.get("tg_t_low_K")
    t_high = parameters.get("tg_t_high_K")
    if ({"tg_t_low_K", "tg_t_high_K"} & changed and
            t_low is not None and t_high is not None and t_low >= t_high):
        raise ValueError("tg_t_low_K must be lower than tg_t_high_K")

    strain_start = parameters.get("deform_strain_start")
    strain_max = parameters.get("K_strain_max")
    if ({"deform_strain_start", "K_strain_max"} & changed and
            strain_start is not None and strain_max is not None and strain_start >= strain_max):
        raise ValueError("deform_strain_start must be lower than K_strain_max")

    fast_rate = parameters.get("K_deform_rate_inv_s")
    slow_rate = parameters.get("K_deform_rate_slow_inv_s")
    if ({"K_deform_rate_inv_s", "K_deform_rate_slow_inv_s"} & changed and
            fast_rate is not None and slow_rate is not None and slow_rate > fast_rate):
        raise ValueError("K_deform_rate_slow_inv_s cannot exceed K_deform_rate_inv_s")

    rates = parameters.get("tg_rates_K_per_ns") or []
    primary_index = parameters.get("tg_primary_rate_index")
    if ({"tg_primary_rate_index", "tg_rates_K_per_ns"} & changed and
            primary_index is not None and not 0 <= primary_index < len(rates)):
        raise ValueError(
            f"tg_primary_rate_index={primary_index} outside planned rate list of length {len(rates)}"
        )
    if rates and ({"tg_rates_K_per_ns", "dt_fs", "tg_t_step_K",
                   "tg_min_steps_per_T"} & changed):
        dt_fs = parameters.get("dt_fs", 1.0)
        t_step = parameters.get("tg_t_step_K", 20.0)
        minimum_steps = parameters.get("tg_min_steps_per_T", 200000)
        infeasible = [rate for rate in rates
                      if t_step / (rate * dt_fs * 1e-6) < minimum_steps - 1]
        if infeasible:
            raise ValueError(
                "tg_rates_K_per_ns contains rates that violate tg_min_steps_per_T: "
                f"{infeasible}"
            )

    pressures = parameters.get("bm_pressures_atm")
    if pressures is not None and "bm_pressures_atm" in changed:
        unique = set(pressures)
        positive = {pressure for pressure in unique if pressure > 0}
        if len(unique) < 4 or 0 not in unique or len(positive) < 2:
            raise ValueError(
                "bm_pressures_atm must contain at least four unique points, including zero "
                "and at least two positive pressures"
            )


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
