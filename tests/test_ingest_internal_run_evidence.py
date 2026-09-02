"""protocol_evidence.py ingest-internal — turns a completed, validated PolyJarvis run into
protocol evidence for planning OTHER polymers, closing the gap between
guides/system_characterization_cache.json (same-SMILES-only replay) and
docs/protocol_evidence_ff.json / protocol_evidence_system_size.json (class/analogue
evidence). rules_common.canonicalize shells into a conda env, so it's monkeypatched to
identity here (same convention as write_characterization_cache.py's own tests)."""
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))

import rules_common
import protocol_evidence as pe  # noqa: E402

PMMA_SMILES = "*CC(*)(C)C(=O)OC"

VALIDATED_ENTRY = {
    "protocol_validated": True,
    "validated_properties": ["density", "tg", "bulk_modulus"],
    "polymer_class": "PACR",
    "source_run_name": "PE1",
    "validated_at": "2026-08-20T12:00:00+00:00",
    "protocol": {
        "decided_params": {
            "dp_typical": 60, "nchain": 40, "T_workflow_K": 300,
            "tg_rates_K_per_ns": [10, 25, 40],
            "alpha_glass_per_K": 2.1e-4, "alpha_melt_per_K": 6.0e-4,
        },
        "decisions": [
            {"id": "D-01_ff", "choice": "pcff"},
            {"id": "D-02_charges", "choice": "none"},
            {"id": "D-03_electrostatics", "choice": "pppm"},
            {"id": "D-04_system_size", "choice": "fox_flory_floor"},
        ],
        "planned_stages": [],
    },
    "simulated_properties": {
        "density": {"value_g_cm3": 1.176},
        "tg": {"value_K": 372.5},
        "bulk_modulus": {"value_GPa": 4.2},
    },
    "notes": "test fixture",
}

BLOCKED_ENTRY = {
    "protocol_validated": False,
    "polymer_class": "PDIE",
    "source_run_name": "cisPBD1",
    "notes": "BLOCKED by requires_cis_lock",
}


@pytest.fixture(autouse=True)
def _identity_canonicalize(monkeypatch):
    monkeypatch.setattr(rules_common, "canonicalize", lambda smi, *a, **k: smi)


def test_evidence_records_cover_only_protocol_choice_fields():
    records = pe.evidence_records_from_completed_run(VALIDATED_ENTRY, "PE1", PMMA_SMILES)
    fields = {r["field"] for r in records}
    assert fields == {"forcefield", "electrostatics", "system_size", "cooling_rate"}


def test_evidence_records_never_emit_measured_value_fields():
    # Gates bind on validity, not accuracy -- a run's acceptance never certifies a
    # measured density/Tg/CTE value is correct, only that the protocol choice it used
    # produced a valid simulation. See the module docstring.
    records = pe.evidence_records_from_completed_run(VALIDATED_ENTRY, "PE1", PMMA_SMILES)
    fields = {r["field"] for r in records}
    assert "density_target" not in fields
    assert "tg_target" not in fields
    assert "cte_glass_melt" not in fields


def test_evidence_records_use_internal_trust_tier_and_pseudo_doi():
    records = pe.evidence_records_from_completed_run(VALIDATED_ENTRY, "PE1", PMMA_SMILES)
    for r in records:
        assert r["trust_tier"] == "internal_validated_run"
        assert r["doi"] == "internal-run:PE1"
        assert r["url"] is None  # pseudo-doi must not synthesize a bogus doi.org URL
        assert r["provenance"]["origin"] == "internal_run"
        assert r["provenance"]["source_run"] == "PE1"
        assert r["smiles"] == [PMMA_SMILES]
        assert r["doi_verified"] is True


def test_forcefield_record_value_matches_decision_choice():
    records = pe.evidence_records_from_completed_run(VALIDATED_ENTRY, "PE1", PMMA_SMILES)
    ff = next(r for r in records if r["field"] == "forcefield")
    assert ff["value"]["recommendation"] == "pcff"


def test_charges_decision_never_mapped_no_matching_field_enum():
    records = pe.evidence_records_from_completed_run(VALIDATED_ENTRY, "PE1", PMMA_SMILES)
    assert not any("charges" in r["field"] for r in records)


def test_all_records_pass_schema_validation():
    records = pe.evidence_records_from_completed_run(VALIDATED_ENTRY, "PE1", PMMA_SMILES)
    for r in records:
        assert pe.validate_record(r) == []


def test_blocked_entry_yields_no_records():
    assert pe.evidence_records_from_completed_run(BLOCKED_ENTRY, "cisPBD1", "*C=CC=C*") == []


def test_missing_decisions_and_measurements_yields_partial_records():
    sparse_entry = {
        "protocol_validated": True, "validated_properties": ["density"],
        "polymer_class": "PHYC", "validated_at": "2026-08-20T00:00:00Z",
        "protocol": {"decided_params": {}, "decisions": [], "planned_stages": []},
        "simulated_properties": {},
    }
    assert pe.evidence_records_from_completed_run(sparse_entry, "PE2", "*CC*") == []


