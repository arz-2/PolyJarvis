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
import track_registry  # noqa: E402

from rules_common import get_class_entry, load_rules  # noqa: E402
from make_deterministic_plan import (_assert_tg_rate_feasible,  # noqa: E402
                                     build_decisions, build_planned_stages, make_plan,
                                     ordered_plan, resolve_d01, KNOWN_DECISIONS,
                                     _derived_from_field, _field_of, _ff_prior_uncertainty)
from select_system_size import solve_system_size  # noqa: E402
import rules_common  # noqa: E402  -- module import so tests can monkeypatch rules_common.canonicalize
import select_hardware as cost_model  # noqa: E402  -- cost model merged into it 2026-09-02
import forcefield  # noqa: E402  -- FIELDS is the only registry of real force-field names


# Re-exported from the registry -- imported by name in several modules.
VALID_PROPERTIES = track_registry.VALID_PROPERTIES
VALID_CONFIDENCE = frozenset({"low", "medium", "high"})
# Rows that WERE decisions and are now derivations of D-01's resolved field. Kept as a named
# set so a pre-2026-09-04 decision file gets an explanation instead of "unknown decision".
RETIRED_DECISIONS = frozenset({"D-02_charges", "D-03_electrostatics",
                               "D-04_system_size", "D-08_hardware"})
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
    "experimental_tg_K": (1, 1500),
    "experimental_density_gcm3": (0.05, 3.0),
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
    "stage8_min_steps": (1, 2_000_000_000),
    "stage8_cap_steps": (1, 2_000_000_000),
    # The melt tail of the core equilibration chain.
    "T_melt_hold_K": (100, 1500),
    "melt_ramp_steps": (1, 2_000_000_000),
    "melt_hold_min_steps": (1, 2_000_000_000),
    "melt_hold_cap_steps": (1, 2_000_000_000),
    "nvt_melt_min_steps": (1, 2_000_000_000),
    "nvt_melt_cap_steps": (1, 2_000_000_000),
    # The cooling stage's own extend ladder, kept separate from npt_continuation_ns so a
    # cooling-stage drift never writes an equilibration-hashed key.
    "cooling_continuation_ns": (0.01, 1000),
    "thermostat_damp_fs": (1, 100000),
    "barostat_damp_fs": (1, 1_000_000),
    "ct_min_decay_melt": (0.0, 1.0),
    "md_tg_ceiling_K": (100, 2000),
    "tg_t_low_K": (1, 1500),
    "tg_t_step_K": (1, 200),
    "tg_min_steps_per_T": (1, 2_000_000_000),
    # THE Tg knob since the single-rate collapse: n_steps_per_T = tg_t_step_K/(rate*dt*1e-6),
    # and cool_block_hold_steps is rate-matched to it, so this one number sets both the
    # staircase and the cooldown. tg_rates_K_per_ns (list), tg_primary_rate_index and
    # tg_steps_per_t were settable here until 2026-09-04 and reached no deck -- an override
    # that validates and changes nothing is worse than one that is rejected.
    "tg_rate_K_per_ns": (1, 1000),
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
    "npt_continuation_ns": (0.01, 1000),
    "mechanical_sampling_factor": (1, 10),
}
# Derived, never hand-listed: the hand-written copy had "trappe" (real key: "trappe-ua") and
# omitted the UA/GAFF entries, so 4 of the 6 values in use failed validation. RUNNABLE_FIELDS,
# not FIELDS: a field with no LAMMPS deck must not be nameable as an override.
FF_OVERRIDE_VALUES = forcefield.RUNNABLE_FIELDS
ENUM_OVERRIDES = {
    "preferred_builder": frozenset({"emc", "radonpy"}),
    "preferred_ff": FF_OVERRIDE_VALUES,
    "charge_method": frozenset({"none", "embedded", "bond-increment", "opls-library",
                                  "gasteiger", "am1bcc", "am1-bcc", "resp"}),
    "electrostatics": frozenset({"pppm", "lj_cut"}),
    "engine": frozenset({"gpu", "kokkos", "cpu"}),
    "mechanical_method": frozenset({"murnaghan", "deformation"}),
    "equilibration_phase": frozenset({"melt_then_cool", "melt_only"}),
}
SEQUENCE_OVERRIDES = frozenset({"bm_pressures_atm", "backbone_types",
                                "mechanical_resample_points"})
