"""Three bugs a full path-trace of the graph found, and their regressions.

Each was invisible to the happy path and to every test that existed, because each only
appears on a path taken by a SECOND invocation or by a failing dependency:

  1. resuming into `adjudicate` discarded the critique it resumed FOR
  2. an adjudication call that failed left the plan in a state materialize rejects
  3. one stray line on stdout would report a successful campaign as failed
"""
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "langgraph"))
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))

import nodes  # noqa: E402
from headless_claude import HeadlessError  # noqa: E402


@pytest.fixture
def run(tmp_path):
    raw = tmp_path / "data" / "R" / "raw"
    raw.mkdir(parents=True)
    return tmp_path, raw


def _state(root, **over):
    base = {"run_name": "R", "smiles": "*CC(*)O", "goal": "g", "properties": ["density"],
            "repo_root": str(root), "events": []}
    base.update(over)
    return base


# --- 1. resume must not discard artifacts it already paid for ----------------
def test_resuming_into_adjudicate_carries_the_grounding_it_resumed_for(run):
    """entry_resolve routes here BECAUSE literature_grounding.json exists. Without passing
    the path on, the adjudicator was told "(none -- the critic returned no usable result)"
    while the file sat on disk, and would adjudicate blind -- throwing away a critique that
    cost real money and minutes, and reaching a worse decision than a fresh run would."""
    root, raw = run
    (raw / "run_plan.json").write_text(json.dumps({"confidence": "unreviewed",
                                                   "polymer_class": "PVNL"}))
    (raw / "literature_grounding.json").write_text(
        json.dumps({"critique": {"D-01_ff": {"verdict": "agrees"}}}))

    out = nodes.entry_resolve(_state(root))
    assert out["entry_node"] == "adjudicate"
    assert out["grounding_path"].endswith("literature_grounding.json")
    assert out["critic_verdict"] == "agrees"


def test_resuming_restores_the_chemistry_findings_for_the_adjudicator(run):
    """The pendant-group and melt-margin findings are the evidence _chemistry_brief puts in
    front of the adjudicator. Absent on resume, a resumed run weighed strictly less than a
    fresh one."""
    root, raw = run
    (raw / "run_plan.json").write_text(json.dumps({"confidence": "unreviewed"}))
    (raw / "classification.json").write_text(json.dumps({
        "polymer_class": "PVNL", "class_source": "radonpy_polyinfo",
        "chemistry_consistency": {
            "verdict": "consistent", "polarity_class": "polar_protic",
            "backbone_groups": [], "pendant_groups": ["hydroxyl_alcohol"],
            "findings": [{"code": "CHEM_HBOND_NETWORK", "severity": "advisory",
                          "detail": "1 donor"}]}}))

    out = nodes.entry_resolve(_state(root))
    assert out["chemistry"]["pendant_groups"] == ["hydroxyl_alcohol"]
    brief = nodes._chemistry_brief({**_state(root), **out})
    assert "CHEM_HBOND_NETWORK" in brief


def test_resume_without_artifacts_is_still_fine(run):
    """A first-time resume has no grounding or classification; absence must not crash."""
    root, raw = run
    (raw / "run_plan.json").write_text(json.dumps({"confidence": "unreviewed"}))
    out = nodes.entry_resolve(_state(root))
    assert out["entry_node"] == "critique"
    assert "grounding_path" not in out


def test_corrupt_artifacts_do_not_break_resume(run):
    root, raw = run
    (raw / "run_plan.json").write_text(json.dumps({"confidence": "unreviewed"}))
    (raw / "literature_grounding.json").write_text("{not json")
    (raw / "classification.json").write_text("{also not json")
    out = nodes.entry_resolve(_state(root))
    assert out["entry_node"] == "adjudicate"
    assert out["critic_verdict"] is None       # file exists but is unreadable