def _write_run_fixture(tmp_path, run_name, smiles):
    run_dir = tmp_path / "data" / run_name
    (run_dir / "raw").mkdir(parents=True)
    (run_dir / "raw" / "run_plan.json").write_text(json.dumps({"smiles": smiles}))
    return run_dir


def test_ingest_from_completed_run_writes_both_stores(tmp_path):
    run_dir = _write_run_fixture(tmp_path, "PE1", PMMA_SMILES)
    cache_path = tmp_path / "system_characterization_cache.json"
    cache_path.write_text(json.dumps({PMMA_SMILES: VALIDATED_ENTRY}))
    ff_store = tmp_path / "protocol_evidence_ff.json"
    size_store = tmp_path / "protocol_evidence_system_size.json"

    result = pe.ingest_from_completed_run(
        "PE1", repo_root=tmp_path, cache_path=cache_path,
        ff_store_path=ff_store, system_size_store_path=size_store)

    assert result["status"] == "written"
    assert result["records_added"] == 4
    ff_data = pe.load_store(str(ff_store), with_methodology=True)
    size_data = pe.load_store(str(size_store))
    assert len(ff_data["records"]) == 3  # forcefield, electrostatics, cooling_rate
    assert len(size_data["records"]) == 1
    assert size_data["records"][0]["field"] == "system_size"


def test_ingest_from_completed_run_content_is_stable_across_reingest(tmp_path):
    # Re-ingesting unchanged data must not accumulate a second generation of records --
    # content stays at 4 total, even though internally it's replace-then-add, not skip.
    _write_run_fixture(tmp_path, "PE1", PMMA_SMILES)
    cache_path = tmp_path / "system_characterization_cache.json"
    cache_path.write_text(json.dumps({PMMA_SMILES: VALIDATED_ENTRY}))
    ff_store = tmp_path / "protocol_evidence_ff.json"
    size_store = tmp_path / "protocol_evidence_system_size.json"

    pe.ingest_from_completed_run("PE1", repo_root=tmp_path, cache_path=cache_path,
                                    ff_store_path=ff_store, system_size_store_path=size_store)
    second = pe.ingest_from_completed_run(
        "PE1", repo_root=tmp_path, cache_path=cache_path,
        ff_store_path=ff_store, system_size_store_path=size_store)

    assert second["records_replaced"] == 4  # prior generation stripped before re-adding
    ff_data = pe.load_store(str(ff_store), with_methodology=True)
    size_data = pe.load_store(str(size_store))
    assert len(ff_data["records"]) == 3
    assert len(size_data["records"]) == 1


def test_reingest_after_revalidation_replaces_not_accumulates(tmp_path):
    # The scenario advisor flagged: re-validate with a DIFFERENT decision (claim text
    # differs -> different record_id under plain dedupe) and confirm only the new
    # generation survives, not both, at the top trust tier.
    _write_run_fixture(tmp_path, "PE1", PMMA_SMILES)
    cache_path = tmp_path / "system_characterization_cache.json"
    ff_store = tmp_path / "protocol_evidence_ff.json"
    size_store = tmp_path / "protocol_evidence_system_size.json"

    cache_path.write_text(json.dumps({PMMA_SMILES: VALIDATED_ENTRY}))
    pe.ingest_from_completed_run("PE1", repo_root=tmp_path, cache_path=cache_path,
                                    ff_store_path=ff_store, system_size_store_path=size_store)

    revalidated_entry = json.loads(json.dumps(VALIDATED_ENTRY))  # deep copy
    revalidated_entry["protocol"]["decisions"][0]["choice"] = "compass"  # FF choice changed
    cache_path.write_text(json.dumps({PMMA_SMILES: revalidated_entry}))
    pe.ingest_from_completed_run("PE1", repo_root=tmp_path, cache_path=cache_path,
                                    ff_store_path=ff_store, system_size_store_path=size_store)

    ff_data = pe.load_store(str(ff_store), with_methodology=True)
    ff_records = [r for r in ff_data["records"] if r["field"] == "forcefield"]
    assert len(ff_records) == 1  # not two disagreeing generations
    assert ff_records[0]["value"]["recommendation"] == "compass"


def test_ingest_skips_when_no_cache_entry_for_smiles(tmp_path):
    _write_run_fixture(tmp_path, "PE1", PMMA_SMILES)
    cache_path = tmp_path / "system_characterization_cache.json"
    cache_path.write_text(json.dumps({}))  # no entry at all

    result = pe.ingest_from_completed_run("PE1", repo_root=tmp_path, cache_path=cache_path)
    assert result["status"] == "skipped"


def test_ingest_skips_blocked_cache_entry(tmp_path):
    _write_run_fixture(tmp_path, "cisPBD1", "*C=CC=C*")
    cache_path = tmp_path / "system_characterization_cache.json"
    cache_path.write_text(json.dumps({"*C=CC=C*": BLOCKED_ENTRY}))

    result = pe.ingest_from_completed_run("cisPBD1", repo_root=tmp_path, cache_path=cache_path)
    assert result["status"] == "skipped"


def test_ingest_skips_when_run_plan_missing(tmp_path):
    result = pe.ingest_from_completed_run("NoSuchRun", repo_root=tmp_path)
    assert result["status"] == "skipped"
