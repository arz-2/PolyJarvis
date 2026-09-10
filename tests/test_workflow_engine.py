import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))

from workflow_engine import (  # noqa: E402
    ACTIVE_BLOCKING_CODES,
    MAX_AGENT_DECISIONS,
    MAX_AUTOMATIC_REMEDIES,
    Finding,
    RemedyRegistry,
    StageResult,
    WorkflowEngine,
    pressure_point_drop_allowed,
)
from scientific_control import validate_overrides  # noqa: E402


class FakeExecutor:
    def __init__(self, results=None):
        self.results = {key: list(value) for key, value in (results or {}).items()}
        self.calls = []

    def execute(self, stage, context):
        self.calls.append((stage, context))
        attempt_dir = Path(context["attempt_dir"])
        artifact = attempt_dir / f"{stage}.json"
        artifact.write_text(json.dumps({"stage": stage, "parameters": context["parameters"]}))
        if self.results.get(stage):
            result = self.results[stage].pop(0)
            return StageResult(result.status, result.findings, (str(artifact),), result.outputs)
        outputs = {}
        if stage == "thermal":
            outputs["tg_gate_verdict"] = "TG_REPORTABLE"
        if stage == "mechanical":
            outputs.update({"method": "murnaghan", "bm_gate_verdict": "BM_REPORTABLE"})
        return StageResult("accepted", artifacts=(str(artifact),), outputs=outputs)


def plan(**params):
    return {"run_name": "WF", "polymer_class": "PSTR",
            "properties": ["density", "tg", "bulk_modulus"],
            "decided_params": params}


def test_registry_covers_every_active_blocking_code():
    RemedyRegistry().assert_complete(ACTIVE_BLOCKING_CODES)


def test_success_accepts_attempt_manifests_and_never_escalates(tmp_path):
    class Recovery:
        def decide(self, payload):
            raise AssertionError("recovery agent must not be called on success")

    result = WorkflowEngine(tmp_path, plan(), FakeExecutor(), recovery_agent=Recovery()).run()

    assert result["status"] == "accepted"
    state = json.loads((tmp_path / "workflow_state.json").read_text())
    assert all(row["status"] == "accepted" for row in state["stages"].values())
    assert all((tmp_path / "attempts" / stage / attempt / "executor_state.json").is_file()
               for stage, attempt in result["accepted_attempts"].items())


def test_low_confidence_escalates_before_plan_mutation(tmp_path):
    finding = Finding("TG_NOT_REPORTABLE", "thermal", confidence="low")
    fake = FakeExecutor({"thermal": [StageResult("remedy_required", (finding,))]})
    engine = WorkflowEngine(tmp_path, plan(tg_steps_per_t=100), fake)

    result = engine.run()

    assert result["status"] == "escalation_required"
    assert engine.state["effective_parameters"]["tg_steps_per_t"] == 100
    assert engine.state["remedy_counters"]["total"] == 0


class RevisePlanRecovery:
    """Matches production SubprocessRecoveryAgent's 3-arg diagnose(intent, plan, issue) --
    _escalate's first attempt (a 1-arg diagnose(payload) call) raises TypeError against this
    signature and falls back to the 3-arg call, exactly like the real subprocess adapter."""

    def __init__(self, modifications, action="revise_plan"):
        self.modifications = modifications
        self.action = action
        self.calls = []

    def diagnose(self, intent, plan, issue):
        self.calls.append((intent, plan, issue))
        return {"action": self.action, "modifications": dict(self.modifications),
                "rationale": "test"}


def test_escalation_applies_revise_plan_and_resumes(tmp_path):
    finding = Finding("TG_NOT_REPORTABLE", "thermal", confidence="low")
    fake = FakeExecutor({"thermal": [StageResult("remedy_required", (finding,))]})
    recovery = RevisePlanRecovery({"tg_t_step_K": 10})
    engine = WorkflowEngine(tmp_path, plan(tg_t_step_K=20), fake,
                            recovery_agent=recovery, override_validator=validate_overrides)

    result = engine.run()

    assert result["status"] == "accepted"
    assert len(recovery.calls) == 1
    thermal_calls = [call for call in fake.calls if call[0] == "thermal"]
    assert len(thermal_calls) == 2
    assert thermal_calls[-1][1]["parameters"]["tg_t_step_K"] == 10
    assert engine.state["agent_escalations"][0]["decision"]["action"] == "revise_plan"


def test_escalation_rejects_out_of_range_modification(tmp_path):
    finding = Finding("TG_NOT_REPORTABLE", "thermal", confidence="low")
    fake = FakeExecutor({"thermal": [StageResult("remedy_required", (finding,))]})
    recovery = RevisePlanRecovery({"tg_t_step_K": 99999})
    engine = WorkflowEngine(tmp_path, plan(tg_t_step_K=20), fake,
                            recovery_agent=recovery, override_validator=validate_overrides)

    result = engine.run()

    assert result["status"] == "escalation_required"
    assert engine.state["effective_parameters"]["tg_t_step_K"] == 20
    assert "validation_error" in engine.state["agent_escalations"][0]


def test_escalation_stops_after_max_agent_decisions(tmp_path):
    finding = Finding("TG_NOT_REPORTABLE", "thermal", confidence="low")
    fake = FakeExecutor({"thermal": [StageResult("remedy_required", (finding,))] * 3})
    recovery = RevisePlanRecovery({"tg_t_step_K": 10})
    engine = WorkflowEngine(tmp_path, plan(tg_t_step_K=20), fake,
                            recovery_agent=recovery, override_validator=validate_overrides)

    result = engine.run()

    assert result["status"] == "escalation_required"
    assert len(recovery.calls) == MAX_AGENT_DECISIONS


def test_retry_ignores_any_attached_modifications(tmp_path):
    finding = Finding("TG_NOT_REPORTABLE", "thermal", confidence="low")
    fake = FakeExecutor({"thermal": [StageResult("remedy_required", (finding,))]})
    recovery = RevisePlanRecovery({"tg_t_step_K": 999999}, action="retry")
    engine = WorkflowEngine(tmp_path, plan(tg_t_step_K=20), fake,
                            recovery_agent=recovery, override_validator=validate_overrides)

    result = engine.run()

    assert result["status"] == "accepted"
    assert engine.state["effective_parameters"]["tg_t_step_K"] == 20


def test_tg_gate_cannot_be_accepted_from_process_completion(tmp_path):
    review = {"Tg_K": 350.0, "tg_gate_verdict": "TG_REVIEW",
              "tg_gate_cause": "breakpoint_ambiguity"}
    fake = FakeExecutor({"thermal": [
        StageResult("accepted", outputs=dict(review)),
        StageResult("accepted", outputs={**review, "Tg_K": 351.0}),
    ]})
    result = WorkflowEngine(tmp_path, plan(tg_t_step_K=20), fake).run()

    assert result["status"] == "escalation_required"
    thermal_calls = [call for call in fake.calls if call[0] == "thermal"]
    assert len(thermal_calls) == 2
    assert thermal_calls[-1][1]["parameters"]["tg_t_step_K"] == 10


