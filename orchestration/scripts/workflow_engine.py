#!/usr/bin/env python3
"""Durable, deterministic workflow state and recovery policy for PolyJarvis.

The engine owns orchestration only.  Stage executors receive resolved scientific
parameters and an attempt directory; they cannot declare a stage successful without
passing its binding reportability gates.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from types import SimpleNamespace
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Protocol


ENGINE_VERSION = "workflow-engine-v1"
MAX_AUTOMATIC_REMEDIES = 12
MAX_AGENT_DECISIONS = 2
TRANSIENT_RETRIES = 2
STAGE_ORDER = ("build", "equilibration", "thermal", "mechanical", "summary")
STAGE_RESULTS = frozenset({"accepted", "remedy_required", "escalation_required", "failed"})
BLOCKING_SEVERITIES = frozenset({"blocking", "structural", "error", "fatal"})

# Parameters are hashed only into stages that actually consume them.  Dependencies carry
# accepted artifact checksums forward, so descendants still change without making sibling
# tracks stale (for example, a Tg sampling change does not invalidate mechanical work).
PARAMETER_STAGE: dict[str, str] = {
    "preferred_builder": "build", "preferred_ff": "build", "charge_method": "build",
    "dp_typical": "build", "nchain": "build", "density_initial_gcm3": "build",
    "build_temperature_K": "build", "electrostatics": "build",
    "cutoff_A": "build", "emc_seed": "build", "backbone_types": "equilibration",
    "gpu_per_run": "build", "mpi_ranks": "build", "engine": "build",
    "dt_fs": "equilibration", "T_equil_K": "equilibration",
    "annealing_T_high_K": "equilibration", "T_workflow_K": "equilibration",
    "P_equil_atm": "equilibration", "t_equil_ns": "equilibration",
    "eq_annealing_cycles": "equilibration", "anneal_cycle_ns": "equilibration",
    "add_melt_npt": "equilibration", "add_300k_production": "equilibration",
    "compression_max_pressure_atm": "equilibration",
    "thermostat_damp_fs": "equilibration", "barostat_damp_fs": "equilibration",
    "npt_prod300_ns": "equilibration", "melt_npt_ns": "equilibration",
    "alpha_glass_per_K": "equilibration", "alpha_melt_per_K": "equilibration",
    "ct_min_decay_melt": "equilibration", "ct_gate_reliable": "equilibration",
    "velocity_seed": "equilibration",
    "npt_prod_ns": "equilibration", "npt_cool_steps": "equilibration",
    "npt_cool300_steps": "equilibration", "npt_continuation_ns": "equilibration",
    "melt_hold_ns": "equilibration", "melt_only_continuation_ns": "equilibration",
    "equilibration_phase": "equilibration", "cooling_resume_source": "equilibration",
    # Ladder bookkeeping the equilibration remedies (_continue_npt, _cooling, _melt_hold,
    # _melt_homogeneity) write into effective_parameters alongside their real scientific
    # knob -- these carry no scientific weight of their own, but MUST still be mapped to their
    # owning stage. An unmapped key falls through PARAMETER_STAGE.get(key, "build") and, on the
    # next engine reconstruction (a resume, exactly this case), reads as a changed "build"
    # parameter -- invalidating the ENTIRE pipeline back to build, discarding every already-
    # accepted stage's bookkeeping (though not its on-disk manifest/artifacts). Hit live on PE1
    # 2026-08-17 via tg_sampling's baseline_tg_steps_per_t below, which cascaded equilibration's
    # already-verified PASS back to "stale" on repair-script reconstruction.
    "npt_continuation_attempt": "equilibration", "baseline_npt_cool_steps": "equilibration",
    "baseline_eq_annealing_cycles": "equilibration", "rerun_homogeneity_gate": "equilibration",
    "tg_t_high_K": "thermal", "tg_t_low_K": "thermal", "tg_t_step_K": "thermal",
    "tg_primary_rate_index": "thermal", "tg_rates_K_per_ns": "thermal",
    "tg_slope_gate_fallback": "thermal",
    "tg_steps_per_t": "thermal", "tg_min_steps_per_T": "thermal",
    # tg_sampling's own ladder-bookkeeping key -- see the equilibration block's comment above.
    "baseline_tg_steps_per_t": "thermal",
    "K_strain_max": "mechanical", "K_deform_rate_inv_s": "mechanical",
    "K_deform_rate_slow_inv_s": "mechanical", "bm_pressures_atm": "mechanical",
    "deform_eq_steps": "mechanical", "deform_strain_start": "mechanical",
    "deform_avg_window": "mechanical", "bm_npt_steps": "mechanical",
    "bm_temperature_K": "mechanical", "bm_thermo_freq": "mechanical",
    "mechanical_method": "mechanical", "mechanical_resample_points": "mechanical",
    "mechanical_sampling_factor": "mechanical",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + "\n")
    temporary.replace(path)


@dataclass(frozen=True)
class Finding:
    code: str
    stage: str
    severity: str = "blocking"
    confidence: str = "high"
    details: dict[str, Any] = field(default_factory=dict)
    remedy_id: Optional[str] = None

    @classmethod
    def from_value(cls, value: Any, stage: str) -> "Finding":
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            return cls(code=value, stage=stage)
        if not isinstance(value, Mapping):
            return cls("UNEXPLAINED_STAGE_FAILURE", stage, confidence="low",
                       details={"raw": repr(value)})
        code = value.get("code") or value.get("verdict") or value.get("reason")
        return cls(
            code=str(code or "UNEXPLAINED_STAGE_FAILURE"),
            stage=str(value.get("stage") or stage),
            severity=str(value.get("severity") or "blocking").lower(),
            confidence=str(value.get("confidence") or "high").lower(),
            details=dict(value.get("details") or value.get("detail") or {}),
            remedy_id=value.get("remedy_id"),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StageResult:
    status: str
    findings: tuple[Finding, ...] = ()
    artifacts: tuple[str, ...] = ()
    outputs: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in STAGE_RESULTS:
            raise ValueError(f"invalid stage result {self.status!r}")

    @classmethod
    def from_value(cls, value: Any, stage: str) -> "StageResult":
        if isinstance(value, cls):
            return value
        if not isinstance(value, Mapping):
            finding = Finding("UNEXPLAINED_STAGE_FAILURE", stage, confidence="low",
                              details={"raw": repr(value)})
            return cls("failed", (finding,))
        findings = tuple(Finding.from_value(item, stage) for item in value.get("findings", ()))
        status = str(value.get("status") or "failed").lower()
        # Legacy adapters can return a single verdict/reason instead of findings.
        if not findings and status in {"failed", "halted", "remedy_required", "escalation_required"}:
            findings = (Finding.from_value(value, stage),)
        if status == "halted":
            status = "remedy_required"
        return cls(status, findings, tuple(map(str, value.get("artifacts", ()))),
                   dict(value.get("outputs") or value.get("result") or {}))


class StageExecutor(Protocol):
    def execute(self, stage: str, context: Mapping[str, Any]) -> StageResult | Mapping[str, Any]: ...


@dataclass(frozen=True)
class Remedy:
    remedy_id: str
    codes: frozenset[str]
    local_cap: int
    action: Callable[[dict[str, Any], Finding, int], dict[str, Any]]
    invalidate_from: str
    agent_only: bool = False


def _merge(params: dict[str, Any], **changes: Any) -> dict[str, Any]:
    revised = dict(params)
    revised.update(changes)
    return revised


def _required_nchain(finding: Finding) -> int:
    details = finding.details
    forecast = details.get("finite_size_forecast") or {}
    forecast_remedy = forecast.get("remedy") or {}
    required = (details.get("required_nchain") or details.get("suggested_nchain") or
                forecast_remedy.get("nchain_suggested"))
    if required is None:
        current = int(details.get("current_nchain") or details.get("nchain") or
                      forecast.get("nchain_current") or 1)
        factor = float(details.get("required_factor") or details.get("size_factor") or
                       forecast_remedy.get("nchain_factor") or 1.0)
        required = math.ceil(current * factor)
    return max(1, math.ceil(float(required) * 1.10))


def _finite_size(params: dict[str, Any], finding: Finding, _: int) -> dict[str, Any]:
    return _merge(params, nchain=_required_nchain(finding))


def _hardware(params: dict[str, Any], finding: Finding, _: int) -> dict[str, Any]:
    recommendation = finding.details.get("recommendation") or finding.details.get("selected_hardware")
    if not isinstance(recommendation, Mapping):
        raise ValueError("hardware remedy requires a deterministic recommendation")
    revised = dict(params)
    for key in ("gpu_per_run", "mpi_ranks", "engine"):
        if key in recommendation:
            revised[key] = recommendation[key]
    return revised


def _remove_noop(params: dict[str, Any], finding: Finding, _: int) -> dict[str, Any]:
    key = finding.details.get("parameter") or finding.details.get("key")
    if not key:
        raise ValueError("no-op remedy requires details.parameter")
    revised = dict(params)
    revised.pop(str(key), None)
    return revised


def _forcefield(params: dict[str, Any], finding: Finding, _: int) -> dict[str, Any]:
    alternatives = finding.details.get("admissible_alternatives") or []
    if len(alternatives) != 1:
        raise ValueError("force-field switch is not uniquely determined")
    alternative = alternatives[0]
    value = alternative.get("forcefield") if isinstance(alternative, Mapping) else alternative
    return _merge(params, preferred_ff=value)


def _continue_npt(params: dict[str, Any], finding: Finding, attempt: int) -> dict[str, Any]:
    details = finding.details
    ns = details.get("extension_ns") or details.get("required_extension_ns")
    if ns is None:
        tau = float(details.get("relaxation_time_ns") or details.get("tau_ns") or 0.5)
        n_eff = max(float(details.get("n_eff") or 0), 1.0)
        target = max(float(details.get("target_n_eff") or 20), n_eff)
        ns = tau * target
    return _merge(params, npt_continuation_ns=float(ns), npt_continuation_attempt=attempt)


def _cooling(params: dict[str, Any], _finding: Finding, attempt: int) -> dict[str, Any]:
    baseline = int(params.get("baseline_npt_cool_steps") or params.get("npt_cool_steps") or 1)
    return _merge(params, npt_cool_steps=baseline * (2 ** attempt),
                  baseline_npt_cool_steps=baseline,
                  cooling_resume_source="accepted_melt")


def _melt_hold(params: dict[str, Any], _finding: Finding, attempt: int) -> dict[str, Any]:
    """MELT_STAGE_DEFICIT ladder: try the cheaper, more-targeted lever first. Attempt 1 escalates
    thermal-cycling depth (more chance to escape a bad initial pack); attempt 2 adds a bounded
    isothermal melt hold, the fallback for systems no amount of annealing fixes (genuine FF
    underbinding) -- assess_cooling_contraction.py cannot separate the two causes on its own.
    5 ns, not the ~100 ns NkepsuMbitou2025 cites for full convergence: PolyJarvis is a quick
    survey tool, not a per-polymer optimizer -- this rung is a bounded diagnostic probe, not
    meant to brute-force convergence. A deficit that doesn't resolve within it should escalate to
    agent_only for human review rather than keep spending wall-clock chasing the literature value."""
    baseline = int(params.get("baseline_eq_annealing_cycles") or params.get("eq_annealing_cycles") or 0)
    revised = _merge(params, eq_annealing_cycles=max(baseline * 2, baseline + 2, 2),
                      baseline_eq_annealing_cycles=baseline)
    if attempt > 1:
        revised = _merge(revised, melt_hold_ns=5.0, add_melt_npt=True,
                          equilibration_phase="melt_then_cool", cooling_resume_source="remedied_melt")
    return revised


def _melt_homogeneity(params: dict[str, Any], finding: Finding, attempt: int) -> dict[str, Any]:
    revised = _continue_npt(params, finding, attempt)
    revised.update({"equilibration_phase": "melt_only", "rerun_homogeneity_gate": True})
    return revised


def _tg_sampling(params: dict[str, Any], _finding: Finding, attempt: int) -> dict[str, Any]:
    baseline = int(params.get("baseline_tg_steps_per_t") or params.get("tg_steps_per_t") or 1)
    revised = dict(params)
    revised["baseline_tg_steps_per_t"] = baseline
    revised["tg_steps_per_t"] = baseline * 2
    if attempt > 1:
        current_step = float(params.get("tg_t_step_K", 20))
        if current_step <= 5.0:
            raise ValueError("Tg temperature-step floor exhausted")
        revised["tg_t_step_K"] = max(5.0, current_step / 2.0)
    return revised


def _tg_review(params: dict[str, Any], _finding: Finding, _attempt: int) -> dict[str, Any]:
    return _merge(params, tg_t_step_K=max(5.0, float(params.get("tg_t_step_K", 20)) / 2.0))


def _murnaghan_resample(params: dict[str, Any], finding: Finding, _: int) -> dict[str, Any]:
    points = finding.details.get("nonmonotonic_points") or finding.details.get("pressure_points") or []
    return _merge(params, mechanical_resample_points=list(points), mechanical_sampling_factor=2)


def _deformation(params: dict[str, Any], _finding: Finding, _: int) -> dict[str, Any]:
    return _merge(params, mechanical_method="deformation")


def _conditional_deformation(params: dict[str, Any], finding: Finding, _: int) -> dict[str, Any]:
    gate_output = finding.details.get("gate_output") or {}
    is_glassy = finding.details.get("is_glassy", gate_output.get("is_glassy",
                                                                  params.get("is_glassy")))
    if is_glassy is not True:
        raise ValueError("Murnaghan fallback is unsupported outside the glassy regime")
    return _merge(params, mechanical_method="deformation")


def _negative_modulus(params: dict[str, Any], _finding: Finding, _: int) -> dict[str, Any]:
    rate = params.get("K_deform_rate_slow_inv_s") or params.get("K_deform_rate_inv_s")
    return _merge(params, K_deform_rate_inv_s=rate,
                  K_strain_max=float(params.get("K_strain_max", 0.03)) / 2.0)


def _rate_sensitivity(params: dict[str, Any], finding: Finding, _: int) -> dict[str, Any]:
    current = float(finding.details.get("slow_rate_inv_s") or
                    params.get("K_deform_rate_slow_inv_s") or
                    params.get("K_deform_rate_inv_s"))
    floor = float(finding.details.get("minimum_rate_inv_s") or params.get("minimum_rate_inv_s") or 1e3)
    return _merge(params, K_deform_rate_slow_inv_s=max(floor, current / 10.0))


def default_remedies() -> tuple[Remedy, ...]:
    """Registry for every active blocking verdict in the v1 workflow."""
    transient = frozenset({"PROCESS_FAILED", "PROCESS_DEAD_NO_SENTINEL", "PROCESS_TIMEOUT",
                           "BUILDER_PROCESS_FAILED", "THERMAL_PROCESS_FAILED",
                           "MECHANICAL_POINT_PROCESS_FAILED"})
    return (
        Remedy("transient_retry", transient, 2, lambda p, _f, _a: dict(p), "same"),
        Remedy("finite_size_rebuild", frozenset({"SIZE_MIN_IMAGE_VIOLATION", "SIZE_CHAIN_SELF_IMAGE",
                                                  "FINITE_SIZE_FAILED"}), 2, _finite_size, "build"),
        Remedy("safe_hardware", frozenset({"UNSAFE_HARDWARE_PIN"}), 1, _hardware, "build"),
        Remedy("remove_noop", frozenset({"UNIMPLEMENTED_PARAMETER", "OVERRIDDEN_NOOP_PARAMETER"}),
               1, _remove_noop, "build"),
        Remedy("unique_forcefield", frozenset({"FORCE_FIELD_TYPING_FAILED"}), 1,
               _forcefield, "build"),
        Remedy("continue_npt", frozenset({"EQUIL_DRIFT", "EQUIL_SEM", "EQUIL_N_EFF", "EXTEND"}),
               2, _continue_npt, "equilibration"),
        Remedy("slower_cooling", frozenset({"UNDER_ANNEALED_COOLING"}), 2,
               _cooling, "equilibration"),
        Remedy("melt_hold", frozenset({"MELT_STAGE_DEFICIT"}), 2,
               _melt_hold, "equilibration"),
        Remedy("melt_homogeneity", frozenset({"HOMOG_HETEROGENEOUS", "DENSITY_HETEROGENEITY"}),
               2, _melt_homogeneity, "equilibration"),
        Remedy("tg_sampling", frozenset({"TG_NOT_REPORTABLE"}), 7,
               _tg_sampling, "thermal"),
        Remedy("tg_breakpoint", frozenset({"TG_REVIEW"}), 1, _tg_review, "thermal"),
        Remedy("deformation_fallback", frozenset({"BM_FALLBACK_DEFORM"}), 1,
               _deformation, "mechanical"),
        Remedy("murnaghan_resample", frozenset({"BM_INADMISSIBLE_NONMONOTONIC"}), 1,
               _murnaghan_resample, "mechanical"),
        Remedy("conditional_deformation", frozenset({"BM_INADMISSIBLE"}), 1,
               _conditional_deformation, "mechanical"),
        Remedy("negative_deformation", frozenset({"DEFORM_NEGATIVE_MODULUS"}), 1,
               _negative_modulus, "mechanical"),
        Remedy("rate_sensitivity", frozenset({"DEFORM_RATE_SENSITIVE"}), 1,
               _rate_sensitivity, "mechanical"),
        Remedy("agent_only", frozenset({
            "PLAN_AGENT_CONTRACT_ERROR", "PLAN_VALIDATION_FAILED", "UNSUPPORTED_BUILDER",
            "DETERMINISTIC_BUILD_FAILED", "FORCE_FIELD_TYPING_AMBIGUOUS",
            "BACKBONE_TYPES_UNRESOLVED", "STRUCTURAL_FAIL", "AMBIGUOUS_ORDERING",
            "BM_INADMISSIBLE_UNSUPPORTED_REGIME", "DEFORM_ANISOTROPIC",
            "DEFORM_INADMISSIBLE", "DEFORM_RATE_SENSITIVITY_PERSISTS",
            "MECHANICAL_IDENTIFIABILITY_FAILED", "ARTIFACT_INTEGRITY_FAILED",
            "UNEXPLAINED_STAGE_FAILURE", "REMEDY_EXHAUSTED", "AUTOMATIC_REMEDY_CAP_REACHED",
        }), 0, lambda p, _f, _a: dict(p), "same", agent_only=True),
    )


ACTIVE_BLOCKING_CODES = frozenset(code for remedy in default_remedies() for code in remedy.codes)


class RemedyRegistry:
    def __init__(self, remedies: tuple[Remedy, ...] | None = None):
        self.remedies = remedies or default_remedies()
        self._by_code: dict[str, Remedy] = {}
        for remedy in self.remedies:
            for code in remedy.codes:
                if code in self._by_code:
                    raise ValueError(f"duplicate remedy route for {code}")
                self._by_code[code] = remedy

    def route(self, finding: Finding) -> Remedy:
        remedy = self._by_code.get(finding.code)
        if remedy is None:
            return next(item for item in self.remedies if item.agent_only)
        return remedy

    def assert_complete(self, active_codes: set[str] | frozenset[str]) -> None:
        missing = set(active_codes) - set(self._by_code)
        if missing:
            raise AssertionError(f"blocking verdicts lack remedy routes: {sorted(missing)}")


def binding_gate_failure(stage: str, outputs: Mapping[str, Any]) -> Optional[Finding]:
    """Return a normalized failure when an output's binding gate is not reportable."""
    if stage == "thermal":
        verdict = outputs.get("tg_gate_verdict")
        if verdict != "TG_REPORTABLE":
            return Finding(str(verdict or "TG_NOT_REPORTABLE"), stage,
                           details={"gate_output": dict(outputs)})
    if stage == "mechanical":
        method = outputs.get("mechanical_method") or outputs.get("method")
        bm = outputs.get("bm_gate_verdict")
        deform = outputs.get("deform_gate_verdict")
        if method == "deformation" or (deform is not None and bm is None):
            if deform != "DEFORM_REPORTABLE":
                reasons = " ".join(map(str, outputs.get("deform_gate_reasons") or ())).lower()
                if outputs.get("bulk_modulus_GPa", 0) < 0 or "negative" in reasons:
                    code = "DEFORM_NEGATIVE_MODULUS"
                elif "anisotropic" in reasons:
                    code = "DEFORM_ANISOTROPIC"
                else:
                    code = str(deform or "DEFORM_INADMISSIBLE")
                return Finding(code, stage, details={"gate_output": dict(outputs)})
            rate = outputs.get("rate_sensitivity") or {}
            if rate.get("verdict") == "WARNING":
                return Finding("DEFORM_RATE_SENSITIVE", stage,
                               details={"gate_output": dict(outputs), **rate})
        elif bm != "BM_REPORTABLE":
            reasons = " ".join(map(str, outputs.get("bm_gate_reasons") or ())).lower()
            code = ("BM_INADMISSIBLE_NONMONOTONIC"
                    if bm == "BM_INADMISSIBLE" and "not monotonic" in reasons
                    else str(bm or "BM_INADMISSIBLE"))
            return Finding(code, stage,
                           details={"gate_output": dict(outputs)})
    return None