BOOLEAN_OVERRIDES = frozenset({"ct_gate_reliable"})
INTEGER_OVERRIDES = frozenset({
    "dp_typical", "nchain",
    "warmup_steps", "densify_ramp_steps", "densify_check_every_steps", "densify_steps_cap",
    "ff_activate_npt_steps", "anneal_heat_steps", "anneal_check_every_steps",
    "anneal_cap_steps", "cool_block_hold_steps", "cool_block_hold_cap_steps",
    "stage8_min_steps", "stage8_cap_steps",
    "melt_ramp_steps", "melt_hold_min_steps", "melt_hold_cap_steps",
    "nvt_melt_min_steps", "nvt_melt_cap_steps",
    "tg_min_steps_per_T",
    "deform_eq_steps", "deform_avg_window", "bm_npt_steps", "bm_thermo_freq",
    "emc_seed", "velocity_seed", "gpu_per_run", "mpi_ranks",
    "mechanical_sampling_factor",
})

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
    def from_run_plan(cls, plan: dict) -> "PlanDecision":
        """Read the adjudicated decision back off run_plan.json.

        decision.json was folded into run_plan.json on 2026-09-04, so the file the reviewer
        edits IS the plan. What used to be the decision file's fields now live as: the D-01_ff
        row (decisions[0]) instead of decision_evaluations, the row's critique.findings instead
        of rationale, and top-level overrides/confidence/dominant_uncertainty.
        """
        rows = {r.get("id"): r for r in plan.get("decisions") or []}
        d01 = rows.get("D-01_ff", {})
        return cls(
            polymer_class=str(plan["polymer_class"]).upper(),
            properties=tuple(plan.get("properties") or ()),
            rationale=tuple((d01.get("critique") or {}).get("findings") or ()),
            overrides=dict(plan.get("overrides") or {}),
            decision_evaluations={k: v for k, v in rows.items()},
            dominant_uncertainty=str(plan.get("dominant_uncertainty")
                                     or "protocol_transferability"),
            confidence=str(plan.get("confidence") or "").lower(),
        )

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
            confidence=str(value.get("confidence") or "").lower(),
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
    """Replays a captured scientific-agent decision for testing or audited execution.

    Accepts either shape: an adjudicated run_plan.json (the current flow) or a legacy
    decision.json. They are told apart by `decided_params`, which only a plan carries.
    """

    def __init__(self, path: Path):
        self.path = path
        self.base_plan = None

    def decide(self, intent: ScientificIntent, context: dict[str, Any]) -> PlanDecision:
        value = json.loads(self.path.read_text())
        if "decided_params" in value:
            # Keep the file itself: its D-01 row carries the critic's evidence and the probe's
            # admissible set, neither of which can be regenerated from the decision alone.
            self.base_plan = value
            return PlanDecision.from_run_plan(value)
        return PlanDecision.from_dict(value)


def planning_context(intent: ScientificIntent) -> dict[str, Any]:
    rules = load_rules()
    classes = rules.get("classes", {})
    summaries = {}
    for class_id, entry in classes.items():
        summaries[class_id] = {
            "name": entry.get("name") or entry.get("polymer_name"),
            "preferred_builder": entry.get("preferred_builder", "emc"),
            "ff_accuracy_prior": entry.get("ff_accuracy_prior"),
            "experimental_tg_K": entry.get("experimental_tg_K"),
            "supported_properties": sorted(VALID_PROPERTIES),
        }
    policy = json.loads((REPO_ROOT / "orchestration" / "decision_policy.json").read_text())
    cache_path = REPO_ROOT / "guides" / "system_characterization_cache.json"
    characterization_cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    canonical_smiles = None
    if intent.smiles:
        try:
            canonical_smiles = rules_common.canonicalize(intent.smiles, isomeric=True)
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


