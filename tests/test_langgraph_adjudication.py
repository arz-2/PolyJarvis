"""apply_adjudication — what a model is allowed to change in run_plan.json.

SKILL.md step 5 tells an adjudicating session to touch five things and leave everything
else alone. In the headless driver that restriction cannot be a prompt: the model has no
Write tool and never touches the file, so the restriction is whatever this function does.
These tests are therefore the actual enforcement, and they run with no model in the loop.

The `origin` tag is the subtlest part. benchmarks/.../llm_contribution.py measures the LLM's
contribution by counting evidence entries tagged origin:"critic" against the tool's own
origin:"autofill" baseline. If a model could set `origin` itself, that measurement would be
self-reported. It cannot: `origin` is absent from the adjudication schema and stamped here.
"""
import copy
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "langgraph"))
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))

import nodes  # noqa: E402
import schemas  # noqa: E402

BASE_PLAN = {
    "schema_version": "2.0", "run_name": "R", "polymer_class": "PSTR", "smiles": "*CC*",
    "goal": "g", "properties": ["density"], "plan_mode": "scaffold",
    "confidence": "unreviewed", "dominant_uncertainty": "tool default",
    "decisions": [{
        "id": "D-01_ff", "choice": "pcff", "admissible": ["pcff"],
        "evidence": [{"claim": "class prior", "origin": "autofill"}],
        "critique": {"findings": []},
    }],
    "overrides": {},
    "decided_params": {"cutoff_A": 12.0},
    "planned_stages": ["build"],
    "system_size": {"resolved_by": "select_system_size.solve_system_size"},
    "cost_estimate": {"total_gpu_hours": 4.0},
}


@pytest.fixture
def plan_file(tmp_path):
    path = tmp_path / "run_plan.json"
    path.write_text(json.dumps(BASE_PLAN, indent=2))
    return path


def _state(plan_file, tmp_path):
    return {"plan_path": str(plan_file), "repo_root": str(tmp_path), "run_name": "R"}


def _apply(plan_file, tmp_path, decision, monkeypatch):
    # validate_run_plan is a separate concern with its own suite; stub the subprocess so
    # these tests stay pure logic.
    monkeypatch.setattr(nodes, "_run", lambda *a, **k: type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})())
    out = nodes.apply_adjudication(_state(plan_file, tmp_path), decision)
    return json.loads(plan_file.read_text()), out


GOOD = {
    "confidence": "medium",
    "dominant_uncertainty": "no measured Tg for this exact SMILES",
    "overrides": {"cutoff_A": 14.0},
    "critic_evidence": [{"claim": "PCFF reproduces PS density",
                         "source_doi": "10.1000/x", "citation": "A Study"}],
    "findings": ["declined the suggested TraPPE override: analog lead only"],
}


def test_applies_exactly_the_five_permitted_keys_and_nothing_else(plan_file, tmp_path, monkeypatch):
    doc, _ = _apply(plan_file, tmp_path, GOOD, monkeypatch)

    assert doc["confidence"] == "medium"
    assert doc["dominant_uncertainty"] == GOOD["dominant_uncertainty"]
    assert doc["overrides"] == {"cutoff_A": 14.0}
    assert len(doc["decisions"][0]["evidence"]) == 2
    assert doc["decisions"][0]["critique"]["findings"] == GOOD["findings"]

    # Everything outside those five is byte-identical.
    before, after = copy.deepcopy(BASE_PLAN), copy.deepcopy(doc)
    for d in (before, after):
        d.pop("confidence"), d.pop("dominant_uncertainty"), d.pop("overrides")
        d["decisions"][0].pop("evidence"), d["decisions"][0].pop("critique")
    assert before == after


def test_origin_is_stamped_by_python_not_supplied_by_the_model(plan_file, tmp_path, monkeypatch):
    """A model that could set origin itself would be self-reporting its own contribution."""
    hostile = {**GOOD, "critic_evidence": [
        {"claim": "c", "source_doi": "10.1/x", "citation": "t", "origin": "autofill"}]}
    doc, _ = _apply(plan_file, tmp_path, hostile, monkeypatch)
    appended = doc["decisions"][0]["evidence"][-1]
    assert appended["origin"] == "critic"
    # `origin` is not an accepted property of a critic_evidence item, so a model cannot
    # supply one at all -- it only appears in that field's human-readable description.
    item = schemas.adjudication_schema({})["properties"]["critic_evidence"]["items"]
    assert "origin" not in item["properties"]
    assert "origin" not in item["required"]


