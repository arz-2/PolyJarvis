import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))

from make_deterministic_plan import make_decision_scaffold  # noqa: E402
from make_deterministic_plan import build_decisions  # noqa: E402
from rules_common import get_class_entry, load_rules  # noqa: E402
from scientific_control import PlanDecision, materialize_plan, ScientificIntent  # noqa: E402


EXPECTED_IDS = {
    "D-01_ff", "D-02_charges", "D-03_electrostatics", "D-04_system_size", "D-08_hardware",
}


def test_scaffold_has_exactly_five_rows_covering_pre_simulation_decisions():
    scaffold = make_decision_scaffold("PSTR", {"density", "tg", "bulk_modulus"})
    assert set(scaffold["decision_evaluations"]) == EXPECTED_IDS


def test_scaffold_rows_carry_default_choice_readonly_field():
    scaffold = make_decision_scaffold("PSTR", {"density"})
    for row_id, row in scaffold["decision_evaluations"].items():
        assert "default_choice" in row, row_id
        assert "criteria_evaluated" in row
        assert "evidence" in row
        assert "alternatives" in row


def test_scaffold_forcing_functions_are_deliberately_invalid():
    scaffold = make_decision_scaffold("PSTR", {"density"})
    assert scaffold["rationale"] == []
    assert scaffold["confidence"] == "unreviewed"


def test_scaffold_criteria_evaluated_matches_policy():
    policy = json.loads((REPO_ROOT / "orchestration" / "decision_policy.json").read_text())
    by_id = {p["decision_id"]: p for p in policy["policies"].values()}
    scaffold = make_decision_scaffold("PSTR", {"density"})
    for row_id, row in scaffold["decision_evaluations"].items():
        assert row["criteria_evaluated"] == by_id[row_id]["evaluate"]


def test_hardware_default_choice_differs_by_forcefield_family():
    pstr = make_decision_scaffold("PSTR", {"density"})
    phyc = make_decision_scaffold("PHYC", {"density"})
    assert (pstr["decision_evaluations"]["D-08_hardware"]["default_choice"]
            != phyc["decision_evaluations"]["D-08_hardware"]["default_choice"])


def test_build_decisions_omits_runtime_gated_policies():
    """D-05/D-06/D-07 have no pre-simulation default choice -- decision_policy.json defines
    all three as mechanized runtime gate verdicts (equil_verdict/tg_gate_verdict/
    bm_gate_verdict) to route on, never re-derive."""
    cls = get_class_entry(load_rules(), "PSTR")
    ids = {row["id"] for row in build_decisions(cls)}
    assert ids == EXPECTED_IDS
    assert "D-05_convergence" not in ids
    assert "D-06_tg_fit_quality" not in ids
    assert "D-07_property_method" not in ids


def test_annotated_scaffold_materializes_without_error():
    scaffold = make_decision_scaffold("PSTR", {"density", "bulk_modulus"})
    scaffold["rationale"] = ["Class defaults are appropriate for this polystyrenic system."]
    scaffold["confidence"] = "medium"
    scaffold["decision_evaluations"]["D-03_electrostatics"]["evidence"] = [
        {"claim": "PPPM required for aromatic backbone", "citation": "class evidence"}
    ]
    decision = PlanDecision.from_dict(scaffold)
    intent = ScientificIntent(
        run_name="SCAFFOLD_TEST",
        goal="Compute density and bulk modulus at 300 K",
        smiles="*CC(c1ccccc1)*",
        requested_properties=("density", "bulk_modulus"),
        polymer_class_hint="PSTR",
    )
    plan = materialize_plan(intent, decision)
    assert {row["id"] for row in plan["decisions"]} == EXPECTED_IDS


def test_cli_refuses_to_overwrite_without_force(tmp_path):
    out_path = tmp_path / "decision.json"
    out_path.write_text("{}")
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "orchestration" / "scripts" / "make_deterministic_plan.py"),
         "decision", "--run_name", "X", "--polymer_class", "PSTR", "--out", str(out_path)],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "already exists" in result.stderr
    assert out_path.read_text() == "{}"


def test_cli_force_overwrites(tmp_path):
    out_path = tmp_path / "decision.json"
    out_path.write_text("{}")
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "orchestration" / "scripts" / "make_deterministic_plan.py"),
         "decision", "--run_name", "X", "--polymer_class", "PSTR", "--out", str(out_path), "--force"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    written = json.loads(out_path.read_text())
    assert set(written["decision_evaluations"]) == EXPECTED_IDS