def _measure_d01_if_unprobed(plan: dict, smiles, rules: dict) -> None:
    """Run the force-field probe on an adjudicated plan that never had one.

    `--with-ff-probe` is opt-in on run-plan, so a plan generated without it carries a D-01 row
    asserting the class prior with NO `admissible` key -- nothing was measured. The refusal
    (nothing types this SMILES) is a safety property that has to bind on every path to
    execution, and between 2026-09-04 and this fix it bound only on the path with no plan file,
    because supplying `base_plan` skipped make_plan entirely. Probing here is idempotent: a row
    that already carries `admissible` was measured and is left alone.

    A probe that rescues a different field carries everything the field implies with it, the
    same way apply_recovery does -- a moved preferred_ff with a stale charge scheme is exactly
    the disagreement the derivation exists to prevent.
    """
    row = next((r for r in plan.get("decisions") or [] if r.get("id") == "D-01_ff"), None)
    if row is None or "admissible" in row or not smiles:
        return
    class_entry = dict(get_class_entry(rules, plan.get("polymer_class", ""), warn_on_miss=False))
    _, resolution = resolve_d01({**class_entry, **plan.get("decided_params", {})},
                                smiles, with_ff_probe=True)
    if not (resolution or {}).get("probed"):
        return                                   # no measured blocker -- nothing to measure
    field = resolution.get("field")
    row["admissible"] = [field] if field else []
    row["resolved_by"] = "forcefield.select_by_moiety"
    if not field or field == row.get("choice"):
        return
    row["choice"] = field
    derived = _derived_from_field(field, rules)
    plan["decided_params"]["preferred_ff"] = field
    plan["decided_params"]["charge_method"] = derived["charge_method"]
    plan["decided_params"]["electrostatics"] = derived["electrostatics"]
    plan["hardware"] = {k: derived[k]
                        for k in ("engine", "mpi_ranks", "gpu_per_run", "ff_family")}


