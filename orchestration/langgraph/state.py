#!/usr/bin/env python3
"""RunState — everything the graph carries between nodes, and the terminal vocabulary.

Deliberately flat and JSON-serialisable: every field here is either an input, something
read back off disk, or a decision the graph made, so a dump of the state is a complete
account of the run without needing the graph object. Nothing in here is authoritative --
run_plan.json, workflow_state.json and the per-attempt executor_state.json remain the
system of record, and any field that mirrors them is re-read rather than remembered.
"""
from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class RunState(TypedDict, total=False):
    # --- inputs -----------------------------------------------------------------
    run_name: str
    smiles: str
    goal: str
    properties: list[str]
    repo_root: str
    dry_run: bool
    no_llm: bool
    resume: bool
    max_gpu_hours: float | None
    allow_unpriced: bool
    deadline_at: str                  # ISO8601 UTC; see guards.deadline_expired

    # --- routing ----------------------------------------------------------------
    entry_node: str

    # --- classification ---------------------------------------------------------
    canonical_smiles: str | None
    cache_hit: bool
    polymer_class: str | None
    class_source: str | None          # radonpy_polyinfo | override | characterization_cache
    classification_path: str | None
    chemistry: dict[str, Any]         # chemistry_policy.consistency() over the repeat unit

    # --- plan -------------------------------------------------------------------
    plan_path: str | None
    plan_mode: str | None
    confidence: str | None
    d01_admissible: list[str] | None
    cost_gpu_hours: float | None
    cost_unpriced: list[str]

    # --- the two model calls ----------------------------------------------------
    grounding_path: str | None
    critic_verdict: str | None        # agrees | disagrees | no_evidence | error | skipped
    adjudication: dict[str, Any]

    # --- execution --------------------------------------------------------------
    execute_result: dict[str, Any]
    workflow_status: str | None
    workflow_stage: str | None
    finding_code: str | None

    # --- terminal ---------------------------------------------------------------
    status: str
    detail: str
    exit_code: int
    events: Annotated[list[dict[str, Any]], operator.add]


# Terminal statuses and their exit codes.
#
# `escalation_required` and `failed` are TERMINAL, not retryable, and that is the single
# most important fact about this graph. agent_escalations is a run-global list in
# workflow_state.json and WorkflowEngine._escalate returns early once it reaches
# MAX_AGENT_DECISIONS, so by the time run() hands back `escalation_required` both agent
# calls are already spent. Re-entering resume_campaign would re-execute the failing stage --
# real GPU time -- and then escalate-fail again against the same exhausted cap. The engine's
# own loop is the retry loop; wrapping a second one around it only burns hardware.
EXIT_CODES: dict[str, int] = {
    "accepted": 0,
    "escalation_required": 2,
    "failed": 3,
    "deadline_exceeded": 4,          # resumable: nothing was killed, see guards
    "cost_exceeded": 5,
    "cost_unknown": 5,
    "classify_error": 6,
    "plan_error": 6,
    "materialize_error": 6,
    "d01_refusal": 7,
    "locked": 8,
}

TERMINAL_STATUSES = frozenset(EXIT_CODES)

#: Statuses that leave the campaign resumable by a later `--resume` invocation.
RESUMABLE_STATUSES = frozenset({"deadline_exceeded", "locked"})

#: What make_deterministic_plan stamps on a fresh plan. It is not a valid confidence, and
#: that is deliberate -- it is the one thing standing between a scaffold and execution.
UNREVIEWED = "unreviewed"

VALID_CONFIDENCE = frozenset({"low", "medium", "high"})