def test_transient_retry_declines_when_the_disk_is_full(tmp_path):
    """Every recovery event on this checkout has been a blind transient_retry. A full
    filesystem makes an unchanged resubmission certain to repeat, so the rung is worth more
    escalated with a named cause than spent reproducing the crash."""
    import workflow_engine

    finding = Finding("PROCESS_FAILED", "equilibration")
    fake = FakeExecutor({"equilibration": [StageResult("remedy_required", (finding,))]})
    engine = WorkflowEngine(tmp_path, plan(), fake)

    full = SimpleNamespace(total=int(1e12), used=int(1e12), free=int(1e9))  # 1 GB free
    with patch.object(workflow_engine.shutil, "disk_usage", return_value=full):
        result = engine.run()

    assert result["status"] == "escalation_required"
    assert len([c for c in fake.calls if c[0] == "equilibration"]) == 1
    events = [json.loads(line) for line in
              (tmp_path / "recovery_log.jsonl").read_text().splitlines()]
    rejected = [e for e in events if e["event"] == "auto_remedy_rejected"]
    assert rejected and "GB free" in rejected[0]["reason"]


def test_transient_retry_still_applies_when_resources_are_fine(tmp_path):
    """Both halves of the preflight must be stubbed, not just the disk.

    _resource_refusal checks free disk AND hardware_runtime.free_gpus(), and the latter reads
    the REAL host ledger. Stubbing only disk left this test asserting "resources are fine"
    while the GPUs were whatever the machine happened to be doing -- so it passed on an idle
    workstation and failed on a busy one, which is exactly what happened on 2026-09-09 with
    four campaigns occupying all four GPUs. The name promises a hermetic condition; make it one.
    """
    import hardware_runtime
    import workflow_engine

    finding = Finding("PROCESS_FAILED", "equilibration")
    fake = FakeExecutor({"equilibration": [StageResult("remedy_required", (finding,))]})
    engine = WorkflowEngine(tmp_path, plan(), fake)

    roomy = SimpleNamespace(total=int(1e13), used=0, free=int(9e12))
    with patch.object(workflow_engine.shutil, "disk_usage", return_value=roomy), \
         patch.object(hardware_runtime, "free_gpus", return_value=[0, 1, 2, 3]):
        result = engine.run()

    assert result["status"] == "accepted"
    assert len([c for c in fake.calls if c[0] == "equilibration"]) == 2


def test_transient_retry_declines_when_no_gpu_is_free(tmp_path):
    """The GPU half of the preflight read gpu_per_run from effective_parameters, where it
    never appears (it is not in SNAPSHOT_KEYS), so the check silently never fired."""
    import hardware_runtime
    import workflow_engine

    finding = Finding("PROCESS_FAILED", "equilibration")
    fake = FakeExecutor({"equilibration": [StageResult("remedy_required", (finding,))]})
    engine = WorkflowEngine(tmp_path, plan(), fake)

    roomy = SimpleNamespace(total=int(1e13), used=0, free=int(9e12))
    with patch.object(workflow_engine.shutil, "disk_usage", return_value=roomy), \
         patch.object(hardware_runtime, "free_gpus", return_value=[]):
        result = engine.run()

    assert result["status"] == "escalation_required"
    events = [json.loads(line) for line in
              (tmp_path / "recovery_log.jsonl").read_text().splitlines()]
    rejected = [e for e in events if e["event"] == "auto_remedy_rejected"]
    assert rejected and "GPU(s) free" in rejected[0]["reason"]


def test_transient_retry_ignores_gpus_for_stages_that_never_claim_one(tmp_path):
    """EMC builds on CPU and the summary is pure analysis, so GPU contention is not a reason
    to refuse either a build or a summary retry."""
    import hardware_runtime
    import workflow_engine

    finding = Finding("PROCESS_FAILED", "build")
    fake = FakeExecutor({"build": [StageResult("remedy_required", (finding,))]})
    engine = WorkflowEngine(tmp_path, plan(), fake)

    roomy = SimpleNamespace(total=int(1e13), used=0, free=int(9e12))
    with patch.object(workflow_engine.shutil, "disk_usage", return_value=roomy), \
         patch.object(hardware_runtime, "free_gpus", return_value=[]):
        result = engine.run()

    assert result["status"] == "accepted"
    assert len([c for c in fake.calls if c[0] == "build"]) == 2


def test_auto_remedy_is_rejected_when_it_violates_a_protocol_floor(tmp_path):
    """Auto-remedies used to bypass every check an agent decision must pass, so tg_breakpoint
    could halve tg_t_step_K straight through the class's tg_min_steps_per_T floor. The
    rejection escalates instead of silently shipping an infeasible sweep."""
    review = {"Tg_K": 350.0, "tg_gate_verdict": "TG_REVIEW",
              "tg_gate_cause": "breakpoint_ambiguity"}
    fake = FakeExecutor({"thermal": [StageResult("accepted", outputs=dict(review))]})
    engine = WorkflowEngine(tmp_path, plan(tg_t_step_K=20, tg_rate_K_per_ns=100, dt_fs=1.0),
                            fake)

    result = engine.run()

    assert result["status"] == "escalation_required"
    assert engine.state["effective_parameters"]["tg_t_step_K"] == 20
    assert len([call for call in fake.calls if call[0] == "thermal"]) == 1
    events = [json.loads(line) for line in
              (tmp_path / "recovery_log.jsonl").read_text().splitlines()]
    rejected = [e for e in events if e["event"] == "auto_remedy_rejected"]
    assert rejected and "tg_min_steps_per_T" in rejected[0]["reason"]


def test_tg_review_method_gap_declines_the_breakpoint_remedy(tmp_path):
    """Halving tg_t_step_K halves the samples per temperature. That resolves an ambiguous
    breakpoint but makes a noisy transition worse, so the method_gap sub-case must escalate
    to the agent (whose lever, a lower tg_rate_K_per_ns, invalidates cooling) rather than
    spend a rung making the fit worse."""
    review = {"Tg_K": 350.0, "tg_gate_verdict": "TG_REVIEW", "tg_gate_cause": "method_gap"}
    fake = FakeExecutor({"thermal": [StageResult("accepted", outputs=dict(review))]})
    result = WorkflowEngine(tmp_path, plan(tg_t_step_K=20), fake).run()

    assert result["status"] == "escalation_required"
    assert len([call for call in fake.calls if call[0] == "thermal"]) == 1
    assert result["finding"]["code"] == "TG_REVIEW"