def materialize_plan(intent: ScientificIntent, decision: PlanDecision,
                     base_plan: dict | None = None) -> dict:
    """Convert a narrow agent decision into a complete executable run plan.

    `base_plan` is the adjudicated run_plan.json when there is one: decision.json was folded
    into run_plan.json on 2026-09-04, so the critic's edits live on that file's D-01 row and
    must not be regenerated away. Without it the plan is built from scratch, WITH the force
    field probe -- the D-01 refusal (choice=None, admissible=[]) is a safety property and has
    to be measured here, not inherited from whoever generated a scaffold earlier. With a
    base_plan, _measure_d01_if_unprobed enforces the same thing on the file it was handed.
    """
    _validate_decision(decision)
    properties = set(decision.properties or intent.requested_properties)
    rules = load_rules()
    class_entry = dict(get_class_entry(rules, decision.polymer_class, warn_on_miss=False))
    effective_class = {**class_entry, **decision.overrides}

    # Solved BEFORE make_plan and handed to it: make_plan sizes the cell itself now (a
    # scaffold plan used to carry none at all), and the solve shells into the RDKit env, so
    # passing this in is what keeps a reasoned plan to one round-trip instead of two.
    # D-01's field is an input to the solve (united-atom cells count heavy atoms only), and an
    # override may already have demoted it off the class prior.
    field = _field_of(effective_class)
    size_solve = solve_system_size(
        decision.polymer_class, intent.smiles, properties,
        dp_typical=class_entry.get("dp_typical"), nchain=class_entry.get("nchain"),
        field=field)
    plan = base_plan or make_plan(intent.run_name, decision.polymer_class, intent.smiles,
                                  properties, size_solve=size_solve, with_ff_probe=True)
    if base_plan is not None:
        _measure_d01_if_unprobed(plan, intent.smiles, rules)
    auto_filled = {k: v for k, v in size_solve.get("recommended_params", {}).items()
                   if k not in decision.overrides}
    if auto_filled:
        effective_class.update(auto_filled)

    _validate_protocol_relationships(effective_class, set(decision.overrides))
    plan["decided_params"].update(track_registry.forced_params_for(properties))
    plan["decided_params"].update(decision.overrides)
    plan["decided_params"].update(auto_filled)
    if "T_equil_K" in decision.overrides and "T_workflow_K" not in decision.overrides:
        plan["decided_params"]["T_workflow_K"] = decision.overrides["T_equil_K"]
        effective_class["T_workflow_K"] = decision.overrides["T_equil_K"]
    plan["planned_stages"] = build_planned_stages(effective_class, properties, intent.smiles)
    # The rows make_plan already resolved are KEPT, never rebuilt. Rebuilding them here
    # transcribed class fields over the measured result and silently restored the class prior --
    # a SMILES that types under no field then built anyway and died in EMC, which is the whole
    # failure D-01's resolution exists to prevent.
    for row in plan.get("decisions", []):
        row["confidence"] = decision.confidence
        evaluation = decision.decision_evaluations.get(row["id"])
        if not evaluation:
            continue
        # An adjudicating agent may add evidence (origin: "critic") or narrow the alternatives;
        # it may not invent a choice -- that is what `overrides` is for, and it is validated.
        for key in ("criteria_evaluated", "evidence", "alternatives"):
            if key in evaluation:
                row[key] = list(evaluation[key])

    size_reasons = list(size_solve.get("recommendation_reasons") or [])
    if auto_filled:
        size_reasons.insert(0, f"system size auto-filled {auto_filled} via solve_system_size()")

    # Re-solve at the FINAL cell (which an override may have moved) to catch advisories that
    # only apply to what the plan actually carries, not to what the solver first recommended.
    final_dp = plan["decided_params"].get("dp_typical")
    size_acks = {}
    if final_dp is not None:
        final_check = solve_system_size(
            decision.polymer_class, intent.smiles, properties, dp_typical=final_dp,
            nchain=plan["decided_params"].get("nchain"),
            field=plan["decided_params"].get("preferred_ff") or field)
        for u in final_check.get("uncertainties", []) or []:
            name = u.get("name")
            if name == "size_over_provisioned":
                name = "system_size_over_provisioned"
            # The whole advisory, not just its detail string: entries carry extra fields
            # (class, current_nchain, ...) that a reader needs. `dominant` is dropped -- every
            # entry here is advisory by construction now, because the plan's headline lives in
            # the separate scalar dominant_uncertainty and no longer shares this container.
            size_acks[name] = {k: v for k, v in u.items()
                               if k not in ("name", "dominant", "reduction_probe")}

    plan["system_size"] = {
        "dp_typical": final_dp,
        "nchain": plan["decided_params"].get("nchain"),
        "resolved_by": "select_system_size.solve_system_size",
        "reasons": size_reasons,
        "acknowledgements": size_acks,
    }

    # Computed from the plan, not asked of the agent: a plan that builds with anything other
    # than its class prior has lost D-01's only DOI-backed evidence and must say so. Recorded on
    # the D-01 row itself now -- it describes that decision and nothing else reads it.
    d01 = next((r for r in plan.get("decisions", []) if r.get("id") == "D-01_ff"), None)
    if d01 is not None:
        ff_prior_ack = _ff_prior_uncertainty(decision.polymer_class,
                                             class_entry.get("ff_accuracy_prior"),
                                             plan["decided_params"].get("preferred_ff"))
        if ff_prior_ack:
            d01.setdefault("acknowledgements", {})["ff_accuracy_prior_not_met"] = (
                ff_prior_ack.get("detail", ""))
        d01["critique"] = {"status": "scientific_agent_decision", "rounds": 1,
                           "findings": list(decision.rationale) + list(decision.assumptions)}

    derived = _derived_from_field(plan["decided_params"].get("preferred_ff"), load_rules())
    plan = ordered_plan(
        run_name=plan.get("run_name"),
        polymer_class=plan.get("polymer_class"),
        smiles=plan.get("smiles"),
        goal=intent.goal,
        properties=sorted(properties),
        plan_mode="reasoned",
        confidence=decision.confidence,
        dominant_uncertainty=decision.dominant_uncertainty,
        decisions=plan.get("decisions", []),
        system_size=plan["system_size"],
        hardware={k: derived[k] for k in ("engine", "mpi_ranks", "gpu_per_run", "ff_family")},
        overrides=dict(decision.overrides),
        decided_params=plan["decided_params"],
        planned_stages=plan.get("planned_stages", []),
    )

    try:
        plan["cost_estimate"] = cost_model.plan_cost_estimate(plan)
    except Exception as e:  # noqa: BLE001 -- cost estimation is advisory, never blocking
        plan["cost_estimate"] = {"error": f"{type(e).__name__}: {e}"}
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
    # A recovery that changes the FIELD must carry everything the field implies with it.
    # Without this, recovery reintroduced exactly the disagreement the derivation exists to
    # prevent: decided_params.preferred_ff moved, and charge_method/electrostatics/hardware
    # kept describing the field the run started with.
    if "preferred_ff" in decision.modifications:
        derived = _derived_from_field(decided_params["preferred_ff"], load_rules())
        for key in ("charge_method", "electrostatics"):
            if key not in decision.modifications:
                decided_params[key] = derived[key]
        revised["hardware"] = {k: derived[k]
                               for k in ("engine", "mpi_ranks", "gpu_per_run", "ff_family")}
    if {"dp_typical", "nchain"} & set(decision.modifications):
        revised.setdefault("system_size", {}).update(
            {"dp_typical": decided_params.get("dp_typical"),
             "nchain": decided_params.get("nchain")})
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
    # A recovery modification (e.g. a dp_typical/nchain bump) changes the actual cost --
    # refresh cost_estimate so it never sits stale next to post-recovery decided_params.
    try:
        revised["cost_estimate"] = cost_model.plan_cost_estimate(revised)
    except Exception as e:  # noqa: BLE001 -- cost estimation is advisory, never blocking
        revised["cost_estimate"] = {"error": f"{type(e).__name__}: {e}"}
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
                # A FilePlanningAgent fed an adjudicated run_plan.json hands the file back
                # so materialize_plan promotes it in place. Regenerating instead would discard
                # the critic's evidence and the FF probe's admissible set.
                plan = materialize_plan(
                    intent, decision,
                    base_plan=getattr(self.planning_agent, "base_plan", None))
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
        write_control_state(self.repo_root, intent.run_name, status="running",
                            plan_path=plan_path)

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
        write_control_state(self.repo_root, run_name,
                            status=result.get("status"),
                            plan_path=result.get("plan_path"),
                            recovery_agent_calls=result.get("recovery_agent_calls"),
                            ended=True)