# --- 2. a failed adjudication must not strand the plan ----------------------
def test_a_failed_adjudication_call_leaves_a_runnable_plan(run, monkeypatch):
    """confidence "unreviewed" is deliberately INVALID -- it is the execution gate. Returning
    without writing left it there, so materialize died two nodes later with
    PLAN_AGENT_CONTRACT_ERROR and a transient streaming abort killed a run that had already
    paid for its critique."""
    root, raw = run
    plan = raw / "run_plan.json"
    plan.write_text(json.dumps({"confidence": "unreviewed", "overrides": {},
                                "decisions": [{"id": "D-01_ff", "evidence": [],
                                               "critique": {"findings": []}}]}))
    monkeypatch.setattr(nodes, "invoke",
                        lambda *a, **k: (_ for _ in ()).throw(HeadlessError("streaming abort")))

    out = nodes.adjudicate(_state(root, plan_path=str(plan)))

    assert json.loads(plan.read_text())["confidence"] == "low"
    assert out["confidence"] == "low"
    assert out.get("status") is None, "a failed critique must not halt the graph"
    assert "streaming abort" in json.loads(plan.read_text())["dominant_uncertainty"]


def test_an_invalid_override_degrades_the_same_way_as_a_failed_call(run, monkeypatch):
    """Both failure modes end in the same place, so there is one behaviour to reason about."""
    root, raw = run
    plan = raw / "run_plan.json"
    plan.write_text(json.dumps({"confidence": "unreviewed", "overrides": {},
                                "decisions": [{"id": "D-01_ff", "evidence": [],
                                               "critique": {"findings": []}}]}))
    monkeypatch.setattr(nodes, "_run",
                        lambda *a, **k: type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})())
    out = nodes.apply_adjudication(
        _state(root, plan_path=str(plan)),
        {"confidence": "high", "dominant_uncertainty": "x", "overrides": {"nonsense_key": 1},
         "critic_evidence": [], "findings": []})
    assert json.loads(plan.read_text())["confidence"] == "low"
    assert out["confidence"] == "low"


# --- 3. execute must not misread a successful campaign ----------------------
def test_execute_finds_the_result_among_stdout_noise(run, monkeypatch):
    """run_campaign_workflow loads the LAMMPS and EMC server modules IN-PROCESS. One of them
    printing to stdout would otherwise turn a campaign that actually succeeded into a
    reported failure -- while workflow_state.json on disk said the opposite."""
    root, raw = run
    plan = raw / "run_plan.json"
    plan.write_text("{}")
    noisy = ("INFO: mpi_ranks not given -- derived 1\n"
             "INFO: gpu_ids not given -- derived \"0\"\n"
             '{"status": "accepted", "run_name": "R", "accepted_attempts": {}}')
    monkeypatch.setattr(nodes, "_run",
                        lambda *a, **k: type("R", (), {"returncode": 0, "stdout": noisy,
                                                       "stderr": ""})())
    out = nodes.execute(_state(root, plan_path=str(plan)))
    assert out["status"] == "accepted"
    assert out["workflow_status"] == "accepted"


def test_execute_reports_failure_when_there_is_genuinely_no_result(run, monkeypatch):
    root, raw = run
    plan = raw / "run_plan.json"
    plan.write_text("{}")
    monkeypatch.setattr(nodes, "_run",
                        lambda *a, **k: type("R", (), {"returncode": 1, "stdout": "traceback",
                                                       "stderr": "boom"})())
    out = nodes.execute(_state(root, plan_path=str(plan)))
    assert out["status"] == "failed"


@pytest.mark.parametrize("status,expected", [
    ("accepted", "accepted"), ("escalation_required", "escalation_required"),
    ("failed", "failed"), ("not_found", "failed"),
])
def test_execute_maps_every_engine_status(run, monkeypatch, status, expected):
    """`not_found` is not one of the engine's three terminal statuses and must not leak
    through as a status the exit-code table has no entry for."""
    root, raw = run
    plan = raw / "run_plan.json"
    plan.write_text("{}")
    monkeypatch.setattr(nodes, "_run",
                        lambda *a, **k: type("R", (), {
                            "returncode": 0, "stdout": json.dumps({"status": status}),
                            "stderr": ""})())
    out = nodes.execute(_state(root, plan_path=str(plan)))
    assert out["status"] == expected
    from state import EXIT_CODES
    assert out["status"] in EXIT_CODES
