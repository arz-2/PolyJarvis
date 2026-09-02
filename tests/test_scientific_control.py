import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))

import rules_common
import select_system_size as sss  # noqa: E402
import scientific_control  # noqa: E402
from scientific_control import (  # noqa: E402
    DeterministicScriptChain,
    PlanDecision,
    RecoveryDecision,
    ScientificControlPlane,
    ScientificIntent,
    WorkflowIssue,
    WorkflowOutcome,
    JsonSubprocessAgent,
    SubprocessPlanningAgent,
    materialize_plan,
    planning_context,
)


INTENT = ScientificIntent(
    run_name="CONTROL_TEST",
    goal="Compute density and bulk modulus at 300 K",
    smiles="*CC(c1ccccc1)*",
    requested_properties=("density", "bulk_modulus"),
    polymer_class_hint="PSTR",
)


class SpyPlanningAgent:
    def __init__(self):
        self.calls = 0

    def decide(self, intent, context):
        self.calls += 1
        assert "PSTR" in context["available_classes"]
        return PlanDecision(
            polymer_class="PSTR",
            properties=("density", "bulk_modulus"),
            rationale=("The requested state is a glassy polystyrenic workflow at 300 K.",),
            # PS's entanglement floor (Me=16600 g/mol -> DP@Me=160) exceeds PSTR's class
            # default dp_typical=50 for a bulk_modulus request -- raise it to clear D-04's
            # measured floor.
            overrides={"dp_typical": 160},
            decision_evaluations={
                "D-02_charges": {
                    "criteria_evaluated": [
                        "backbone_polarity", "charge_method_cost", "ff_embedded_vs_qm"
                    ],
                },
                "D-03_electrostatics": {
                    "criteria_evaluated": [
                        "backbone_heteroatoms", "max_partial_charge", "computational_cost"
                    ],
                    "evidence": [{
                        "claim": "Long-range electrostatics follow the selected PCFF protocol.",
                        "citation": "class-configured force-field evidence",
                    }],
                    "alternatives": ["short-range Coulomb treatment"],
                },
            },
            dominant_uncertainty="forcefield_transferability",
            confidence="medium",
        )


class SpyRecoveryAgent:
    def __init__(self, decision=None):
        self.calls = 0
        self.decision = decision or RecoveryDecision("retry", "Transient failure; resume state.")

    def diagnose(self, intent, plan, issue):
        self.calls += 1
        assert issue.code == "TENSION_RUN_FAILED"
        return self.decision


class SequenceWorkflow:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def execute(self, plan_path, dry_run=False, attempt=0):
        self.calls += 1
        assert json.loads(plan_path.read_text())["plan_mode"] == "reasoned"
        return self.outcomes.pop(0)


def completed_outcome():
    return WorkflowOutcome(
        status="complete",
        result={"status": "complete", "run_summary": "/tmp/run_summary.json"},
        steps=({"step": "validate_run_plan"}, {"step": "run_campaign"}),
    )


def failed_outcome(attempt=0):
    issue = WorkflowIssue(
        stage="mechanical",
        code="TENSION_RUN_FAILED",
        detail={"failure_pressure_atm": -800},
        attempt=attempt,
    )
    return WorkflowOutcome("issue", {"status": "halted"}, issue)


def test_success_never_triggers_recovery_agent(tmp_path):
    planning = SpyPlanningAgent()
    recovery = SpyRecoveryAgent()
    workflow = SequenceWorkflow([completed_outcome()])

    result = ScientificControlPlane(planning, workflow, recovery, tmp_path).run(INTENT)

    assert result["status"] == "complete"
    assert planning.calls == 1
    assert workflow.calls == 1
    assert recovery.calls == 0
    assert result["recovery_agent_calls"] == 0
    event_names = [event["event"] for event in result["events"]]
    assert event_names == [
        "scientific_agent_called",
        "plan_materialized",
        "deterministic_chain_finished",
    ]


def test_issue_is_the_only_trigger_for_recovery_agent(tmp_path):
    planning = SpyPlanningAgent()
    recovery = SpyRecoveryAgent()
    workflow = SequenceWorkflow([failed_outcome(), completed_outcome()])

    result = ScientificControlPlane(planning, workflow, recovery, tmp_path).run(INTENT)

    assert result["status"] == "complete"
    assert recovery.calls == 1
    assert workflow.calls == 2
    event_names = [event["event"] for event in result["events"]]
    assert event_names.count("issue_detected") == 1
    assert event_names.count("recovery_agent_called") == 1