def test_minimize_not_converged_escalates_tolerance_and_iteration_caps(tmp_path):
    finding = Finding("MINIMIZE_NOT_CONVERGED", "equilibration")
    fake = FakeExecutor({"equilibration": [
        StageResult("remedy_required", (finding,)),
        StageResult("remedy_required", (finding,)),
    ]})
    engine = WorkflowEngine(
        tmp_path,
        plan(minimize_maxiter=50000, minimize_maxeval=100000,
             minimize_etol=1e-6, minimize_ftol=1e-6),
        fake,
    )

    result = engine.run()

    assert result["status"] == "accepted"
    equil_calls = [call for call in fake.calls if call[0] == "equilibration"]
    assert len(equil_calls) == 3
    # attempt 1: x4 iteration/eval caps, x10 looser tolerances
    p1 = equil_calls[1][1]["parameters"]
    assert p1["minimize_maxiter"] == 200000
    assert p1["minimize_maxeval"] == 400000
    assert round(p1["minimize_etol"], 10) == 1e-5
    assert round(p1["minimize_ftol"], 10) == 1e-5
    assert "equilibration_resume_from" not in p1  # stage 0 -- always a full restart
    # attempt 2: escalates again off the frozen baseline, not off attempt 1's already-raised value
    p2 = equil_calls[2][1]["parameters"]
    assert p2["minimize_maxiter"] == 800000
    assert round(p2["minimize_etol"], 10) == 1e-4


def test_minimize_not_converged_routes_to_raise_minimize_tolerance():
    from workflow_engine import RemedyRegistry, Finding as F
    registry = RemedyRegistry()
    remedy = registry.route(F("MINIMIZE_NOT_CONVERGED", "equilibration"))
    assert remedy.remedy_id == "raise_minimize_tolerance"


def test_thermal_change_invalidates_mechanical_and_summary_not_build(tmp_path):
    first = WorkflowEngine(tmp_path, plan(tg_t_step_K=20), FakeExecutor())
    assert first.run()["status"] == "accepted"
    build_attempt = first.state["stages"]["build"]["accepted_attempt"]

    second_fake = FakeExecutor()
    second = WorkflowEngine(tmp_path, plan(tg_t_step_K=10), second_fake)
    assert second.run()["status"] == "accepted"

    assert second.state["stages"]["build"]["accepted_attempt"] == build_attempt
    called = [stage for stage, _ in second_fake.calls]
    assert called == ["thermal", "mechanical", "summary"]


def test_changed_accepted_artifact_invalidates_producer_and_descendants(tmp_path):
    fake = FakeExecutor()
    engine = WorkflowEngine(tmp_path, plan(), fake)
    engine.run()
    manifest_path = (tmp_path / "attempts" / "build" /
                     engine.state["stages"]["build"]["accepted_attempt"] / "executor_state.json")
    artifact = Path(json.loads(manifest_path.read_text())["artifacts"][0]["path"])
    artifact.write_text("changed")

    resumed_fake = FakeExecutor()
    resumed = WorkflowEngine(tmp_path, plan(), resumed_fake)
    assert resumed.run()["status"] == "accepted"
    assert [stage for stage, _ in resumed_fake.calls] == [
        "build", "equilibration", "cooling", "thermal", "mechanical", "summary"
    ]


def test_interrupted_running_attempt_is_recovered_as_incomplete(tmp_path):
    engine = WorkflowEngine(tmp_path, plan(), FakeExecutor())
    engine.state["stages"]["build"]["status"] = "running"
    engine._save()

    resumed = WorkflowEngine(tmp_path, plan(), FakeExecutor())

    assert resumed.state["stages"]["build"]["status"] == "incomplete"
    assert "accepted_attempt" not in resumed.state["stages"]["build"]


def test_incomplete_attempt_reattaches_to_same_attempt_dir_not_a_fresh_one(tmp_path):
    """A prior process death (killed session, host reboot) mid-executor-call must not cause the
    next run to mint attempt-0002 and silently resubmit -- an executor that persisted a
    long-running background job's chain_id in attempt-0001's own directory (e.g.
    do_equil_and_check's pending_equil_submission.json) needs that same directory back so it can
    reattach instead of discarding real, possibly already-finished work."""
    engine = WorkflowEngine(tmp_path, plan(), FakeExecutor())
    input_hash = engine._input_hash("build")
    attempt_id, attempt_dir = engine._new_attempt("build", input_hash)
    marker = attempt_dir / "pending_submission.json"
    marker.write_text('{"chain_id": "abc123"}')

    resumed = WorkflowEngine(tmp_path, plan(), FakeExecutor())
    assert resumed.state["stages"]["build"]["status"] == "incomplete"

    reused_id, reused_dir = resumed._new_attempt("build", input_hash)

    assert reused_id == attempt_id
    assert reused_dir == attempt_dir
    assert marker.is_file()  # the reattach point survives -- not wiped by a fresh mkdir
    assert len(resumed.state["stages"]["build"]["attempts"]) == 1  # no second entry appended
    assert resumed.state["stages"]["build"]["status"] == "running"


def test_incomplete_attempt_with_changed_input_hash_gets_a_fresh_attempt(tmp_path):
    """A changed input (e.g. a recovery-agent revise_plan between the death and the resume)
    must not reattach to a stale attempt scoped to the old inputs."""
    engine = WorkflowEngine(tmp_path, plan(), FakeExecutor())
    old_hash = engine._input_hash("build")
    old_id, _ = engine._new_attempt("build", old_hash)

    resumed = WorkflowEngine(tmp_path, plan(), FakeExecutor())
    new_id, new_dir = resumed._new_attempt("build", "a-completely-different-hash")

    assert new_id != old_id
    assert new_dir.is_dir()


def test_agent_only_code_escalates_immediately_without_local_remedy(tmp_path):
    """BACKBONE_TYPES_UNRESOLVED has no registered remedy -- it must reach _escalate on the
    very first failure, never spend an automatic-remedy attempt first."""
    finding = Finding("BACKBONE_TYPES_UNRESOLVED", "equilibration")
    fake = FakeExecutor({"equilibration": [StageResult("remedy_required", (finding,))]})
    engine = WorkflowEngine(tmp_path, plan(), fake)

    result = engine.run()

    assert result["status"] == "escalation_required"
    equil_calls = [call for call in fake.calls if call[0] == "equilibration"]
    assert len(equil_calls) == 1
    assert engine.state["remedy_counters"]["total"] == 0
    assert engine.state["agent_escalations"] == []


class RegisteredRemedyRecovery:
    def __init__(self, remedy_id):
        self.remedy_id = remedy_id
        self.calls = []

    def diagnose(self, intent, plan, issue):
        self.calls.append((intent, plan, issue))
        return {"action": "registered_remedy", "remedy_id": self.remedy_id, "rationale": "test"}


