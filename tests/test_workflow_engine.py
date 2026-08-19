import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))

from workflow_engine import (  # noqa: E402
    ACTIVE_BLOCKING_CODES,
    MAX_AGENT_DECISIONS,
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


def test_melt_stage_deficit_escalates_anneal_cycles_before_melt_hold(tmp_path):
    finding = Finding("MELT_STAGE_DEFICIT", "equilibration")
    fake = FakeExecutor({"equilibration": [
        StageResult("remedy_required", (finding,)),
        StageResult("remedy_required", (finding,)),
    ]})
    engine = WorkflowEngine(tmp_path, plan(eq_annealing_cycles=3), fake)

    result = engine.run()

    assert result["status"] == "accepted"
    equil_calls = [call for call in fake.calls if call[0] == "equilibration"]
    assert len(equil_calls) == 3
    # attempt 1: cheaper lever only -- more thermal-cycling depth, no melt hold yet
    assert equil_calls[1][1]["parameters"]["eq_annealing_cycles"] == 6
    assert "melt_hold_ns" not in equil_calls[1][1]["parameters"]
    # attempt 2: cycles stay escalated, bounded melt hold added as the fallback
    assert equil_calls[2][1]["parameters"]["eq_annealing_cycles"] == 6
    assert equil_calls[2][1]["parameters"]["melt_hold_ns"] == 5.0


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


def test_pressure_point_drop_requires_identifiable_remaining_series():
    assert pressure_point_drop_allowed({-500: "failed", 0: "accepted", 500: "accepted",
                                        1000: "accepted", 2000: "accepted"})
    assert not pressure_point_drop_allowed({0: "accepted", 500: "accepted",
                                            1000: "accepted", 2000: "failed"})
    assert not pressure_point_drop_allowed({-500: "accepted", 0: "accepted",
                                            500: "accepted", 1000: "failed"})
