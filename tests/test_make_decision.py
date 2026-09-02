"""The `decision` subcommand: a COMPLETE deterministic decision, not a scaffold.

Renamed from test_make_decision_scaffold.py on 2026-09-02, when make_decision_scaffold()
became make_decision(): every row is now resolved from this repo's own resolvers, and
`confidence` is the only thing left blocking materialization.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))

from make_deterministic_plan import make_decision  # noqa: E402
from make_deterministic_plan import build_decisions  # noqa: E402
from rules_common import get_class_entry, load_rules  # noqa: E402
from scientific_control import PlanDecision, materialize_plan, ScientificIntent  # noqa: E402


EXPECTED_IDS = {
    "D-01_ff", "D-02_charges", "D-03_electrostatics", "D-04_system_size", "D-08_hardware",
}
PS_SMILES = "*CC(c1ccccc1)*"
SCRIPT = str(REPO_ROOT / "orchestration" / "scripts" / "make_deterministic_plan.py")


@pytest.fixture(scope="module")
def pstr_decision():
    """One real resolve, shared: solve_system_size and select_hardware each shell into the
    RDKit conda env, so building this per-test would make the module minutes long."""
    return make_decision("PSTR", PS_SMILES, {"density", "tg", "bulk_modulus"})


def test_decision_has_exactly_five_rows_covering_pre_simulation_decisions(pstr_decision):
    assert set(pstr_decision["decision_evaluations"]) == EXPECTED_IDS


def test_rows_carry_default_choice_and_the_autofill_provenance_keys(pstr_decision):
    for row_id, row in pstr_decision["decision_evaluations"].items():
        assert "default_choice" in row, row_id
        assert "criteria_evaluated" in row
        assert "evidence" in row
        assert "alternatives" in row
        assert row["resolved_by"], f"{row_id} must name the resolver that decided it"


def test_confidence_is_now_the_only_forcing_function(pstr_decision):
    """rationale used to be the other half of the block. The tool writes it now, so a run
    that skips review is stopped by confidence alone."""
    assert pstr_decision["rationale"], "rationale is autofilled, not left empty"
    assert pstr_decision["confidence"] == "unreviewed"
    assert pstr_decision["overrides"] == {}, "overrides is the critic's lever, never the tool's"


def test_baseline_flag_stamps_a_materializable_confidence():
    baseline = make_decision("PSTR", PS_SMILES, {"density"}, baseline=True)
    assert baseline["confidence"] == "low"
    assert any("BASELINE ARM" in r for r in baseline["rationale"])


def test_every_policy_criterion_gets_its_own_evidence_entry(pstr_decision):
    """The point of the autofill: not just a choice, but a finding against each criterion the
    policy names -- including the ones this layer cannot reach, which say so explicitly."""
    for row_id, row in pstr_decision["decision_evaluations"].items():
        covered = {e.get("criterion") for e in row["evidence"]}
        missing = set(row["criteria_evaluated"]) - covered
        assert not missing, f"{row_id} leaves {missing} unaddressed"


def test_evidence_required_policies_carry_a_real_citation(pstr_decision):
    """validate_run_plan.py requires source_doi or citation on D-01/D-03. Before 2026-09-02
    D-03's seeded entry had only a bare `source` key and never satisfied it."""
    for row_id in ("D-01_ff", "D-03_electrostatics"):
        ev = pstr_decision["decision_evaluations"][row_id]["evidence"]
        assert any(e.get("source_doi") or e.get("citation") for e in ev), row_id


def test_autofilled_evidence_is_tagged_so_the_benchmark_can_exclude_it(pstr_decision):
    """benchmarks/.../llm_contribution.py keys off origin to keep the deterministic baseline
    out of the LLM-contribution count."""
    for row in pstr_decision["decision_evaluations"].values():
        for e in row["evidence"]:
            assert e.get("origin") == "autofill", e


def test_d04_default_choice_is_derived_not_the_dead_class_keys(pstr_decision):
    """polymer_rules.json's per-class dp_typical/nchain were removed 2026-09-02; reading them
    off the class rendered the literal string "DP=None, nchain=None"."""
    choice = pstr_decision["decision_evaluations"]["D-04_system_size"]["default_choice"]
    assert "None" not in choice, choice
    assert choice.startswith("DP=")


def test_criteria_evaluated_matches_policy(pstr_decision):
    policy = json.loads((REPO_ROOT / "orchestration" / "decision_policy.json").read_text())
    by_id = {p["decision_id"]: p for p in policy["policies"].values()}
    for row_id, row in pstr_decision["decision_evaluations"].items():
        assert row["criteria_evaluated"] == by_id[row_id]["evaluate"]


def test_hardware_default_choice_differs_by_forcefield_family(pstr_decision):
    """D-08 is resolved per-molecule by select_hardware now, but it must still route on the FF
    family: PSTR is pcff, PHYC is trappe-ua, and those price to different configurations."""
    phyc = make_decision("PHYC", "*CC*", {"density"})
    assert (pstr_decision["decision_evaluations"]["D-08_hardware"]["default_choice"]
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


def test_autofilled_decision_materializes_once_confidence_is_set():
    decision_dict = make_decision("PSTR", PS_SMILES, {"density", "bulk_modulus"})
    decision_dict["confidence"] = "medium"
    decision = PlanDecision.from_dict(decision_dict)
    intent = ScientificIntent(
        run_name="DECISION_TEST",
        goal="Compute density and bulk modulus at 300 K",
        smiles=PS_SMILES,
        requested_properties=("density", "bulk_modulus"),
        polymer_class_hint="PSTR",
    )
    plan = materialize_plan(intent, decision)
    assert {row["id"] for row in plan["decisions"]} == EXPECTED_IDS


def test_cli_requires_smiles_for_decision():
    """D-01/D-02/D-03/D-04/D-08 are all resolved per-molecule now."""
    result = subprocess.run(
        [sys.executable, SCRIPT, "decision", "--run_name", "X", "--polymer_class", "PSTR",
         "--out", "-"],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "--smiles is required" in result.stderr


def test_cli_refuses_to_overwrite_without_force(tmp_path):
    out_path = tmp_path / "decision.json"
    out_path.write_text("{}")
    result = subprocess.run(
        [sys.executable, SCRIPT, "decision", "--run_name", "X", "--polymer_class", "PSTR",
         "--smiles", PS_SMILES, "--out", str(out_path)],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "already exists" in result.stderr
    assert out_path.read_text() == "{}"


def test_cli_force_overwrites(tmp_path):
    out_path = tmp_path / "decision.json"
    out_path.write_text("{}")
    result = subprocess.run(
        [sys.executable, SCRIPT, "decision", "--run_name", "X", "--polymer_class", "PSTR",
         "--smiles", PS_SMILES, "--out", str(out_path), "--force"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    written = json.loads(out_path.read_text())
    assert set(written["decision_evaluations"]) == EXPECTED_IDS