def test_registered_remedy_action_applies_despite_low_confidence(tmp_path):
    """_escalate resets confidence to 'high' before replaying an agent-selected registered
    remedy -- a low-confidence finding that skipped the automatic ladder must still be
    remediable once the agent explicitly names the one predefined remedy for its code."""
    finding = Finding("EQUIL_DRIFT", "equilibration", confidence="low",
                       details={"extension_ns": 5.0})
    fake = FakeExecutor({"equilibration": [StageResult("remedy_required", (finding,))]})
    recovery = RegisteredRemedyRecovery("continue_npt")
    engine = WorkflowEngine(tmp_path, plan(), fake, recovery_agent=recovery)

    result = engine.run()

    assert result["status"] == "accepted"
    assert len(recovery.calls) == 1
    assert engine.state["remedy_counters"]["by_id"]["continue_npt"] == 1
    equil_calls = [call for call in fake.calls if call[0] == "equilibration"]
    assert equil_calls[-1][1]["parameters"]["npt_continuation_ns"] == 5.0


def test_registered_remedy_action_rejects_mismatched_remedy_id(tmp_path):
    """An agent naming a remedy other than the one route()'d for this finding's code must be
    rejected outright -- it never gets to pick an arbitrary lever off-menu."""
    finding = Finding("EQUIL_DRIFT", "equilibration", confidence="low")
    fake = FakeExecutor({"equilibration": [StageResult("remedy_required", (finding,))]})
    recovery = RegisteredRemedyRecovery("raise_minimize_tolerance")
    engine = WorkflowEngine(tmp_path, plan(), fake, recovery_agent=recovery)

    result = engine.run()

    assert result["status"] == "escalation_required"
    assert engine.state["remedy_counters"]["total"] == 0


def test_route_local_cap_exhaustion_escalates_after_automatic_retries(tmp_path):
    """raise_minimize_tolerance's local_cap is 2 -- a third MINIMIZE_NOT_CONVERGED finding on the same
    route must escalate rather than apply a third automatic doubling."""
    finding = Finding("MINIMIZE_NOT_CONVERGED", "equilibration")
    fake = FakeExecutor({"equilibration": [StageResult("remedy_required", (finding,))] * 3})
    engine = WorkflowEngine(tmp_path, plan(cool_block_hold_steps=1000), fake)

    result = engine.run()

    assert result["status"] == "escalation_required"
    assert engine.state["remedy_counters"]["by_route"]["raise_minimize_tolerance:equilibration"] == 2
    equil_calls = [call for call in fake.calls if call[0] == "equilibration"]
    assert len(equil_calls) == 3


def test_apply_remedy_respects_global_automatic_remedy_cap(tmp_path):
    """MAX_AUTOMATIC_REMEDIES is a budget across every route, not just per-route -- once spent,
    even a fresh route with capacity left of its own must not auto-apply."""
    engine = WorkflowEngine(tmp_path, plan(), FakeExecutor())
    engine.state["remedy_counters"]["total"] = MAX_AUTOMATIC_REMEDIES
    finding = Finding("EQUIL_DRIFT", "equilibration")

    assert engine._apply_remedy(finding) is False
    assert engine.state["remedy_counters"]["total"] == MAX_AUTOMATIC_REMEDIES


class DecideRecovery:
    def __init__(self, action="stop"):
        self.action = action
        self.calls = []

    def decide(self, payload):
        self.calls.append(payload)
        return {"action": self.action, "rationale": "test", "modifications": {}}


def test_escalate_dispatches_to_decide_when_available(tmp_path):
    """_escalate prefers a .decide(payload) method over .diagnose(...) when both could apply --
    exercised separately from the .diagnose(intent, plan, issue) fallback covered elsewhere."""
    finding = Finding("BACKBONE_TYPES_UNRESOLVED", "equilibration")
    fake = FakeExecutor({"equilibration": [StageResult("remedy_required", (finding,))]})
    recovery = DecideRecovery(action="stop")
    engine = WorkflowEngine(tmp_path, plan(), fake, recovery_agent=recovery)

    result = engine.run()

    assert result["status"] == "failed"
    assert len(recovery.calls) == 1
    assert recovery.calls[0]["valid_predefined_remedies"] == ["agent_only"]
    assert engine.state["agent_escalations"][0]["decision"]["action"] == "stop"


def _read_recovery_log(tmp_path):
    log_path = tmp_path / "recovery_log.jsonl"
    if not log_path.is_file():
        return []
    return [json.loads(line) for line in log_path.read_text().splitlines() if line.strip()]


def test_auto_remedy_appends_to_recovery_log(tmp_path):
    finding = Finding("MINIMIZE_NOT_CONVERGED", "equilibration")
    fake = FakeExecutor({"equilibration": [StageResult("remedy_required", (finding,))]})
    engine = WorkflowEngine(tmp_path, plan(cool_block_hold_steps=1000), fake)

    assert engine.run()["status"] == "accepted"

    events = _read_recovery_log(tmp_path)
    assert [e["event"] for e in events] == ["auto_remedy"]
    assert events[0]["remedy_id"] == "raise_minimize_tolerance"
    assert events[0]["code"] == "MINIMIZE_NOT_CONVERGED"
    assert events[0]["run_name"] == "WF"


def test_escalation_appends_outcome_to_recovery_log(tmp_path):
    finding = Finding("TG_NOT_REPORTABLE", "thermal", confidence="low")
    fake = FakeExecutor({"thermal": [StageResult("remedy_required", (finding,))]})
    recovery = RevisePlanRecovery({"tg_t_step_K": 10})
    engine = WorkflowEngine(tmp_path, plan(tg_t_step_K=20), fake,
                            recovery_agent=recovery, override_validator=validate_overrides)

    assert engine.run()["status"] == "accepted"

    events = _read_recovery_log(tmp_path)
    assert [e["event"] for e in events] == ["escalation"]
    assert events[0]["outcome"] == "resume"
    assert events[0]["action"] == "revise_plan"
    assert events[0]["code"] == "TG_NOT_REPORTABLE"


def test_escalation_without_recovery_agent_logs_the_reason(tmp_path):
    finding = Finding("BACKBONE_TYPES_UNRESOLVED", "equilibration")
    fake = FakeExecutor({"equilibration": [StageResult("remedy_required", (finding,))]})
    engine = WorkflowEngine(tmp_path, plan(), fake)

    engine.run()

    events = _read_recovery_log(tmp_path)
    assert [e["event"] for e in events] == ["escalation"]
    assert events[0]["outcome"] == "escalation_required"
    assert events[0]["reason"] == "no_recovery_agent_configured"


def test_pressure_point_drop_requires_identifiable_remaining_series():
    assert pressure_point_drop_allowed({-500: "failed", 0: "accepted", 500: "accepted",
                                        1000: "accepted", 2000: "accepted"})
    assert not pressure_point_drop_allowed({0: "accepted", 500: "accepted",
                                            1000: "accepted", 2000: "failed"})
    assert not pressure_point_drop_allowed({-500: "accepted", 0: "accepted",
                                            500: "accepted", 1000: "failed"})


# ─── BM_LADDER_NOT_CONVERGED (Feature 2: reactive ladder-widening remedy) ──────────

def test_bm_ladder_not_converged_routes_to_murnaghan_ladder_extend():
    from workflow_engine import RemedyRegistry, Finding as F
    registry = RemedyRegistry()
    remedy = registry.route(F("BM_LADDER_NOT_CONVERGED", "mechanical"))
    assert remedy.remedy_id == "murnaghan_ladder_extend"
    assert remedy.local_cap == 1
    assert remedy.invalidate_from == "mechanical"