def write_control_state(repo_root, run_name: str, *, status: str, plan_path=None,
                        recovery_agent_calls=None, current_stage=None,
                        ended: bool = False) -> Path:
    """Write data/<run>/raw/control_state.json: WHICH SESSION IS ON THIS RUN, and is it over.

    Deliberately thin. It used to carry the control plane's whole return value -- an ~8 KB
    resolved-stage-params dump under `result`, plus an `events` list whose last entry embedded
    that same dump a second time, byte-identical. Nothing ever read either: the only fields any
    consumer touches are `status` (agent_api.inspect_run, the benchmark runner) and
    `recovery_agent_calls` (benchmark adaptive-gating).

    Worse, it was written ONCE, by the first control-plane call, and `run_campaign.py --plan` --
    the resume path -- never touched it. So a resumed run's file froze at the first session's
    status and escalation count; adaptive_gating.py carried a max(control, engine) workaround
    for exactly that. Both writers now update it, so `session_ended_at` and the counts describe
    the session that actually last ran.

    recovery_agent_calls is read from the engine's own workflow_state.agent_escalations rather
    than counted here, so it cannot drift from the engine's record.
    """
    path = Path(repo_root) / "data" / run_name / "raw" / "control_state.json"
    now = datetime.now(timezone.utc).isoformat()

    existing = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            existing = {}

    if recovery_agent_calls is None:
        recovery_agent_calls = 0
        state_file = Path(repo_root) / "data" / run_name / "workflow_state.json"
        if state_file.exists():
            try:
                recovery_agent_calls = len(json.loads(state_file.read_text()).get(
                    "agent_escalations", []))
            except (OSError, json.JSONDecodeError):
                pass

    _write_json(path, {
        "run_name": run_name,
        "plan_path": str(plan_path) if plan_path else existing.get("plan_path"),
        "status": status,
        "session_started_at": existing.get("session_started_at") or now,
        "session_ended_at": now if ended else None,
        "current_stage": current_stage,
        "recovery_agent_calls": recovery_agent_calls,
    })
    return path


