"""The one walk the suite never took: run-plan's own output, straight into materialization.

Every scientific_control test built its PlanDecision by hand, and every make_deterministic_plan
test stopped at the written file. Nothing joined them -- so when the 2026-09-04 fold re-pointed
`rationale` at `decisions[0].critique.findings` (which run-plan writes EMPTY, because a critique
that has not happened must not be pre-populated with a finding), _validate_decision's
"at least one rationale" requirement silently closed BOTH documented paths:

  * the novel-run-plan skill's step 3 -> step 6 hand-off, and
  * --baseline, the arm that exists precisely to materialize with no LLM in the loop.

The suite stayed green. These tests walk the seam.
"""

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))

from make_deterministic_plan import make_plan  # noqa: E402
from scientific_control import (  # noqa: E402
    PlanDecision,
    ScientificIntent,
    materialize_plan,
)

SMILES = "*CC(c1ccccc1)*"
INTENT = ScientificIntent(
    run_name="SCAFFOLD_WALK",
    goal="Predict Tg",
    smiles=SMILES,
    requested_properties=("tg",),
    polymer_class_hint="PSTR",
)


@pytest.fixture(scope="module")
def scaffold():
    """Exactly what `make_deterministic_plan.py run-plan` writes -- no hand edits."""
    return make_plan("SCAFFOLD_WALK", "PSTR", SMILES, {"tg"})


def test_run_plans_own_output_materializes_once_confidence_is_set(scaffold):
    """confidence is the ONLY gate (docs/AGENT_CONTRACT.md). Set it and nothing else."""
    plan = json.loads(json.dumps(scaffold))
    assert plan["decisions"][0]["critique"]["findings"] == [], (
        "run-plan must not pre-write a critique finding; if it starts to, this test stops "
        "covering the empty-findings case that broke materialization"
    )
    plan["confidence"] = "low"

    materialized = materialize_plan(INTENT, PlanDecision.from_run_plan(plan), base_plan=plan)

    assert materialized["plan_mode"] == "reasoned"
    assert materialized["confidence"] == "low"
    assert materialized["decided_params"]["preferred_ff"]


def test_the_baseline_arm_materializes_with_no_llm_edit_at_all(scaffold):
    """--baseline stamps confidence='low' at generation time, so the deterministic benchmark
    arm must go from run-plan to execution with zero edits in between."""
    plan = make_plan("SCAFFOLD_WALK", "PSTR", SMILES, {"tg"}, baseline=True)
    assert plan["confidence"] == "low"

    materialized = materialize_plan(INTENT, PlanDecision.from_run_plan(plan), base_plan=plan)
    assert materialized["plan_mode"] == "reasoned"


def test_unreviewed_confidence_still_blocks(scaffold):
    """The gate that IS meant to bind: an unadjudicated plan must not execute."""
    plan = json.loads(json.dumps(scaffold))
    assert plan["confidence"] == "unreviewed"
    with pytest.raises(ValueError, match="confidence must be one of"):
        materialize_plan(INTENT, PlanDecision.from_run_plan(plan), base_plan=plan)


def test_deleting_confidence_does_not_skip_the_gate(scaffold):
    plan = json.loads(json.dumps(scaffold))
    plan.pop("confidence")
    with pytest.raises(ValueError, match="deleting it does not skip the gate"):
        materialize_plan(INTENT, PlanDecision.from_run_plan(plan), base_plan=plan)


# ── The D-01 refusal has to bind on the plan path too ────────────────────────────────────

NYLON = "*CCCCCC(=O)N*"          # carbonyl_adjacent_N: the screen finds a measured blocker
NYLON_INTENT = ScientificIntent(
    run_name="PROBE_WALK", goal="Predict Tg", smiles=NYLON,
    requested_properties=("tg",), polymer_class_hint="PAMD",
)


@pytest.mark.requires_binaries          # a real EMC trial build; installed_styles() -> {} without LAMMPS
def test_an_unprobed_plan_is_probed_before_it_can_execute():
    """`--with-ff-probe` is opt-in on run-plan, so a plan can reach materialization with a
    D-01 row that only ASSERTS the class prior. The refusal -- nothing types this SMILES --
    is a safety property that has to bind on every path, and supplying `base_plan` skipped
    make_plan (and therefore the probe) entirely between the 2026-09-04 fold and this fix.
    """
    plan = make_plan("PROBE_WALK", "PAMD", NYLON, {"tg"})     # no probe
    assert "admissible" not in plan["decisions"][0]
    plan["confidence"] = "low"

    out = materialize_plan(NYLON_INTENT, PlanDecision.from_run_plan(plan), base_plan=plan)

    row = out["decisions"][0]
    assert "admissible" in row, "the refusal was inherited unmeasured"
    assert row["resolved_by"] == "forcefield.select_by_moiety"
    # Whatever it measured, the field and everything derived from it agree.
    assert out["decided_params"]["preferred_ff"] == row["choice"] or not row["choice"]


def test_a_plan_that_was_already_probed_is_not_reprobed():
    """Idempotent: a measured row is left exactly as the generator (or the critic) left it."""
    plan = make_plan("PROBE_WALK", "PAMD", NYLON, {"tg"})
    plan["decisions"][0]["admissible"] = ["pcff"]
    plan["decisions"][0]["choice"] = "pcff"
    plan["decisions"][0]["resolved_by"] = "already measured"
    plan["confidence"] = "low"

    out = materialize_plan(NYLON_INTENT, PlanDecision.from_run_plan(plan), base_plan=plan)

    assert out["decisions"][0]["admissible"] == ["pcff"]
    assert out["decisions"][0]["resolved_by"] == "already measured"