def test_murnaghan_ladder_extend_widens_compression_and_reuses_resample_fields():
    """Reuses mechanical_resample_points/mechanical_sampling_factor -- the exact fields
    murnaghan_resample already uses -- so do_mechanical's existing merge-by-pressure-value
    retry logic needs no changes to support this remedy."""
    registry = RemedyRegistry()
    remedy = registry.route(Finding("BM_LADDER_NOT_CONVERGED", "mechanical"))
    finding = Finding("BM_LADDER_NOT_CONVERGED", "mechanical", details={
        "gate_output": {
            "murnaghan_result": {
                "pressures_atm": [1, 1000, 2500, 5000, 10000, 15000],
                "B0_GPa": 1.65,
            },
        },
    })

    revised = remedy.action({}, finding, 1)

    assert revised["mechanical_resample_points"] == [30000]
    assert revised["mechanical_sampling_factor"] == 1


def test_murnaghan_ladder_extend_falls_back_to_fluctuation_k_when_no_b0():
    remedy = RemedyRegistry().route(Finding("BM_LADDER_NOT_CONVERGED", "mechanical"))
    finding = Finding("BM_LADDER_NOT_CONVERGED", "mechanical", details={
        "gate_output": {
            "murnaghan_result": {"pressures_atm": [0, 3000, 7000, 15000], "B0_GPa": None},
            "pressure_selection": {"fluctuation_K_GPa": 2.0},
        },
    })

    revised = remedy.action({}, finding, 1)

    assert revised["mechanical_resample_points"] == [30000]


def test_murnaghan_ladder_extend_respects_ceiling():
    remedy = RemedyRegistry().route(Finding("BM_LADDER_NOT_CONVERGED", "mechanical"))
    finding = Finding("BM_LADDER_NOT_CONVERGED", "mechanical", details={
        "gate_output": {"murnaghan_result": {
            "pressures_atm": [0, 15000, 30000], "B0_GPa": 5.0}},
    })

    with pytest.raises(ValueError):
        remedy.action({}, finding, 1)


def test_murnaghan_ladder_extend_requires_prior_pressures():
    remedy = RemedyRegistry().route(Finding("BM_LADDER_NOT_CONVERGED", "mechanical"))
    finding = Finding("BM_LADDER_NOT_CONVERGED", "mechanical", details={"gate_output": {}})

    with pytest.raises(ValueError):
        remedy.action({}, finding, 1)


def test_binding_gate_failure_is_additive_to_bm_reportable():
    from workflow_engine import binding_gate_failure

    reportable = {"bm_gate_verdict": "BM_REPORTABLE", "bm_convergence_verdict": "BM_LADDER_CONVERGED"}
    assert binding_gate_failure("mechanical", reportable) is None

    not_converged = {"bm_gate_verdict": "BM_REPORTABLE",
                     "bm_convergence_verdict": "BM_LADDER_NOT_CONVERGED",
                     "bm_convergence_confidence": "high"}
    finding = binding_gate_failure("mechanical", not_converged)
    assert finding.code == "BM_LADDER_NOT_CONVERGED"
    assert finding.confidence == "high"

    # bm_gate_verdict's own three-value contract still takes precedence and is unaffected
    inadmissible = {"bm_gate_verdict": "BM_INADMISSIBLE", "bm_gate_reasons": ["K is negative"],
                    "bm_convergence_verdict": "BM_LADDER_CONVERGED"}
    finding = binding_gate_failure("mechanical", inadmissible)
    assert finding.code == "BM_INADMISSIBLE"


def test_binding_gate_failure_propagates_low_confidence_from_convergence_verdict():
    from workflow_engine import binding_gate_failure

    outputs = {"bm_gate_verdict": "BM_REPORTABLE",
              "bm_convergence_verdict": "BM_LADDER_NOT_CONVERGED",
              "bm_convergence_confidence": "low"}
    finding = binding_gate_failure("mechanical", outputs)
    assert finding.confidence == "low"


def test_bm_ladder_not_converged_applies_the_extend_remedy_and_reruns(tmp_path):
    """End-to-end through the engine (not just the routing/action unit tests above):
    binding_gate_failure fires even though do_mechanical's own accepted=True
    (bm_gate_verdict==BM_REPORTABLE) -- the engine's independent gate re-check on an
    "accepted" StageResult is what actually blocks acceptance until the ladder
    identifies B0', then re-executes mechanical with mechanical_resample_points set."""
    not_converged = StageResult("accepted", outputs={
        "bm_gate_verdict": "BM_REPORTABLE",
        "bm_convergence_verdict": "BM_LADDER_NOT_CONVERGED",
        "bm_convergence_confidence": "high",
        "murnaghan_result": {"pressures_atm": [1, 1000, 2500, 5000, 10000, 15000],
                             "B0_GPa": 1.65},
    })
    converged = StageResult("accepted", outputs={
        "bm_gate_verdict": "BM_REPORTABLE",
        "bm_convergence_verdict": "BM_LADDER_CONVERGED",
        "method": "murnaghan",
    })
    fake = FakeExecutor({"mechanical": [not_converged, converged]})
    engine = WorkflowEngine(tmp_path, plan(), fake)

    result = engine.run()

    assert result["status"] == "accepted"
    mech_calls = [call for call in fake.calls if call[0] == "mechanical"]
    assert len(mech_calls) == 2
    assert mech_calls[-1][1]["parameters"]["mechanical_resample_points"] == [30000]
    assert engine.state["remedy_counters"]["by_id"]["murnaghan_ladder_extend"] == 1


def test_low_confidence_bm_ladder_finding_escalates_before_plan_mutation(tmp_path):
    """Mirrors test_low_confidence_escalates_before_plan_mutation: a
    BM_LADDER_NOT_CONVERGED finding whose only reason is loo_unstable/b0_prime_out_of_band
    (confidence=low) must never auto-widen the ladder -- it escalates instead."""
    finding = Finding("BM_LADDER_NOT_CONVERGED", "mechanical", confidence="low")
    fake = FakeExecutor({"mechanical": [StageResult("remedy_required", (finding,))]})
    engine = WorkflowEngine(tmp_path, plan(), fake)

    result = engine.run()

    assert result["status"] == "escalation_required"
    assert "mechanical_resample_points" not in engine.state["effective_parameters"]
    assert engine.state["remedy_counters"]["total"] == 0


# ── One rate, two branches ───────────────────────────────────────────────────────────────

