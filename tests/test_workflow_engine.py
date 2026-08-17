import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))

from workflow_engine import (  # noqa: E402
    ACTIVE_BLOCKING_CODES,
    Finding,
    RemedyRegistry,
    StageResult,
    WorkflowEngine,
    pressure_point_drop_allowed,
)


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
    assert all((tmp_path / "attempts" / stage / attempt / "manifest.json").is_file()
               for stage, attempt in result["accepted_attempts"].items())


def test_low_confidence_escalates_before_plan_mutation(tmp_path):
    finding = Finding("TG_NOT_REPORTABLE", "thermal", confidence="low")
    fake = FakeExecutor({"thermal": [StageResult("remedy_required", (finding,))]})
    engine = WorkflowEngine(tmp_path, plan(tg_steps_per_t=100), fake)

    result = engine.run()

    assert result["status"] == "escalation_required"
    assert engine.state["effective_parameters"]["tg_steps_per_t"] == 100
    assert engine.state["remedy_counters"]["total"] == 0


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
                     engine.state["stages"]["build"]["accepted_attempt"] / "manifest.json")
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


def test_pressure_point_drop_requires_identifiable_remaining_series():
    assert pressure_point_drop_allowed({-500: "failed", 0: "accepted", 500: "accepted",
                                        1000: "accepted", 2000: "accepted"})
    assert not pressure_point_drop_allowed({0: "accepted", 500: "accepted",
                                            1000: "accepted", 2000: "failed"})
    assert not pressure_point_drop_allowed({-500: "accepted", 0: "accepted",
                                            500: "accepted", 1000: "failed"})
