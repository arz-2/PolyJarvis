"""Shared metrics schema for one polymer x arm ("polyjarvis" | "radonpy").

Every field here maps to a concrete, already-existing field in the source JSON files
documented in each metrics/*.py module's docstring -- nothing here is a new tracking
mechanism, it is a normalized read-out of what PolyJarvis and RadonPy already record.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class AccuracyBlock:
    density_g_cm3: Optional[float] = None
    density_exp_ref_g_cm3: Optional[float] = None
    bulk_modulus_GPa: Optional[float] = None
    bulk_modulus_method: Optional[str] = None  # e.g. "murnaghan" | "npt_fluctuation"
    bulk_modulus_exp_ref_range_GPa: Optional[list] = None
    gate_verdict: Optional[str] = None  # arm-native verdict string, unmapped
    method_note: str = ""  # explicit methodology-mismatch flag (never silently dropped)


@dataclass
class WallTimeBlock:
    build_time_s: Optional[float] = None
    qm_time_s: Optional[float] = None  # RadonPy only; None/0 for PolyJarvis
    md_compute_time_s: Optional[float] = None
    md_compute_time_method: Optional[str] = None  # "footer" | "mtime_fallback"
    orchestration_wall_time_s: Optional[float] = None


@dataclass
class LLMContributionBlock:
    applicable: bool = True  # False for the RadonPy arm
    plan_mode: Optional[str] = None  # "reasoned" | "deterministic" | "scaffold"
    llm_authored_decisions_total: int = 0  # out of D-01/D-02/D-03/D-04/D-08
    llm_authored_decisions_with_evidence: int = 0
    mechanized_gate_decisions_total: int = 0  # D-05/D-06/D-07
    literature_grounding_evidence_count: int = 0
    confidence: Optional[str] = None
    note: str = ""


@dataclass
class AdaptiveGatingBlock:
    recovery_agent_calls: int = 0
    cap_hit: bool = False  # recovery_agent_calls == cap AND status == "unresolved"
    auto_remedy_total: int = 0
    escalation_total: int = 0
    first_attempt_pass: Optional[bool] = None
    final_pass: Optional[bool] = None
    note: str = ""


@dataclass
class HumanInterventionBlock:
    cap_hit_intervention_needed: bool = False  # PolyJarvis: reuses cap_hit
    manual_interventions_logged: int = 0  # RadonPy: from interventions.jsonl
    note: str = ""


@dataclass
class ArmMetrics:
    polymer: str
    arm: str  # "polyjarvis" | "radonpy"
    forcefield: Optional[str] = None
    charge_method: Optional[str] = None
    accuracy: AccuracyBlock = field(default_factory=AccuracyBlock)
    wall_time: WallTimeBlock = field(default_factory=WallTimeBlock)
    llm_contribution: LLMContributionBlock = field(default_factory=LLMContributionBlock)
    adaptive_gating: AdaptiveGatingBlock = field(default_factory=AdaptiveGatingBlock)
    human_intervention: HumanInterventionBlock = field(default_factory=HumanInterventionBlock)

    def to_dict(self) -> dict:
        return asdict(self)
