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


def _derived(field):
    """The single source of truth for what a field implies -- asserting against a hardcoded
    copy would just re-encode the bug this test exists to catch."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(nodes.SCRIPT_DIR)))
    from make_deterministic_plan import _derived_from_field
    from rules_common import load_rules
    return _derived_from_field(field, load_rules())


def _stub_typing(monkeypatch, *, types_smiles: bool, error: str = ""):
    """Pin the EMC trial build both ways so these stay pure-logic tests.

    _apply_field_change imports `forcefield` inside the function and calls
    forcefield.check_typing, which shells out to a real EMC build. The default suite must not
    depend on EMC being installed, and it must be able to exercise the DECLINE branch, which
    no real SMILES would reach on demand.
    """
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(nodes.SCRIPT_DIR)))
    import forcefield
    monkeypatch.setattr(forcefield, "check_typing",
                        lambda *a, **k: {"types_smiles": types_smiles, "typing_error": error})


def test_a_measured_force_field_change_moves_everything_it_implies(plan_file, tmp_path, monkeypatch):
    """The critic may move the field, and when it does the derivation must follow.

    This test previously asserted the opposite -- that `choice` stayed read-only. That
    contract was deliberately retired on 2026-09-08: the adjudicator is the one component
    that reads force-field literature, and it was the one component that could not act on it.
    Setting overrides.preferred_ff wrote decided_params.preferred_ff while D-01_ff.choice kept
    the old field, which validate_run_plan.py then failed as `ff_choice_not_applied` -- so the
    old behaviour was not "read-only", it was "silently unrunnable".
    """
    _stub_typing(monkeypatch, types_smiles=True)
    doc, _ = _apply(plan_file, tmp_path,
                    {**GOOD, "overrides": {"preferred_ff": "opls/2024/opls-aa"}}, monkeypatch)
    assert doc["decisions"][0]["choice"] == "opls/2024/opls-aa"
    assert doc["overrides"]["preferred_ff"] == "opls/2024/opls-aa"
    # Everything the field implies moves with it, or the plan describes a run nobody built.
    # These land in `overrides` -- materialize_plan copies that wholesale into decided_params.
    assert doc["overrides"]["charge_method"] == _derived("opls/2024/opls-aa")["charge_method"]
    assert doc["overrides"]["electrostatics"] == _derived("opls/2024/opls-aa")["electrostatics"]
    assert doc["hardware"]["ff_family"] == _derived("opls/2024/opls-aa")["ff_family"]
    findings = doc["decisions"][0]["critique"]["findings"]
    assert any("moved the force field" in f for f in findings)


def test_a_force_field_the_builder_cannot_type_is_declined_without_costing_the_critique(
        plan_file, tmp_path, monkeypatch):
    """Buildability is MEASURED, not assumed, and a bad field suggestion is cheap.

    forcefield.select_by_moiety only probes when a moiety rule BLOCKS, so a SMILES that trips
    no rule reaches adjudication with its admissible set unmeasured -- the critic would be
    reasoning about a field nobody has tried. Measured 2026-09-08: compass types only 2 of the
    stereo_r2 campaign's 7 repeat units, so an unchecked switch plans a run that dies at build.
    On a failed probe the FIELD override alone is dropped; the evidence and the uncertainty
    statement that came with it still apply.
    """
    _stub_typing(monkeypatch, types_smiles=False, error="pcff missing {na,c_2}")
    # A second override rides along, because the point is that it SURVIVES the decline.
    doc, _ = _apply(plan_file, tmp_path,
                    {**GOOD, "overrides": {"preferred_ff": "opls/2024/opls-aa",
                                           "cutoff_A": 14.0}}, monkeypatch)
    assert doc["decisions"][0]["choice"] == "pcff"          # unchanged
    assert "preferred_ff" not in doc["overrides"]           # the field override alone is dropped
    assert doc["overrides"]["cutoff_A"] == 14.0             # the rest of the critique survives
    assert doc["confidence"] == "medium"
    findings = doc["decisions"][0]["critique"]["findings"]
    assert any("DECLINED" in f and "opls/2024/opls-aa" in f for f in findings)


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
