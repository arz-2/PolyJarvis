import json
import sys
from pathlib import Path

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