def test_issue_without_recovery_agent_stops_at_structured_boundary(tmp_path):
    result = ScientificControlPlane(
        SpyPlanningAgent(), SequenceWorkflow([failed_outcome()]), None, tmp_path
    ).run(INTENT)

    assert result["status"] == "needs_recovery_agent"
    assert result["issue"]["code"] == "TENSION_RUN_FAILED"
    assert result["recovery_agent_calls"] == 0


def test_recovery_agent_cannot_modify_paths_or_commands(tmp_path):
    recovery = SpyRecoveryAgent(RecoveryDecision(
        "revise_plan",
        "Attempted unsafe edit",
        {"work_dir": "/tmp/agent-owned"},
    ))
    control = ScientificControlPlane(
        SpyPlanningAgent(), SequenceWorkflow([failed_outcome()]), recovery, tmp_path
    )

    with pytest.raises(ValueError, match="unsupported overrides"):
        control.run(INTENT)


def test_materializer_applies_bounded_scientific_overrides():
    decision = PlanDecision(
        polymer_class="PSTR",
        properties=("density",),
        rationale=("Use a longer NPT production window for the requested precision.",),
        overrides={"stage8_min_steps": 8000000, "nchain": 12},
        decision_evaluations={
            "D-02_charges": {
                "criteria_evaluated": [
                    "backbone_polarity", "charge_method_cost", "ff_embedded_vs_qm"
                ],
            },
            "D-03_electrostatics": {
                "criteria_evaluated": [
                    "backbone_heteroatoms", "max_partial_charge", "computational_cost"
                ],
                "evidence": [{"claim": "PCFF electrostatics", "citation": "class evidence"}],
                "alternatives": ["short-range Coulomb treatment"],
            },
        },
        dominant_uncertainty="sampling",
        confidence="high",
    )

    plan = materialize_plan(INTENT, decision)

    assert plan["plan_mode"] == "reasoned"
    assert plan["decided_params"]["stage8_min_steps"] == 8000000
    assert plan["decided_params"]["nchain"] == 12
    assert plan["uncertainties"][0] == {
        "name": "sampling", "dominant": True, "reduction_probe": "none"
    }
    # Everything after the dominant entry is a solve_system_size advisory, and every one of
    # them must be non-dominant -- they disclose, they never take over the plan's headline
    # uncertainty.
    assert all(u.get("dominant") is False for u in plan["uncertainties"][1:])
    # And they must quote the FINAL decided_params, not the pre-override derivation: this plan
    # overrides nchain to 12, so an advisory about nchain has to say 12. It said 10 (the derived
    # value) until materialize_plan started re-running solve_system_size against the final
    # parameters -- a plan that contradicts its own decided_params is worse than one that
    # discloses nothing.
    nchain_advisories = [u for u in plan["uncertainties"] if "nchain" in u["name"]]
    assert nchain_advisories, "expected an nchain advisory: nchain=12 is below the PCFF advisory minimum 20"
    assert all("nchain=12" in u["detail"] for u in nchain_advisories)
    assert "decision_sha256" in plan["provenance"]


def test_materializer_rejects_unknown_polymer_class():
    decision = PlanDecision(
        polymer_class="NOT_CONFIGURED",
        properties=("density",),
        rationale=("Attempt an unsupported class.",),
    )

    with pytest.raises(ValueError, match="unknown polymer class"):
        materialize_plan(INTENT, decision)


def test_real_script_chain_dry_run(tmp_path):
    decision = SpyPlanningAgent().decide(INTENT, {"available_classes": {"PSTR": {}}})
    plan = materialize_plan(INTENT, decision)
    plan_path = tmp_path / "run_plan.json"
    plan_path.write_text(json.dumps(plan))

    outcome = DeterministicScriptChain(python=sys.executable).execute(plan_path, dry_run=True)

    assert outcome.status == "complete", outcome.issue
    assert [step["step"] for step in outcome.steps] == [
        "validate_run_plan", "resolve_stage_params"
    ]
    assert "build" in outcome.result
    assert "murnaghan" in outcome.result