def test_lowering_the_tg_rate_invalidates_the_cooldown_as_well_as_the_staircase(tmp_path):
    """The Tg staircase and the cool_block descent run at the SAME rate, by construction
    (stage_params.rate_matched_cool_block_hold_steps) -- a run's density and its Tg have to
    describe one glass. But cooling and thermal both descend from the melt hold INDEPENDENTLY,
    so invalidate_from("thermal") never reaches cooling: mapped to "thermal" alone,
    tg_rate_K_per_ns re-ran the staircase at the new rate while the already-accepted cooldown
    stayed at the old one. Lowering the rate is the only lever left for a Tg fit that will not
    resolve, so this is the path a recovery actually takes.
    """
    engine = WorkflowEngine(tmp_path, plan(tg_rate_K_per_ns=100), FakeExecutor())
    assert engine.run()["status"] == "accepted"

    resumed = WorkflowEngine(tmp_path, plan(tg_rate_K_per_ns=40), FakeExecutor())

    for stage in ("cooling", "thermal"):
        assert resumed.state["stages"][stage]["status"] == "stale", (
            f"{stage} still accepted at the old rate")
    # ...and the melt hold it descends from is untouched: the rate does not move the melt.
    assert resumed.state["stages"]["equilibration"]["status"] == "accepted"


def test_a_thermal_only_knob_leaves_the_cooldown_accepted(tmp_path):
    """The counterpart: widening the temperature step is thermal's business alone."""
    engine = WorkflowEngine(tmp_path, plan(tg_rate_K_per_ns=100, tg_t_step_K=20), FakeExecutor())
    assert engine.run()["status"] == "accepted"

    resumed = WorkflowEngine(tmp_path, plan(tg_rate_K_per_ns=100, tg_t_step_K=10), FakeExecutor())
    assert resumed.state["stages"]["thermal"]["status"] == "stale"
    assert resumed.state["stages"]["cooling"]["status"] == "accepted"


# ─── EXTEND sizing: the tau*20 path is gone, and the right stage gets extended ──

def _extend_finding(**details):
    return Finding("EXTEND", "equilibration", details=details)


def test_a_melt_extend_is_sized_from_the_measured_displacement_not_the_advisory_tau():
    """The 17,453 ns regression, locked.

    On 2026-09-09 PLLA_1's EXTEND carried relaxation_time_ns=872.66 -- a KWW tau fitted to an
    11.5%-decayed C(t), an extrapolation 176x beyond its own trajectory. `tau * target_n_eff`
    turned that into a request for 17.45 MICROseconds of continuation, which validate_overrides
    rejected as out of range, costing an agent escalation and a full ten-stage replay.
    C(t) is advisory now and must never size anything.
    """
    import workflow_engine
    finding = _extend_finding(relaxation_time_ns=872.6603,
                              failing_binding_gates=["chain_displacement"])
    with pytest.raises(ValueError, match="extension_ns"):
        workflow_engine._continue_npt({}, finding, 1)


def test_a_declining_remedy_records_why(tmp_path):
    """Declining must leave a named cause in recovery_log.jsonl. Every exception used to return
    False silently, so the agent inherited the escalation with no trace of what the
    deterministic remedy had already ruled out."""
    import workflow_engine

    finding = Finding("EXTEND", "equilibration",
                      details={"relaxation_time_ns": 872.66,
                               "failing_binding_gates": ["chain_displacement"]})
    fake = FakeExecutor({"equilibration": [StageResult("remedy_required", (finding,))]})
    engine = WorkflowEngine(tmp_path, plan(), fake)
    roomy = SimpleNamespace(total=int(1e13), used=0, free=int(9e12))
    with patch.object(workflow_engine.shutil, "disk_usage", return_value=roomy), \
         patch.object(__import__("hardware_runtime"), "free_gpus", return_value=[0, 1, 2, 3]):
        engine.run()

    events = [json.loads(l) for l in (tmp_path / "recovery_log.jsonl").read_text().splitlines()]
    rejected = [e for e in events if e["event"] == "auto_remedy_rejected"]
    assert rejected, "a remedy that raised must log why it declined"
    assert "extension_ns" in rejected[-1]["reason"]


def test_a_displacement_failure_extends_the_nvt_window_it_was_measured_on():
    """MSD and C(t) are computed on nvt_melt_hold.dump -- the FIXED-VOLUME window, because a
    barostatted trajectory affine-scales coordinates every step and would contaminate
    cumulative CoM displacement. Extending npt_melt_hold for a displacement failure lengthens a
    trajectory the gate never reads, so MSD/Rg^2 comes back unchanged and the gate re-fails
    identically. That was the behaviour until 2026-09-09."""
    import workflow_engine
    revised = workflow_engine._continue_npt(
        {}, _extend_finding(extension_ns=12.0,
                            failing_binding_gates=["chain_displacement"]), 1)
    assert revised["equilibration_extend_base_stage"] == "nvt_melt_hold"
    assert revised["equilibration_extend_ensemble"] == "nvt"
    assert revised["npt_continuation_ns"] == 12.0


def test_a_thermo_failure_still_extends_the_npt_cell_its_gates_read():
    """density/energy drift and SEM are read from npt_melt_hold's own log, so those keep the
    NPT base stage -- the routing is by which trajectory failed, not a blanket switch."""
    import workflow_engine
    revised = workflow_engine._continue_npt(
        {}, Finding("EQUIL_DRIFT", "equilibration",
                    details={"extension_ns": 3.0, "failing_binding_gates": ["density_drift"]}), 1)
    assert revised["equilibration_extend_base_stage"] == "npt_melt_hold"
    assert revised["equilibration_extend_ensemble"] == "npt"


def test_a_thermo_extend_still_sizes_when_displacement_passed():
    """The near-miss of 2026-09-09: aPS_1's melt failed density_drift + msid_gaussian with
    chain_displacement PASSING at 2.793x Rg^2. Scoping the "cannot size, decline" branch to the
    whole EXTEND code (rather than to a displacement failure) made the remedy stand down on a
    problem that has a perfectly good default, and sent the run to its LAST agent escalation.

    A thermo gate is a sampling-convergence failure: it extends the NPT cell whose log those
    gates are read from, and it takes the size the GATE measured (`extension_ns`, from
    _thermo_extension_ns) rather than declining.
    """
    import workflow_engine
    finding = Finding("EXTEND", "equilibration",
                      details={"failing_binding_gates": ["density_drift", "msid_gaussian"],
                               "extension_ns": 2.0,
                               # a huge CHAIN C(t) integral must not leak into a THERMO sizing
                               "relaxation_time_ns": 872.6603})
    revised = workflow_engine._continue_npt({}, finding, 1)
    assert revised["npt_continuation_ns"] == 2.0
    assert revised["equilibration_extend_base_stage"] == "npt_melt_hold"
    assert revised["equilibration_extend_ensemble"] == "npt"