def test_autofill_evidence_can_be_neither_deleted_nor_retagged(plan_file, tmp_path, monkeypatch):
    doc, _ = _apply(plan_file, tmp_path, GOOD, monkeypatch)
    autofill = [e for e in doc["decisions"][0]["evidence"] if e.get("origin") == "autofill"]
    assert autofill == BASE_PLAN["decisions"][0]["evidence"]


def test_evidence_and_findings_are_append_only(plan_file, tmp_path, monkeypatch):
    doc, _ = _apply(plan_file, tmp_path, GOOD, monkeypatch)
    assert doc["decisions"][0]["evidence"][0] == BASE_PLAN["decisions"][0]["evidence"][0]
    doc2, _ = _apply(plan_file, tmp_path, GOOD, monkeypatch)
    assert len(doc2["decisions"][0]["evidence"]) == 3  # appended again, never replaced


def test_the_force_field_choice_stays_read_only(plan_file, tmp_path, monkeypatch):
    """materialize_plan reads criteria_evaluated/evidence/alternatives off the row and
    ignores `choice`, so letting a model edit it would be a silent no-op that looks like a
    decision. Disagreement travels through `overrides`, which is validated."""
    doc, _ = _apply(plan_file, tmp_path,
                    {**GOOD, "overrides": {"preferred_ff": "opls/2024/opls-aa"}}, monkeypatch)
    assert doc["decisions"][0]["choice"] == "pcff"
    assert doc["overrides"]["preferred_ff"] == "opls/2024/opls-aa"


def test_a_force_field_outside_the_measured_set_is_rejected(plan_file, tmp_path, monkeypatch):
    """ENUM_OVERRIDES holds the fields EMC actually has; a plausible-looking name that is
    not one of them ("opls-aa") must not reach the plan."""
    doc, out = _apply(plan_file, tmp_path,
                      {**GOOD, "overrides": {"preferred_ff": "opls-aa"}}, monkeypatch)
    assert doc["overrides"] == {}
    assert out["confidence"] == "low"


def test_an_override_outside_the_allowlist_never_reaches_disk(plan_file, tmp_path, monkeypatch):
    doc, out = _apply(plan_file, tmp_path,
                      {**GOOD, "overrides": {"lammps_command": "rm -rf /"}}, monkeypatch)
    assert "lammps_command" not in doc["overrides"]
    assert doc["overrides"] == {}
    assert out["confidence"] == "low"


def test_an_out_of_range_override_degrades_to_the_deterministic_baseline(plan_file, tmp_path, monkeypatch):
    """A model hiccup should cost the critique, not the campaign: the plan stays runnable
    at confidence 'low' rather than halting the graph."""
    doc, out = _apply(plan_file, tmp_path, {**GOOD, "overrides": {"cutoff_A": 9999.0}},
                      monkeypatch)
    assert doc["confidence"] == "low"
    assert "adjudication rejected" in doc["dominant_uncertainty"]
    assert out["events"][0]["note"].startswith("fell back")


def test_an_invalid_confidence_falls_back_to_low_rather_than_reaching_the_plan(plan_file, tmp_path, monkeypatch):
    """'unreviewed' is the one value that must never survive: it is the execution gate."""
    doc, _ = _apply(plan_file, tmp_path, {**GOOD, "confidence": "unreviewed"}, monkeypatch)
    assert doc["confidence"] == "low"


def test_overrides_are_replaced_not_merged(plan_file, tmp_path, monkeypatch):
    """materialize_plan copies `overrides` wholesale into decided_params, so a merge would
    keep a superseded key alive after the adjudicator dropped it."""
    plan_file.write_text(json.dumps({**BASE_PLAN, "overrides": {"dp_typical": 40}}))
    doc, _ = _apply(plan_file, tmp_path, GOOD, monkeypatch)
    assert doc["overrides"] == {"cutoff_A": 14.0}


def test_confidence_enum_in_the_model_contract_excludes_unreviewed():
    enum = schemas.adjudication_schema({})["properties"]["confidence"]["enum"]
    assert set(enum) == {"low", "medium", "high"}