def test_subprocess_scientific_agent_uses_json_contract(tmp_path):
    script = tmp_path / "planning_agent.py"
    script.write_text(
        "import json, sys\n"
        "payload = json.load(sys.stdin)\n"
        "assert payload['task'] == 'plan_polymer_simulation'\n"
        "assert 'decision_framework' in payload['context']\n"
        "json.dump({"
        "'polymer_class':'PSTR',"
        "'properties':['density'],"
        "'rationale':['Use the configured PSTR density protocol.'],"
        "'confidence':'medium'"
        "}, sys.stdout)\n"
    )
    agent = SubprocessPlanningAgent(JsonSubprocessAgent([sys.executable, str(script)]))

    decision = agent.decide(INTENT, {
        "available_classes": {"PSTR": {}},
        "decision_framework": {"D-01_ff": {}},
    })

    assert decision.polymer_class == "PSTR"
    assert decision.properties == ("density",)
    assert decision.rationale == ("Use the configured PSTR density protocol.",)


def test_real_chain_invokes_in_process_workflow_once(tmp_path, monkeypatch):
    decision = SpyPlanningAgent().decide(INTENT, {"available_classes": {"PSTR": {}}})
    plan = materialize_plan(INTENT, decision)
    plan_path = tmp_path / "run_plan.json"
    plan_path.write_text(json.dumps(plan))
    commands = []
    engine_calls = []

    def fake_run(command, **kwargs):
        commands.append(command)
        if "validate_run_plan.py" in command[1]:
            stdout = json.dumps({"findings": [], "count": 0})
        else:
            raise AssertionError("campaign stages must not launch subprocesses")
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    monkeypatch.setattr("scientific_control.subprocess.run", fake_run)
    monkeypatch.setattr("run_campaign.run_campaign_workflow", lambda *args, **kwargs: (
        engine_calls.append((args, kwargs)) or {"status": "accepted", "state_path": ""}
    ))

    outcome = DeterministicScriptChain(python=sys.executable).execute(plan_path)

    assert outcome.status == "complete"
    assert [step["step"] for step in outcome.steps] == ["validate_run_plan", "workflow_engine"]
    assert len(commands) == 1
    assert len(engine_calls) == 1


def test_real_chain_normalizes_engine_failure_context(tmp_path, monkeypatch):
    decision = SpyPlanningAgent().decide(INTENT, {"available_classes": {"PSTR": {}}})
    plan = materialize_plan(INTENT, decision)
    plan_path = tmp_path / "run_plan.json"
    plan_path.write_text(json.dumps(plan))

    def fake_run(command, **kwargs):
        if "validate_run_plan.py" in command[1]:
            return subprocess.CompletedProcess(
                command, 0, stdout=json.dumps({"findings": [], "count": 0}), stderr=""
            )
        raise AssertionError("campaign stages must not launch subprocesses")

    monkeypatch.setattr("scientific_control.subprocess.run", fake_run)
    engine_result = {
        "status": "escalation_required", "stage": "equilibration",
        "finding": {"code": "BACKBONE_TYPES_UNRESOLVED",
                    "details": {"atom_type_names": {"1": "c4"}}},
        "state_path": str(tmp_path / "workflow_state.json"),
    }
    monkeypatch.setattr("run_campaign.run_campaign_workflow",
                        lambda *args, **kwargs: engine_result)

    outcome = DeterministicScriptChain(python=sys.executable).execute(plan_path)

    assert outcome.status == "issue"
    assert outcome.issue.code == "BACKBONE_TYPES_UNRESOLVED"
    assert outcome.issue.detail["result"] == engine_result


def test_recovery_agent_is_never_called_more_than_twice(tmp_path):
    recovery = SpyRecoveryAgent()
    workflow = SequenceWorkflow([
        failed_outcome(0),
        failed_outcome(1),
        failed_outcome(2),
    ])

    result = ScientificControlPlane(SpyPlanningAgent(), workflow, recovery, tmp_path).run(INTENT)

    assert result["status"] == "unresolved"
    assert recovery.calls == 2
    assert workflow.calls == 3
    assert result["recovery_agent_calls"] == 2


# ─── planning_context() canonicalizes intent.smiles before the cache lookup ───────────────