def test_an_unsized_continuation_declines_instead_of_inventing_a_length():
    """What stood here read as a formula -- `tau_ns * target_n_eff` -- but nothing in the repo
    has ever written tau_ns, n_eff or target_n_eff into a finding, so every path through it
    returned exactly 0.5 * 20 = 10.0 ns regardless of run, stage or gate.

    On 2026-09-09 that gave aPS_1 a 10 ns extension against a 2 ns melt hold, and would have
    given any cooling EXTEND 10 ns against a 0.5 ns npt_final. Both callers now size from
    measurement, so an unsized finding is a real gap and must be declined with a named cause --
    which routes it to the recovery agent -- not papered over with a constant.
    """
    import workflow_engine
    finding = Finding("EXTEND", "equilibration",
                      details={"failing_binding_gates": ["density_drift"]})
    with pytest.raises(ValueError, match="cannot size a continuation"):
        workflow_engine._continue_npt({}, finding, 1)


def test_no_default_extension_length_survives_anywhere_in_continue_npt():
    """Guard against the constant creeping back. 0.5 and 20 are the two halves of the retired
    default; neither may appear as a literal in _continue_npt's body."""
    import inspect, workflow_engine
    src = inspect.getsource(workflow_engine._continue_npt)
    body = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))
    for literal in ("or 0.5", "or 20", "tau * target"):
        assert literal not in body, f"retired sizing default reappeared: {literal!r}"


def test_the_chain_relaxation_time_can_never_size_any_extension():
    """relaxation_time_ns is the end-to-end C(t) integral. It sized the 17,453 ns request, and
    C(t) is advisory now -- no path may consult it, in either branch."""
    import inspect
    import workflow_engine
    src = inspect.getsource(workflow_engine._continue_npt)
    body = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))
    assert "relaxation_time_ns" not in body, "the chain C(t) tau is back in the sizing path"


def test_a_plan_write_outside_decided_params_invalidates_nothing(tmp_path):
    """The guarantee the backbone_types fix rests on, asserted rather than assumed.

    _reconcile_plan compares plan_hash over the WHOLE plan, so any write to run_plan.json moves
    it -- but it computes `changed` from decided_params alone. A derived value persisted
    elsewhere must therefore update plan_hash and invalidate NOTHING. If that ever stops holding,
    the gate's backbone_types write-back silently starts replaying ten stages again.
    """
    import workflow_engine
    fake = FakeExecutor({})
    doc = plan()
    engine = WorkflowEngine(tmp_path, doc, fake)
    engine.state["stages"]["build"]["status"] = "accepted"
    engine._save()
    before_hash = engine.state["plan_hash"]

    doc2 = json.loads(json.dumps(doc))
    doc2["derived_inputs"] = {"backbone_types": {"value": [1, 2, 3]}}
    engine2 = WorkflowEngine(tmp_path, doc2, fake)

    assert engine2.state["plan_hash"] != before_hash, "the plan really did change"
    assert engine2.state["stages"]["build"]["status"] == "accepted"
    assert not engine2.state["stages"]["build"].get("stale_reason")
    assert not engine2.state["stages"]["equilibration"].get("stale_reason")


def test_the_same_write_inside_decided_params_does_invalidate(tmp_path):
    """The other half: a genuine parameter change must still invalidate. This is why the fix
    moves the DERIVED value out rather than exempting the key -- a caller-SUPPLIED
    backbone_types changes which atoms the assessment treats as backbone, and must re-gate."""
    import workflow_engine
    fake = FakeExecutor({})
    doc = plan()
    engine = WorkflowEngine(tmp_path, doc, fake)
    engine.state["stages"]["build"]["status"] = "accepted"
    engine._save()

    doc2 = json.loads(json.dumps(doc))
    doc2["decided_params"]["backbone_types"] = [1, 2, 3]
    engine2 = WorkflowEngine(tmp_path, doc2, fake)
    assert engine2.state["stages"]["equilibration"].get("stale_reason") == "executable plan changed"


# ─── a verdict already on disk is applied, not re-earned ───────────────────────

def _die_after_verdict(tmp_path, finding):
    """First engine: executor returns remedy_required, then the process 'dies' before the
    remedy is applied -- reproduced by making _apply_remedy a no-op for that one run."""
    fake = FakeExecutor({"equilibration": [StageResult("remedy_required", (finding,))]})
    engine = WorkflowEngine(tmp_path, plan(), fake)
    with patch.object(WorkflowEngine, "_apply_remedy", return_value=False), \
         patch.object(WorkflowEngine, "_escalate", return_value="failed"):
        engine.run()
    return fake


def test_a_resumed_run_applies_the_verdict_it_already_earned(tmp_path):
    """The aPS_1 replay, locked. The stage must NOT be executed a second time."""
    import workflow_engine
    finding = Finding("EXTEND", "equilibration",
                      details={"extension_ns": 2.0,
                               "failing_binding_gates": ["density_drift"]})
    first = _die_after_verdict(tmp_path, finding)
    assert len([c for c in first.calls if c[0] == "equilibration"]) == 1

    # A fresh engine on the same run_dir -- i.e. `agent_api.py resume`.
    second = FakeExecutor({"equilibration": [StageResult("accepted", ())]})
    engine = WorkflowEngine(tmp_path, plan(), second)
    roomy = SimpleNamespace(total=int(1e13), used=0, free=int(9e12))
    with patch.object(workflow_engine.shutil, "disk_usage", return_value=roomy), \
         patch.object(__import__("hardware_runtime"), "free_gpus", return_value=[0, 1, 2, 3]):
        engine.run()

    events = [json.loads(l) for l in (tmp_path / "recovery_log.jsonl").read_text().splitlines()]
    assert any(e["event"] == "verdict_resumed" for e in events), \
        "the persisted verdict must be replayed, not re-earned by re-running the stage"
    applied = [e for e in events if e["event"] == "auto_remedy"]
    assert applied and applied[-1]["code"] == "EXTEND"
    # The remedy revised the parameters, so the stage runs ONCE more -- with the extension.
    assert engine.state["effective_parameters"]["npt_continuation_ns"] == 2.0
    assert len([c for c in second.calls if c[0] == "equilibration"]) == 1


def test_a_resumed_verdict_is_served_only_once(tmp_path):
    """Guard against a remedy that revises nothing leaving the input_hash unchanged, so the
    same verdict would be handed back forever."""
    finding = Finding("EXTEND", "equilibration", details={"extension_ns": 2.0})
    _die_after_verdict(tmp_path, finding)
    engine = WorkflowEngine(tmp_path, plan(), FakeExecutor({}))
    h = engine._input_hash("equilibration")
    assert engine._resume_pending_verdict("equilibration", h) is not None
    assert engine._resume_pending_verdict("equilibration", h) is None


def test_a_verdict_from_a_different_protocol_is_not_resumed(tmp_path):
    """A changed parameter means the verdict was about a different protocol -- re-run it."""
    finding = Finding("EXTEND", "equilibration", details={"extension_ns": 2.0})
    _die_after_verdict(tmp_path, finding)
    engine = WorkflowEngine(tmp_path, plan(), FakeExecutor({}))
    assert engine._resume_pending_verdict("equilibration", "a-different-hash") is None


