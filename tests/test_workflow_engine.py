import json
import sys
from pathlib import Path


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
    fake = FakeExecutor({"thermal": [
        StageResult("accepted", outputs={"Tg_K": 350.0, "tg_gate_verdict": "TG_REVIEW"}),
        StageResult("accepted", outputs={"Tg_K": 351.0, "tg_gate_verdict": "TG_REVIEW"}),
    ]})
    result = WorkflowEngine(tmp_path, plan(tg_t_step_K=20), fake).run()

    assert result["status"] == "escalation_required"
    thermal_calls = [call for call in fake.calls if call[0] == "thermal"]
    assert len(thermal_calls) == 2
    assert thermal_calls[-1][1]["parameters"]["tg_t_step_K"] == 10


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
        "build", "equilibration", "thermal", "mechanical", "summary"
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
    recovery = RegisteredRemedyRecovery("slower_cooling")
    engine = WorkflowEngine(tmp_path, plan(), fake, recovery_agent=recovery)

    result = engine.run()

    assert result["status"] == "escalation_required"
    assert engine.state["remedy_counters"]["total"] == 0


def test_route_local_cap_exhaustion_escalates_after_automatic_retries(tmp_path):
    """slower_cooling's local_cap is 2 -- a third UNDER_ANNEALED_COOLING finding on the same
    route must escalate rather than apply a third automatic doubling."""
    finding = Finding("UNDER_ANNEALED_COOLING", "equilibration")
    fake = FakeExecutor({"equilibration": [StageResult("remedy_required", (finding,))] * 3})
    engine = WorkflowEngine(tmp_path, plan(cool_block_hold_steps=1000), fake)

    result = engine.run()

    assert result["status"] == "escalation_required"
    assert engine.state["remedy_counters"]["by_route"]["slower_cooling:equilibration"] == 2
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
    finding = Finding("UNDER_ANNEALED_COOLING", "equilibration")
    fake = FakeExecutor({"equilibration": [StageResult("remedy_required", (finding,))]})
    engine = WorkflowEngine(tmp_path, plan(cool_block_hold_steps=1000), fake)

    assert engine.run()["status"] == "accepted"

    events = _read_recovery_log(tmp_path)
    assert [e["event"] for e in events] == ["auto_remedy"]
    assert events[0]["remedy_id"] == "slower_cooling"
    assert events[0]["code"] == "UNDER_ANNEALED_COOLING"
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