def test_planning_context_looks_up_cache_by_canonical_smiles(tmp_path, monkeypatch):
    """A cache entry keyed by the ISOMERIC-CANONICAL form of a SMILES must still be found even
    when intent.smiles is a differently-formatted-but-equivalent string -- the pre-fix code
    looked up characterization_cache.get(intent.smiles) with no canonicalization at all."""
    import shutil
    (tmp_path / "orchestration").mkdir()
    shutil.copy(REPO_ROOT / "orchestration" / "decision_policy.json",
               tmp_path / "orchestration" / "decision_policy.json")
    (tmp_path / "guides").mkdir()
    canonical = "*CC(c1ccccc1)*"  # deliberately distinct from INTENT.smiles's raw string below
    cache_entry = {"polymer_class": "PSTR", "protocol_validated": True}
    (tmp_path / "guides" / "system_characterization_cache.json").write_text(
        json.dumps({canonical: cache_entry}))

    monkeypatch.setattr(scientific_control, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(rules_common, "canonicalize", lambda smi, *a, **k: canonical)

    raw_intent = ScientificIntent(
        run_name="CANON_TEST", goal="test", smiles="not-yet-canonical-form",
        requested_properties=("density",), polymer_class_hint="PSTR",
    )
    context = planning_context(raw_intent)
    assert context["exact_smiles_characterization"] == cache_entry


# --- D-04 system size: materialize_plan() auto-fills solve_system_size()'s recommendation --

PHYC_INTENT = ScientificIntent(
    run_name="D04_AUTOFILL_TEST", goal="test", smiles="*CC*",
    requested_properties=("tg",), polymer_class_hint="PHYC",
)


def test_materializer_auto_fills_the_floor_clearing_dp_when_unset(monkeypatch):
    """PHYC's class default dp_typical is well above its Fox-Flory floor (20) -- the agent
    left dp_typical unset, so materialize_plan() should fill in the floor-clearing minimum
    via solve_system_size() rather than the bloated class default.

    UPDATED 2026-09-02: the floor is now Wang 2021's system-mass criterion derived from the
    run's own repeat unit, not the retired Fox-Flory DP constants. PE's 28.1 g/mol repeat needs
    DP 179 to reach 50 kg/mol across 10 chains -- so 179 IS the floor here, not a rigidity
    artifact to be neutralized. The old docstring called it out as something that would "break
    this test's own assertion"; under the mass floor it is the assertion.

    The rigidity/Kuhn stub stays: that recommendation is a separate, additive source tested in
    test_select_system_size.py, and this test is about the floor auto-fill."""
    monkeypatch.setattr(sss, "_backbone_rigidity", lambda smiles: None)
    decision = PlanDecision(
        polymer_class="PHYC", properties=("tg",),
        rationale=("Just need Tg.",), dominant_uncertainty="none", confidence="high",
    )
    plan = materialize_plan(PHYC_INTENT, decision)
    assert plan["decided_params"]["dp_typical"] == 179
    d04 = next(d for d in plan["decisions"] if d["id"] == "D-04_system_size")
    assert d04["choice"] == "DP=179, nchain=10"
    assert any("floor" in e.get("claim", "") for e in d04["evidence"])
    assert any("D-04_system_size auto-filled" in a for a in plan["assumptions"])


def test_materializer_explicit_override_wins_over_the_auto_fill():
    decision = PlanDecision(
        polymer_class="PHYC", properties=("tg",),
        rationale=("Pin a specific DP for a reason.",),
        overrides={"dp_typical": 40}, dominant_uncertainty="none", confidence="high",
    )
    plan = materialize_plan(PHYC_INTENT, decision)
    assert plan["decided_params"]["dp_typical"] == 40  # the agent's pin, not the derived floor
    # nchain is still auto-filled (it is derived now, and the agent pinned only dp_typical), so
    # an auto-fill assumption legitimately fires -- it must just not claim dp_typical.
    autofill = [a for a in plan["assumptions"] if "D-04_system_size auto-filled" in a]
    assert not any("dp_typical" in a for a in autofill), autofill


def test_deleting_confidence_does_not_skip_the_gate():
    """confidence is the ONLY forcing function since 2026-09-02: make_deterministic_plan.py's
    `decision` subcommand now writes rationale itself, so the old `rationale == []` half of the
    block never fires on a real file. from_dict used to default a missing key to "medium",
    which meant deleting it sailed through validation."""
    base = {"polymer_class": "PHYC", "properties": ["tg"], "rationale": ["r"],
            "dominant_uncertainty": "none"}
    for label, value in (("absent", None), ("empty", ""), ("unreviewed", "unreviewed")):
        d = dict(base)
        if value is not None:
            d["confidence"] = value
        with pytest.raises(ValueError, match="confidence must be one of"):
            scientific_control._validate_decision(PlanDecision.from_dict(d))

    ok = dict(base, confidence="medium")
    scientific_control._validate_decision(PlanDecision.from_dict(ok))  # must not raise


def test_materializer_attaches_a_populated_cost_estimate():
    """Mechanizes decision_policy.json's gpu_budget/computational_cost criteria -- every
    materialized reasoned plan should carry a real cost_model.plan_cost_estimate() payload,
    not just name the criterion without a number behind it."""
    decision = PlanDecision(
        polymer_class="PHYC", properties=("tg",),
        rationale=("Just need Tg.",), dominant_uncertainty="none", confidence="high",
    )
    plan = materialize_plan(PHYC_INTENT, decision)
    assert "cost_estimate" in plan
    assert "error" not in plan["cost_estimate"]
    assert plan["cost_estimate"]["total_gpu_hours"] is not None
    assert "tg" in plan["cost_estimate"]["stages"]


def test_materializer_cost_estimate_failure_degrades_to_error_payload_not_a_raise(monkeypatch):
    """cost estimation is advisory -- an unresolvable estimate must never block plan
    materialization."""
    monkeypatch.setattr(scientific_control.cost_model, "plan_cost_estimate",
                        lambda plan, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    decision = PlanDecision(
        polymer_class="PHYC", properties=("tg",),
        rationale=("Just need Tg.",), dominant_uncertainty="none", confidence="high",
    )
    plan = materialize_plan(PHYC_INTENT, decision)
    assert "boom" in plan["cost_estimate"]["error"]


def test_materializer_flags_tg_ladder_cost_unoptimized_when_tg_is_planned():
    """D-06: no accuracy-vs-cooling-rate curve exists anywhere in this codebase (only an
    aggregate fast-cooling bias is documented, not a per-rate slope), so the rate ladder stays
    floor-only rather than fabricating an optimizer. Surface that gap explicitly rather than
    silently implying the ladder is cost-optimal."""
    decision = PlanDecision(
        polymer_class="PHYC", properties=("tg",),
        rationale=("Just need Tg.",), dominant_uncertainty="none", confidence="high",
    )
    plan = materialize_plan(PHYC_INTENT, decision)
    names = {u["name"] for u in plan["uncertainties"]}
    assert "tg_ladder_cost_unoptimized" in names


def test_materializer_omits_tg_ladder_flag_when_tg_is_not_planned():
    intent = ScientificIntent(
        run_name="D06_NO_TG_TEST", goal="test", smiles="*CC*",
        requested_properties=("bulk_modulus",), polymer_class_hint="PHYC",
    )
    decision = PlanDecision(
        polymer_class="PHYC", properties=("bulk_modulus",),
        rationale=("Just need K.",), dominant_uncertainty="none", confidence="high",
    )
    plan = materialize_plan(intent, decision)
    names = {u["name"] for u in plan["uncertainties"]}
    assert "tg_ladder_cost_unoptimized" not in names


def test_apply_recovery_refreshes_the_stale_cost_estimate():
    """A recovery dp_typical/nchain bump changes the plan's actual cost -- cost_estimate
    must not sit stale next to the post-recovery decided_params (same failure mode as the
    'decided_params can be decorative' class of bug: a field the code carries but a later
    step forgets to keep in sync)."""
    decision = PlanDecision(
        polymer_class="PHYC", properties=("tg",),
        rationale=("Just need Tg.",), dominant_uncertainty="none", confidence="high",
    )
    plan = materialize_plan(PHYC_INTENT, decision)
    before = plan["cost_estimate"]["total_gpu_hours"]

    revised = scientific_control.apply_recovery(
        plan, RecoveryDecision("revise_plan", "Bump nchain for a finite-size rebuild.",
                              modifications={"nchain": 200}))
    assert "cost_estimate" in revised
    assert "error" not in revised["cost_estimate"]
    assert revised["cost_estimate"]["total_gpu_hours"] != before


def test_planning_context_falls_back_to_raw_smiles_on_canonicalization_failure(tmp_path, monkeypatch):
    import shutil
    (tmp_path / "orchestration").mkdir()
    shutil.copy(REPO_ROOT / "orchestration" / "decision_policy.json",
               tmp_path / "orchestration" / "decision_policy.json")
    (tmp_path / "guides").mkdir()
    raw_smiles = "*CC*"
    cache_entry = {"polymer_class": "PHYC", "protocol_validated": True}
    (tmp_path / "guides" / "system_characterization_cache.json").write_text(
        json.dumps({raw_smiles: cache_entry}))

    monkeypatch.setattr(scientific_control, "REPO_ROOT", tmp_path)

    def _boom(smi, *a, **k):
        raise RuntimeError("RDKit unavailable")
    monkeypatch.setattr(rules_common, "canonicalize", _boom)

    raw_intent = ScientificIntent(
        run_name="CANON_TEST2", goal="test", smiles=raw_smiles,
        requested_properties=("density",), polymer_class_hint="PHYC",
    )
    context = planning_context(raw_intent)
    assert context["exact_smiles_characterization"] == cache_entry


# --- D-04 system size: the plan DISCLOSES solve_system_size()'s advisories ----------------

PEEK_SMILES = "*Oc1ccc(C(=O)c2ccc(Oc3ccc(*)cc3)cc2)cc1"


def _tg_plan(polymer_class: str, smiles: str, run_name: str) -> dict:
    intent = ScientificIntent(run_name=run_name, goal="test", smiles=smiles,
                              requested_properties=("tg",), polymer_class_hint=polymer_class)
    decision = PlanDecision(polymer_class=polymer_class, properties=("tg",),
                            rationale=("test",), dominant_uncertainty="sampling",
                            confidence="high")
    return materialize_plan(intent, decision)


def test_stiff_backbone_chain_length_bias_reaches_the_plan():
    """PEEK's aromatic rings are IN the backbone path, so solve_system_size classifies it
    stiff and raises RIGID_BACKBONE_CHAIN_LENGTH_BIAS.

    That advisory was computed and then dropped until 2026-09-02: materialize_plan read only
    recommended_params/recommendation_reasons off the solve, so the uncertainty list it built
    never saw it. The system-size design demoted rigidity from GATING the DP to REPORTING the
    residual bias ("Reported, not gated" -- select_system_size._rigid_backbone_uncertainty),
    which only holds up if the report actually lands somewhere a reader sees. This is that
    wiring: a heavy aromatic repeat unit clears the 50k g/mol system-mass floor at a very
    short DP, and nothing else in the plan says so."""
    plan = _tg_plan("PKTN", PEEK_SMILES, "RIGIDITY_DISCLOSURE_TEST")
    bias = [u for u in plan["uncertainties"] if u["name"] == "RIGID_BACKBONE_CHAIN_LENGTH_BIAS"]
    assert len(bias) == 1, [u["name"] for u in plan["uncertainties"]]
    assert bias[0]["class"] == "stiff"
    assert bias[0]["dominant"] is False, "advisory only -- it must never displace the headline"
    assert "UNQUANTIFIED" in bias[0]["detail"]


def test_flexible_backbone_carries_no_chain_length_bias_advisory():
    """The counterpart: PE is flexible, so there is no rigid-backbone bias to disclose. A
    disclosure that fires on every plan tells a reader nothing."""
    plan = _tg_plan("PHYC", "*CC*", "RIGIDITY_FLEXIBLE_TEST")
    names = {u["name"] for u in plan["uncertainties"]}
    assert "RIGID_BACKBONE_CHAIN_LENGTH_BIAS" not in names


def test_plan_size_advisories_never_displace_the_dominant_uncertainty():
    """Every advisory folded in from solve_system_size is non-dominant, and the planner's own
    dominant uncertainty stays first -- validate_run_plan.py's _uncertainty_findings requires
    exactly one named dominant entry, so a plumbing mistake here is a structural finding."""
    plan = _tg_plan("PKTN", PEEK_SMILES, "RIGIDITY_DOMINANCE_TEST")
    assert plan["uncertainties"][0] == {"name": "sampling", "dominant": True,
                                        "reduction_probe": "none"}
    assert sum(1 for u in plan["uncertainties"] if u.get("dominant")) == 1