def test_a_process_death_is_not_a_verdict(tmp_path):
    """PROCESS_FAILED lands as `failed`, not `remedy_required`: it routes through
    transient_retry, which re-runs by design. Replaying it would defeat that."""
    fake = FakeExecutor({"equilibration": [StageResult("failed", (
        Finding("PROCESS_FAILED", "equilibration"),))]})
    engine = WorkflowEngine(tmp_path, plan(), fake)
    with patch.object(WorkflowEngine, "_apply_remedy", return_value=False), \
         patch.object(WorkflowEngine, "_escalate", return_value="failed"):
        engine.run()
    engine2 = WorkflowEngine(tmp_path, plan(), FakeExecutor({}))
    assert engine2._resume_pending_verdict(
        "equilibration", engine2._input_hash("equilibration")) is None


def test_a_plan_change_does_not_discard_remedy_applied_parameters(tmp_path):
    """aPS_1 / sPVC_1, 2026-09-09. continue_npt had written npt_continuation_ns=2.0 into
    effective_parameters; the melt gate then wrote backbone_types back into run_plan.json, and
    the next resume's _reconcile_plan replaced effective_parameters wholesale with the plan's
    decided_params. The continuation parameter vanished, so the 'continuation' ran as a fresh
    ten-stage chain -- with recovery_log.jsonl still showing the remedy as applied.
    """
    import workflow_engine
    fake = FakeExecutor({})
    doc = plan()
    engine = WorkflowEngine(tmp_path, doc, fake)
    engine.state["effective_parameters"]["npt_continuation_ns"] = 2.0
    engine.state["effective_parameters"]["equilibration_extend_base_stage"] = "npt_melt_hold"
    engine._save()

    doc2 = json.loads(json.dumps(doc))
    doc2["decided_params"]["cutoff_A"] = 14.0        # any real plan change
    engine2 = WorkflowEngine(tmp_path, doc2, fake)

    assert engine2.state["effective_parameters"]["npt_continuation_ns"] == 2.0
    assert engine2.state["effective_parameters"]["equilibration_extend_base_stage"] == "npt_melt_hold"
    assert engine2.state["effective_parameters"]["cutoff_A"] == 14.0   # the plan still wins


def test_the_plan_still_wins_for_keys_it_defines(tmp_path):
    """Preservation must not let a stale remedy value shadow the plan -- only keys the plan does
    not define survive."""
    import workflow_engine
    fake = FakeExecutor({})
    doc = plan()
    engine = WorkflowEngine(tmp_path, doc, fake)
    engine.state["effective_parameters"]["cutoff_A"] = 99.0
    engine._save()
    doc2 = json.loads(json.dumps(doc))
    doc2["decided_params"]["cutoff_A"] = 14.0
    engine2 = WorkflowEngine(tmp_path, doc2, fake)
    assert engine2.state["effective_parameters"]["cutoff_A"] == 14.0
    assert engine2.state["stages"]["build"].get("stale_reason") == "executable plan changed"


def test_a_remedy_parameter_does_not_invalidate_its_own_stage_forever(tmp_path):
    """sPVC_1, 2026-09-09. The companion bug to
    test_a_plan_change_does_not_discard_remedy_applied_parameters: preservation kept the remedy
    key, but `changed` was computed as effective_parameters vs decided_params, and a remedy key
    exists ONLY in the former -- so it compared unequal on every reconcile, forever.

    The damage is silent until a fresh process constructs an engine. The melt gate's
    derived_inputs write-back moved the plan hash at 11:59 while the engine was mid-run; the
    resume hours later saw the stale hash, recomputed `changed`, found npt_continuation_ns
    "changed", and invalidated an equilibration that had been ACCEPTED for four hours --
    re-submitting a 2 ns melt continuation for a stage that was already done.
    """
    import workflow_engine
    fake = FakeExecutor({})
    doc = plan()
    engine = WorkflowEngine(tmp_path, doc, fake)
    engine.state["stages"]["equilibration"]["status"] = "accepted"
    engine.state["effective_parameters"]["npt_continuation_ns"] = 2.0
    engine._save()

    # The plan itself is UNCHANGED in every decided_param; only an out-of-contract field moves,
    # exactly as the backbone_types derivation does.
    doc2 = json.loads(json.dumps(doc))
    doc2.setdefault("derived_inputs", {})["backbone_types"] = {"value": [1, 2, 3]}
    engine2 = WorkflowEngine(tmp_path, doc2, fake)

    assert engine2.state["stages"]["equilibration"]["status"] == "accepted", (
        "an accepted stage was invalidated by a remedy parameter that no plan edit touched")
    assert engine2.state["stages"]["equilibration"].get("stale_reason") is None
    assert engine2.state["effective_parameters"]["npt_continuation_ns"] == 2.0


def test_a_real_plan_edit_still_invalidates_after_a_remedy_ran(tmp_path):
    """The narrowing must not blind the diff: a genuine decided_params change still invalidates,
    even while a remedy key is being preserved alongside it."""
    import workflow_engine
    fake = FakeExecutor({})
    doc = plan()
    engine = WorkflowEngine(tmp_path, doc, fake)
    engine.state["stages"]["equilibration"]["status"] = "accepted"
    engine.state["effective_parameters"]["npt_continuation_ns"] = 2.0
    engine._save()

    doc2 = json.loads(json.dumps(doc))
    doc2["decided_params"]["cutoff_A"] = 14.0
    engine2 = WorkflowEngine(tmp_path, doc2, fake)

    assert engine2.state["stages"]["equilibration"].get("stale_reason") == (
        "executable plan changed")
    assert engine2.state["effective_parameters"]["npt_continuation_ns"] == 2.0


def test_revise_plan_moves_the_reconcile_baseline_with_the_plan(tmp_path):
    """A revised plan must become the baseline the NEXT reconcile diffs against.

    Otherwise the first plan-hash move after a revise_plan (a derived_inputs write will do it)
    compares the revised decided_params against the pre-revision snapshot and invalidates every
    stage the revision just settled -- the same trap as
    test_a_remedy_parameter_does_not_invalidate_its_own_stage_forever, one level up.
    """
    import workflow_engine
    fake = FakeExecutor({})
    doc = plan()
    engine = WorkflowEngine(tmp_path, doc, fake)
    engine.state["stages"]["equilibration"]["status"] = "accepted"

    revised = json.loads(json.dumps(doc))
    revised["decided_params"]["cutoff_A"] = 14.0
    engine.plan = revised
    engine.state["plan_hash"] = workflow_engine._canonical_hash(revised)
    engine.state["plan_decided_params"] = json.loads(
        json.dumps(revised.get("decided_params") or {}))
    engine._save()

    # Now an out-of-contract write moves the hash again. Nothing in decided_params changed.
    revised2 = json.loads(json.dumps(revised))
    revised2.setdefault("derived_inputs", {})["backbone_types"] = {"value": [1, 2]}
    engine2 = WorkflowEngine(tmp_path, revised2, fake)

    assert engine2.state["stages"]["equilibration"]["status"] == "accepted"
    assert engine2.state["stages"]["equilibration"].get("stale_reason") is None