def _validate_decision(decision: PlanDecision) -> None:
    # No rationale check. It required at least one entry until 2026-09-04, when the fold read
    # `rationale` off decisions[0].critique.findings -- which run-plan writes empty, because a
    # critique that has not happened yet must not be pre-populated with a finding. The result
    # blocked BOTH documented paths: a freshly generated plan, and --baseline, the arm that
    # exists precisely to materialize with no LLM in the loop. `confidence` is the only gate
    # (docs/AGENT_CONTRACT.md says so), and it is checked next.
    if decision.confidence not in VALID_CONFIDENCE:
        raise ValueError(
            f"confidence must be one of {sorted(VALID_CONFIDENCE)}; got "
            f"{decision.confidence!r}"
            + ("  (key absent or empty -- deleting it does not skip the gate)"
               if not decision.confidence else "")
        )
    properties = set(decision.properties)
    if not properties or not properties <= VALID_PROPERTIES:
        raise ValueError(f"properties must be a non-empty subset of {sorted(VALID_PROPERTIES)}")
    rules = load_rules()
    if decision.polymer_class not in rules.get("classes", {}):
        raise ValueError(f"unknown polymer class {decision.polymer_class!r}")
    validate_overrides(decision.overrides)
    supplied = set(decision.decision_evaluations)
    retired = supplied & RETIRED_DECISIONS
    if retired:
        # Not an error: these rows carry no information any more. Each was a pure function of
        # D-01's field and is now derived (make_deterministic_plan._derived_from_field), so a
        # decision file written before 2026-09-04 is still materializable -- its retired rows
        # are dropped rather than silently honoured, because honouring them is what let a
        # recorded charge scheme disagree with the field actually built.
        print(f"INFO: ignoring retired decision evaluations {sorted(retired)} -- each is now "
              f"derived from D-01_ff's resolved field, not decided independently.",
              file=sys.stderr)
        for rid in retired:
            decision.decision_evaluations.pop(rid, None)
    unknown_decisions = supplied - KNOWN_DECISIONS - RETIRED_DECISIONS
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
            if key == "backbone_types" and any(item <= 0 for item in value):
                raise ValueError(f"{key} values must be positive")


def _validate_protocol_relationships(parameters: dict[str, Any], changed: set[str]) -> None:
    """Reject internally inconsistent plans before any files or jobs are created."""
    t_low = parameters.get("tg_t_low_K")
    t_high = parameters.get("T_melt_hold_K")
    if ({"tg_t_low_K", "T_melt_hold_K"} & changed and
            t_low is not None and t_high is not None and t_low >= t_high):
        raise ValueError("tg_t_low_K must be lower than T_melt_hold_K")

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

    # One rate since 2026-09-04, and it IS the per-T step count. Delegated to the planner's own
    # assertion rather than re-derived here: two copies of N = t_step/(rate*dt*1e-6) drifted
    # apart once already, and this one was still checking a list nobody writes.
    if {"tg_rate_K_per_ns", "dt_fs", "tg_t_step_K", "tg_min_steps_per_T"} & changed:
        _assert_tg_rate_feasible(parameters, "overrides")

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
    planning.add_argument("--plan", "--decision-file", dest="plan_file",
                          help="An adjudicated run_plan.json (or a legacy decision.json). "
                               "--decision-file is kept as an alias so existing invocations "
                               "and the skill's older command line keep working.")
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
    if args.plan_file:
        planning_agent: PlanningAgent = FilePlanningAgent(Path(args.plan_file))
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
