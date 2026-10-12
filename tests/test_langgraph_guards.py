"""The cost and deadline guards — all that stands between an unattended graph and the GPUs.

There is no human confirmation step in this driver by design, so these two are the whole
safety story, and each encodes a fact about the surrounding system that is easy to get
wrong:

  cost      cost_estimate.total_gpu_hours is a documented LOWER BOUND -- `unpriced_stages`
            routinely holds equil, whose stage-length knobs resolve inside the MCP engine
            rather than from decided_params. A ceiling test against a lower bound is sound
            in exactly one direction, so the guard refuses loudly and never clears quietly.

  deadline  it never kills anything. LAMMPS is launched detached and survives the driver,
            while run_campaign's gpu_claim releases the ledger entry on SIGTERM -- so a
            hard kill would free a GPU that is still in use and invite a double-claim.
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "langgraph"))
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))

import guards  # noqa: E402
import nodes  # noqa: E402


# --- cost -------------------------------------------------------------------
def _plan(**estimate):
    return {"cost_estimate": estimate} if estimate else {"cost_estimate": None}


def test_priced_work_under_the_ceiling_is_admitted():
    v = guards.check_cost(_plan(total_gpu_hours=8.0), max_gpu_hours=40)
    assert v["ok"] and v["gpu_hours"] == 8.0


def test_priced_work_over_the_ceiling_refuses():
    v = guards.check_cost(_plan(total_gpu_hours=41.0), max_gpu_hours=40)
    assert not v["ok"] and v["status"] == "cost_exceeded"


def test_an_admitted_plan_still_carries_the_lower_bound_caveat():
    """Passing the ceiling is NOT evidence the run fits; the caveat must travel with it."""
    v = guards.check_cost(_plan(total_gpu_hours=8.0,
                                unpriced_stages=[{"stage": "equil", "reason": "..."}]),
                          max_gpu_hours=40)
    assert v["ok"] and v["unpriced"] == ["equil"] and "LOWER bound" in v["note"]


def test_no_ceiling_admits_any_priced_cost():
    assert guards.check_cost(_plan(total_gpu_hours=9999.0), max_gpu_hours=None)["ok"]


def test_an_unpriceable_plan_refuses_once_it_should_have_been_priced():
    v = guards.check_cost(_plan(unpriced_stages=["equil"]), max_gpu_hours=40)
    assert not v["ok"] and v["status"] == "cost_unknown"


def test_allow_unpriced_is_the_only_way_past_an_unpriceable_plan():
    v = guards.check_cost(_plan(unpriced_stages=["equil"]), max_gpu_hours=40,
                          allow_unpriced=True)
    assert v["ok"] and v["gpu_hours"] is None


def test_a_scaffold_is_not_yet_expected_to_carry_a_cost():
    """run-plan writes cost_estimate: null -- materialize_plan is what prices a run. The
    pre-gate must not mistake that for an unpriceable plan and refuse before the critic."""
    assert guards.check_cost(_plan(), max_gpu_hours=40, priced=False)["ok"]
    assert not guards.check_cost(_plan(), max_gpu_hours=40, priced=True)["ok"]


def test_a_broken_estimate_refuses_even_before_pricing_was_due():
    v = guards.check_cost({"cost_estimate": {"error": "no host curve"}},
                          max_gpu_hours=40, priced=False)
    assert not v["ok"] and v["status"] == "cost_unknown"


# --- D-01 -------------------------------------------------------------------
def test_an_unbuildable_chemistry_refuses_before_any_model_spend():
    v = guards.check_d01_admissible(
        {"smiles": "*X*", "decisions": [{"id": "D-01_ff", "admissible": [],
                                         "reason": "no field typed this unit"}]})
    assert not v["ok"] and v["status"] == "d01_refusal"
    assert "no field typed this unit" in v["detail"]


def test_a_buildable_chemistry_passes():
    assert guards.check_d01_admissible({"decisions": [{"admissible": ["pcff"]}]})["ok"]


def test_an_unprobed_decision_is_not_treated_as_a_refusal():
    """admissible=None means "not measured", which is different from "measured empty"."""
    assert guards.check_d01_admissible({"decisions": [{"admissible": None}]})["ok"]
    assert guards.check_d01_admissible({})["ok"]


# --- deadline ---------------------------------------------------------------
def _at(offset_hours):
    return (datetime.now(timezone.utc) + timedelta(hours=offset_hours)).isoformat()


def test_no_deadline_never_expires():
    assert not guards.deadline_expired({})


def test_a_future_deadline_has_not_expired():
    assert not guards.deadline_expired({"deadline_at": _at(1)})


def test_a_past_deadline_has_expired():
    assert guards.deadline_expired({"deadline_at": _at(-1)})


def test_an_expired_deadline_stops_the_graph_before_execute_and_kills_nothing(monkeypatch):
    """The stop must happen without ever entering execute -- and, crucially, without
    signalling anything: a detached LAMMPS outlives the driver while the GPU claim would be
    released on SIGTERM, so a kill here would free a card still in use."""
    pytest.importorskip("langgraph")
    from graph import build_graph

    def explode(_state):
        raise AssertionError("execute must not run after the deadline")

    monkeypatch.setattr(nodes, "execute", explode)
    monkeypatch.setattr(nodes, "entry_resolve",
                        lambda s: {"entry_node": "execute", "plan_path": "/nonexistent",
                                   "events": []})
    final = build_graph().invoke(
        {"run_name": "R", "smiles": "*CC*", "goal": "g", "properties": ["density"],
         "repo_root": "/tmp", "deadline_at": _at(-1), "events": []})
    assert final["status"] == "deadline_exceeded"


def test_deadline_exceeded_is_reported_as_resumable():
    from state import EXIT_CODES, RESUMABLE_STATUSES
    assert "deadline_exceeded" in RESUMABLE_STATUSES
    assert EXIT_CODES["deadline_exceeded"] == 4


def test_escalation_and_failure_are_terminal_not_resumable():
    """A run that escalated twice has spent both agent calls; resuming would re-execute the
    failing stage on real hardware and then fail again against the same exhausted cap."""
    from state import RESUMABLE_STATUSES
    assert "escalation_required" not in RESUMABLE_STATUSES
    assert "failed" not in RESUMABLE_STATUSES


# --- the gate nodes ---------------------------------------------------------
def test_cost_gate_refuses_when_there_is_no_plan_to_price(tmp_path):
    out = nodes.cost_guard_post({"plan_path": str(tmp_path / "missing.json"),
                                 "max_gpu_hours": 10})
    assert out["status"] == "plan_error"


def test_pre_gate_refuses_d01_without_spending_on_the_critic(tmp_path):
    path = tmp_path / "run_plan.json"
    path.write_text(json.dumps({"smiles": "*X*", "cost_estimate": None,
                                "decisions": [{"id": "D-01_ff", "admissible": []}]}))
    out = nodes.cost_guard_pre({"plan_path": str(path), "max_gpu_hours": 40})
    assert out["status"] == "d01_refusal"
