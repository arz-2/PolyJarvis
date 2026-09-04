"""The `run-plan` subcommand: a COMPLETE deterministic plan, not a scaffold.

Renamed from test_make_decision.py on 2026-09-04, when decision.json was folded into
run_plan.json. There is no separate decision artifact any more: `run-plan` writes the full
D-01_ff row -- one evidence entry per criterion decision_policy.json names -- straight into the
plan, and `confidence` is the only thing left blocking materialization.

There is also only ONE row. D-02_charges, D-03_electrostatics and D-08_hardware were never
decisions: each is a pure function of the field D-01 resolves (verified 21/21 across the class
table), so they are derived into decided_params/hardware instead. D-04_system_size was a solver,
not a choice, and lives in plan["system_size"].
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))

from make_deterministic_plan import make_plan, build_decisions, KNOWN_DECISIONS  # noqa: E402
from rules_common import get_class_entry, load_rules  # noqa: E402
from scientific_control import PlanDecision, ScientificIntent, materialize_plan  # noqa: E402

PS_SMILES = "*CC(c1ccccc1)*"
SCRIPT = str(REPO_ROOT / "orchestration" / "scripts" / "make_deterministic_plan.py")


@pytest.fixture(scope="module")
def pstr_plan():
    """One real resolve, shared: solve_system_size and select_hardware each shell into the
    RDKit conda env, so building this per-test would make the module minutes long."""
    return make_plan("PSTR_PLAN_TEST", "PSTR", PS_SMILES, {"density", "tg", "bulk_modulus"})


@pytest.fixture(scope="module")
def d01(pstr_plan):
    return pstr_plan["decisions"][0]


def test_the_plan_has_exactly_one_decision_row(pstr_plan):
    assert [r["id"] for r in pstr_plan["decisions"]] == ["D-01_ff"]
    assert KNOWN_DECISIONS == {"D-01_ff"}


def test_the_retired_rows_are_derived_not_decided(pstr_plan):
    """D-02/D-03/D-08 must not come back as rows, and their values must still be present --
    derived from the resolved field, which is what stops a recorded charge scheme from
    disagreeing with the field actually built."""
    ids = {r["id"] for r in pstr_plan["decisions"]}
    assert not ids & {"D-02_charges", "D-03_electrostatics", "D-04_system_size", "D-08_hardware"}
    dp = pstr_plan["decided_params"]
    assert dp["charge_method"] == "bond-increment"   # pcff family
    assert dp["electrostatics"] == "pppm"
    assert pstr_plan["hardware"]["ff_family"] == "pcff"
    assert pstr_plan["system_size"]["dp_typical"]


def test_the_row_carries_choice_and_the_autofill_provenance_keys(d01):
    for key in ("choice", "criteria_evaluated", "evidence", "alternatives"):
        assert key in d01, key
    assert d01["resolved_by"], "the row must name the resolver that decided it"


def test_confidence_is_the_only_forcing_function(pstr_plan):
    assert pstr_plan["confidence"] == "unreviewed"
    assert pstr_plan["overrides"] == {}, "overrides is the critic's lever, never the tool's"


def test_baseline_flag_stamps_a_materializable_confidence():
    assert make_plan("B", "PSTR", PS_SMILES, {"density"}, baseline=True)["confidence"] == "low"


def test_every_policy_criterion_gets_its_own_evidence_entry(d01):
    """The point of the autofill: not just a choice, but a finding against each criterion the
    policy names -- including the ones this layer cannot reach, which say so explicitly."""
    covered = {e.get("criterion") for e in d01["evidence"]}
    missing = set(d01["criteria_evaluated"]) - covered
    assert not missing, f"D-01_ff leaves {missing} unaddressed"


def test_the_row_carries_a_real_citation(d01):
    """validate_run_plan.py requires source_doi or citation on D-01."""
    assert any(e.get("source_doi") or e.get("citation") for e in d01["evidence"])


def test_autofilled_evidence_is_tagged_so_the_benchmark_can_exclude_it(d01):
    """benchmarks/.../llm_contribution.py keys off origin to keep the deterministic baseline
    out of the LLM-contribution count."""
    for e in d01["evidence"]:
        assert e.get("origin") == "autofill", e


def test_criteria_evaluated_matches_policy(d01):
    policy = json.loads((REPO_ROOT / "orchestration" / "decision_policy.json").read_text())
    by_id = {p["decision_id"]: p for p in policy["policies"].values()}
    assert d01["criteria_evaluated"] == by_id["D-01_ff"]["evaluate"]


def test_hardware_differs_by_forcefield_family(pstr_plan):
    """Hardware is no longer a decision row, but it must still route on the FF family: PSTR is
    pcff, PHYC is trappe-ua, and those price to different configurations."""
    phyc = make_plan("H", "PHYC", "*CC*", {"density"})
    assert pstr_plan["hardware"]["ff_family"] == "pcff"
    assert phyc["hardware"]["ff_family"] == "trappe"
    assert pstr_plan["hardware"] != phyc["hardware"]


def test_build_decisions_omits_runtime_gated_policies():
    """D-05/D-06/D-07 have no pre-simulation default choice -- decision_policy.json defines
    all three as mechanized runtime gate verdicts (equil_verdict/tg_gate_verdict/
    bm_gate_verdict) to route on, never re-derive."""
    ids = {row["id"] for row in build_decisions(get_class_entry(load_rules(), "PSTR"))}
    assert ids == {"D-01_ff"}
    for gated in ("D-05_convergence", "D-06_tg_fit_quality", "D-07_property_method"):
        assert gated not in ids


def test_the_plan_materializes_once_confidence_is_set(pstr_plan):
    decision = PlanDecision(
        polymer_class="PSTR", properties=("density", "bulk_modulus"),
        rationale=("Reviewed.",), dominant_uncertainty="protocol_transferability",
        confidence="medium",
    )
    intent = ScientificIntent(
        run_name="DECISION_TEST", goal="Compute density and bulk modulus at 300 K",
        smiles=PS_SMILES, requested_properties=("density", "bulk_modulus"),
        polymer_class_hint="PSTR",
    )
    plan = materialize_plan(intent, decision)
    assert {row["id"] for row in plan["decisions"]} == {"D-01_ff"}
    assert plan["plan_mode"] == "reasoned"
    assert plan["confidence"] == "medium"


def test_cli_refuses_to_overwrite_without_force(tmp_path):
    """run_plan.json is where the critique is adjudicated now, so the no-clobber protection
    moved onto it from the retired `decision` subcommand."""
    out = tmp_path / "run_plan.json"
    out.write_text('{"existing": "critique work"}')
    r = subprocess.run([sys.executable, SCRIPT, "run-plan", "--run_name", "X",
                        "--polymer_class", "PSTR", "--smiles", PS_SMILES,
                        "--properties", "density", "--out", str(out)],
                       capture_output=True, text=True)
    assert r.returncode != 0
    assert json.loads(out.read_text()) == {"existing": "critique work"}


def test_cli_force_overwrites(tmp_path):
    out = tmp_path / "run_plan.json"
    out.write_text('{"existing": "stale"}')
    r = subprocess.run([sys.executable, SCRIPT, "run-plan", "--run_name", "X",
                        "--polymer_class", "PSTR", "--smiles", PS_SMILES,
                        "--properties", "density", "--out", str(out), "--force"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert json.loads(out.read_text())["decisions"][0]["id"] == "D-01_ff"