def pressure_point_drop_allowed(point_status: Mapping[float, str]) -> bool:
    """Whether failed pressure points may be dropped without losing identifiability.

    Callers retry each failed point once before using this predicate. Values equal to
    ``"accepted"`` are valid; all other values are treated as failed/incomplete.
    """
    valid = {float(pressure) for pressure, status in point_status.items()
             if status == "accepted"}
    return (len(valid) >= 4 and 0.0 in valid and
            sum(pressure > 0.0 for pressure in valid) >= 2)


class WorkflowEngine:
    """Execute, remedy, invalidate, and resume one campaign."""

    def __init__(self, run_dir: Path, plan: Mapping[str, Any], executor: StageExecutor,
                 *, registry: Optional[RemedyRegistry] = None,
                 recovery_agent: Any = None, policy_hashes: Optional[Mapping[str, str]] = None,
                 implementation_version: str = ENGINE_VERSION,
                 plan_path: Optional[Path] = None,
                 plan_validator: Optional[Callable[[Mapping[str, Any]], list[Mapping[str, Any]]]] = None,
                 override_validator: Optional[Callable[[Mapping[str, Any]], None]] = None):
        self.run_dir = Path(run_dir)
        self.plan = json.loads(json.dumps(plan))
        self.executor = executor
        self.registry = registry or RemedyRegistry()
        self.recovery_agent = recovery_agent
        self.policy_hashes = dict(policy_hashes or {})
        self.implementation_version = implementation_version
        self.plan_path = Path(plan_path) if plan_path else None
        self.plan_validator = plan_validator
        # Bounds/whitelist check for agent-proposed `modifications` (raises ValueError on an
        # out-of-range value or an unsupported key); injected rather than imported so this
        # module stays stdlib-only and independently testable. scientific_control.py's
        # validate_overrides is the production value.
        self.override_validator = override_validator
        self.state_path = self.run_dir / "workflow_state.json"
        self.attempts_dir = self.run_dir / "attempts"
        self.state = self._load_or_create_state()
        self._reconcile_plan()

    def enabled_stages(self) -> tuple[str, ...]:
        properties = set(self.plan.get("properties") or ())
        stages = ["build", "equilibration"]
        if "tg" in properties:
            stages.append("thermal")
        if "bulk_modulus" in properties:
            stages.append("mechanical")
        stages.append("summary")
        return tuple(stages)

    def _load_or_create_state(self) -> dict[str, Any]:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        if self.state_path.exists():
            state = json.loads(self.state_path.read_text())
            for record in state.get("stages", {}).values():
                if record.get("status") == "running":
                    record["status"] = "incomplete"
                    record.pop("accepted_attempt", None)
            self._save(state)
            return state
        state = {
            "schema_version": 1,
            "engine_version": self.implementation_version,
            "run_name": self.plan.get("run_name"),
            "plan_hash": _canonical_hash(self.plan),
            "effective_parameters": dict(self.plan.get("decided_params") or {}),
            "stages": {name: {"status": "pending", "attempts": []} for name in self.enabled_stages()},
            "remedy_counters": {"total": 0, "by_id": {}, "by_route": {}},
            "agent_escalations": [],
            "created_at": _now(),
            "updated_at": _now(),
        }
        self._save(state)
        return state

    def _save(self, state: Optional[dict[str, Any]] = None) -> None:
        target = state if state is not None else self.state
        target["updated_at"] = _now()
        atomic_write_json(self.state_path, target)

    def _reconcile_plan(self) -> None:
        new_hash = _canonical_hash(self.plan)
        if self.state.get("plan_hash") == new_hash:
            return
        old = dict(self.state.get("effective_parameters") or {})
        new = dict(self.plan.get("decided_params") or {})
        changed = {key for key in set(old) | set(new) if old.get(key) != new.get(key)}
        self.state["plan_hash"] = new_hash
        self.state["effective_parameters"] = new
        affected = [PARAMETER_STAGE.get(key, "build") for key in changed]
        if affected:
            enabled = self.enabled_stages()
            earliest = min((stage for stage in affected if stage in enabled),
                           key=enabled.index, default="build")
            self.invalidate_from(earliest, "executable plan changed")
        else:
            self._save()

    def _dependencies(self, stage: str) -> tuple[str, ...]:
        enabled = self.enabled_stages()
        if stage == "build":
            return ()
        if stage == "equilibration":
            return ("build",)
        if stage == "thermal":
            return ("equilibration",)
        if stage == "mechanical":
            return (("equilibration", "thermal") if "thermal" in self.enabled_stages()
                    else ("equilibration",))
        return tuple(name for name in enabled if name != "summary")

    def _accepted_manifest(self, stage: str) -> dict[str, Any]:
        record = self.state["stages"][stage]
        attempt_id = record.get("accepted_attempt")
        if not attempt_id:
            raise ValueError(f"{stage} has no accepted attempt")
        path = self.attempts_dir / stage / attempt_id / "manifest.json"
        manifest = json.loads(path.read_text())
        for artifact in manifest.get("artifacts", []):
            artifact_path = Path(artifact["path"])
            if not artifact_path.is_absolute():
                artifact_path = path.parent / artifact_path
            if not artifact_path.is_file() or file_sha256(artifact_path) != artifact["sha256"]:
                raise ValueError(f"artifact integrity failed for {artifact_path}")
        return manifest

    def _input_hash(self, stage: str) -> str:
        dependency_checksums = {}
        for dependency in self._dependencies(stage):
            manifest = self._accepted_manifest(dependency)
            dependency_checksums[dependency] = {
                item["path"]: item["sha256"] for item in manifest.get("artifacts", [])
            }
        relevant_parameters = {
            key: value for key, value in self.state["effective_parameters"].items()
            if PARAMETER_STAGE.get(key, "build") == stage
            # Global scientific parameters intentionally belong to build only. Descendants
            # receive their effect through dependency artifact checksums.
        }
        return _canonical_hash({
            "stage": stage,
            "effective_parameters": relevant_parameters,
            "scientific_identity": ({
                "polymer_class": self.plan.get("polymer_class"),
                "smiles": self.plan.get("smiles"),
            } if stage == "build" else {}),
            "policy_hashes": self.policy_hashes,
            "implementation_version": self.implementation_version,
            "dependencies": dependency_checksums,
        })

    def invalidate_from(self, stage: str, reason: str) -> None:
        enabled = self.enabled_stages()
        descendants = {stage}
        changed = True
        while changed:
            changed = False
            for name in enabled:
                if name not in descendants and descendants.intersection(self._dependencies(name)):
                    descendants.add(name)
                    changed = True
        for name in enabled:
            if name not in descendants:
                continue
            record = self.state["stages"].setdefault(name, {"attempts": []})
            if record.get("status") == "accepted":
                record["status"] = "stale"
            elif record.get("status") != "running":
                record["status"] = "pending"
            record.pop("accepted_attempt", None)
            record["stale_reason"] = reason
        self._save()

    def reconcile_inputs(self) -> None:
        for stage in self.enabled_stages():
            record = self.state["stages"].setdefault(stage, {"status": "pending", "attempts": []})
            if record.get("status") != "accepted":
                break
            try:
                # Verify this stage's own immutable outputs as well as the dependency hashes
                # incorporated into its input hash.
                self._accepted_manifest(stage)
                current = self._input_hash(stage)
            except (OSError, ValueError, json.JSONDecodeError):
                self.invalidate_from(stage, "accepted artifact missing or changed")
                break
            if record.get("input_hash") != current:
                self.invalidate_from(stage, "stage input hash changed")
                break

    def _new_attempt(self, stage: str, input_hash: str) -> tuple[str, Path]:
        record = self.state["stages"][stage]
        attempt_id = f"attempt-{len(record.get('attempts', [])) + 1:04d}"
        attempt_dir = self.attempts_dir / stage / attempt_id
        attempt_dir.mkdir(parents=True, exist_ok=False)
        entry = {"attempt_id": attempt_id, "status": "running", "input_hash": input_hash,
                 "started_at": _now()}
        record.setdefault("attempts", []).append(entry)
        record.update({"status": "running", "input_hash": input_hash})
        self._save()
        return attempt_id, attempt_dir

    def _finish_attempt(self, stage: str, attempt_id: str, attempt_dir: Path,
                        result: StageResult, input_hash: str) -> dict[str, Any]:
        artifacts = []
        for raw_path in result.artifacts:
            path = Path(raw_path)
            if not path.is_absolute():
                path = attempt_dir / path
            if not path.is_file():
                raise ValueError(f"executor declared missing artifact {path}")
            artifacts.append({"path": str(path), "sha256": file_sha256(path),
                              "size": path.stat().st_size})
        manifest = {
            "attempt_id": attempt_id, "stage": stage, "status": result.status,
            "input_hash": input_hash, "findings": [item.to_dict() for item in result.findings],
            "outputs": result.outputs, "artifacts": artifacts, "finished_at": _now(),
        }
        atomic_write_json(attempt_dir / "manifest.json", manifest)
        entry = self.state["stages"][stage]["attempts"][-1]
        entry.update({"status": result.status, "finished_at": manifest["finished_at"],
                      "manifest": str(attempt_dir / "manifest.json")})
        self._save()
        return manifest

    def _execute_stage(self, stage: str) -> tuple[StageResult, dict[str, Any]]:
        input_hash = self._input_hash(stage)
        attempt_id, attempt_dir = self._new_attempt(stage, input_hash)
        dependencies = {name: self._accepted_manifest(name) for name in self._dependencies(stage)}
        context = {
            "run_name": self.plan.get("run_name"), "stage": stage,
            "attempt_id": attempt_id, "attempt_dir": str(attempt_dir),
            "parameters": dict(self.state["effective_parameters"]),
            "plan": json.loads(json.dumps(self.plan)), "dependencies": dependencies,
            "prior_attempts": list(self.state["stages"][stage].get("attempts", ())[:-1]),
        }
        try:
            result = StageResult.from_value(self.executor.execute(stage, context), stage)
            gate_failure = binding_gate_failure(stage, result.outputs) if result.status == "accepted" else None
            if gate_failure:
                result = StageResult("remedy_required", result.findings + (gate_failure,),
                                     result.artifacts, result.outputs)
        except Exception as exc:  # process adapters normalize unexpected execution failures
            result = StageResult("failed", (Finding("PROCESS_FAILED", stage,
                                                     details={"error": str(exc)}),))
        manifest = self._finish_attempt(stage, attempt_id, attempt_dir, result, input_hash)
        return result, manifest

    def _apply_remedy(self, finding: Finding) -> bool:
        remedy = self.registry.route(finding)
        counters = self.state["remedy_counters"]
        route_key = f"{remedy.remedy_id}:{finding.stage}"
        used = int(counters.setdefault("by_route", {}).get(route_key, 0))
        if finding.confidence == "low" or remedy.agent_only or used >= remedy.local_cap:
            return False
        if int(counters["total"]) >= MAX_AUTOMATIC_REMEDIES:
            return False
        try:
            revised = remedy.action(dict(self.state["effective_parameters"]), finding, used + 1)
        except (KeyError, TypeError, ValueError):
            return False
        self.state["effective_parameters"] = revised
        counters["total"] += 1
        counters["by_id"][remedy.remedy_id] = int(counters["by_id"].get(remedy.remedy_id, 0)) + 1
        counters["by_route"][route_key] = used + 1
        self.state.setdefault("remedy_history", []).append({
            "remedy_id": remedy.remedy_id, "finding": finding.to_dict(),
            "application": used + 1, "at": _now(),
        })
        invalidate = finding.stage if remedy.invalidate_from == "same" else remedy.invalidate_from
        self.invalidate_from(invalidate, f"remedy {remedy.remedy_id}")
        return True

    def _escalate(self, finding: Finding, manifest: Mapping[str, Any]) -> str:
        escalations = self.state["agent_escalations"]
        if self.recovery_agent is None or len(escalations) >= MAX_AGENT_DECISIONS:
            return "escalation_required"
        payload = {
            "finding": finding.to_dict(),
            "remedy_history": list(self.state.get("remedy_history", [])),
            "attempt_manifests": [entry.get("manifest") for record in self.state["stages"].values()
                                  for entry in record.get("attempts", []) if entry.get("manifest")],
            "current_plan": json.loads(json.dumps(self.plan)),
            "valid_actions": ["registered_remedy", "revise_plan", "stop"],
            "valid_predefined_remedies": [self.registry.route(finding).remedy_id],
        }
        if hasattr(self.recovery_agent, "decide"):
            decision = self.recovery_agent.decide(payload)
        elif hasattr(self.recovery_agent, "diagnose"):
            try:
                decision = self.recovery_agent.diagnose(payload)
            except TypeError:
                intent_payload = {
                    "run_name": self.plan.get("run_name"), "goal": self.plan.get("goal", ""),
                    "smiles": self.plan.get("smiles", ""),
                    "requested_properties": tuple(self.plan.get("properties") or ()),
                    "polymer_class_hint": self.plan.get("polymer_class"),
                }
                intent = SimpleNamespace(to_dict=lambda: intent_payload)
                issue = SimpleNamespace(code=finding.code, stage=finding.stage,
                                        detail=payload, attempt=len(escalations) + 1,
                                        to_dict=lambda: finding.to_dict())
                decision = self.recovery_agent.diagnose(intent, self.plan, issue)
        else:
            decision = self.recovery_agent(payload)
        if hasattr(decision, "__dict__"):
            decision = vars(decision)
        decision = dict(decision)
        escalations.append({"finding": finding.to_dict(), "decision": decision,
                            "manifest": manifest.get("attempt_id"), "at": _now()})
        self._save()
        action = decision.get("action", "stop")
        if action == "registered_remedy":
            selected = decision.get("remedy_id")
            expected = self.registry.route(finding).remedy_id
            if selected != expected:
                return "escalation_required"
            # Agent selection does not override scientific bounds or caps.
            revised_finding = Finding(finding.code, finding.stage, finding.severity, "high",
                                      finding.details, selected)
            return "resume" if self._apply_remedy(revised_finding) else "escalation_required"
        if action in {"revise_plan", "retry"}:
            # retry means unchanged params by definition; ignore any modifications a
            # non-conforming agent attaches to it rather than reject the whole decision.
            modifications = dict(decision.get("modifications") or {}) if action == "revise_plan" else {}
            forbidden = {"path", "dir", "command", "script", "state", "artifact", "file"}
            unsafe = [key for key in modifications
                      if any(token in key.lower() for token in forbidden)]
            if unsafe:
                return "escalation_required"
            if self.override_validator is not None:
                try:
                    self.override_validator(modifications)
                except ValueError as exc:
                    escalations[-1]["validation_error"] = str(exc)
                    self._save()
                    return "escalation_required"
            candidate = json.loads(json.dumps(self.plan))
            candidate.setdefault("decided_params", {}).update(modifications)
            if self.plan_validator is not None:
                validation_findings = list(self.plan_validator(candidate))
                if any(item.get("severity") in {"structural", "blocking", "error", "fatal"}
                       for item in validation_findings):
                    escalations[-1]["validation_findings"] = validation_findings
                    self._save()
                    return "escalation_required"
            self.plan = candidate
            self.state["plan_hash"] = _canonical_hash(candidate)
            self.state["effective_parameters"].update(modifications)
            if self.plan_path is not None:
                atomic_write_json(self.plan_path, candidate)
            earliest = decision.get("invalidate_from") or finding.stage
            if earliest not in self.enabled_stages():
                return "escalation_required"
            self.invalidate_from(earliest, "recovery agent bounded revision")
            return "resume"
        return "failed"

    def run(self) -> dict[str, Any]:
        self.reconcile_inputs()
        while True:
            progressed = False
            for stage in self.enabled_stages():
                record = self.state["stages"][stage]
                if record.get("status") == "accepted":
                    continue
                if any(self.state["stages"][dep].get("status") != "accepted"
                       for dep in self._dependencies(stage)):
                    continue
                result, manifest = self._execute_stage(stage)
                progressed = True
                if result.status == "accepted":
                    record = self.state["stages"][stage]
                    record.update({"status": "accepted", "accepted_attempt": manifest["attempt_id"],
                                   "input_hash": manifest["input_hash"]})
                    self._save()
                    continue
                binding = [item for item in result.findings if item.severity in BLOCKING_SEVERITIES]
                finding = binding[0] if binding else Finding("UNEXPLAINED_STAGE_FAILURE", stage,
                                                             confidence="low")
                if self._apply_remedy(finding):
                    break
                outcome = self._escalate(finding, manifest)
                if outcome == "resume":
                    break
                record = self.state["stages"][stage]
                record["status"] = outcome
                self.state["status"] = outcome
                self.state["active_finding"] = finding.to_dict()
                self._save()
                return {"status": outcome, "stage": stage, "finding": finding.to_dict(),
                        "state_path": str(self.state_path)}
            else:
                if all(self.state["stages"][stage].get("status") == "accepted"
                       for stage in self.enabled_stages()):
                    self.state["status"] = "accepted"
                    self._save()
                    return {"status": "accepted", "run_name": self.plan.get("run_name"),
                            "state_path": str(self.state_path),
                            "accepted_attempts": {stage: self.state["stages"][stage]["accepted_attempt"]
                                                  for stage in self.enabled_stages()}}
            if not progressed:
                self.state["status"] = "failed"
                self._save()
                return {"status": "failed", "reason": "workflow made no progress",
                        "state_path": str(self.state_path)}


def inspect_workflow(run_dir: Path) -> dict[str, Any]:
    path = Path(run_dir) / "workflow_state.json"
    if not path.exists():
        return {"status": "not_found", "state_path": str(path)}
    state = json.loads(path.read_text())
    return {"status": state.get("status", "active"), "state": state,
            "state_path": str(path)}
