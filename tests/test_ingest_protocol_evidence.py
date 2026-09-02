"""protocol_evidence.py ingest — the write-back half of the query-first/search-on-miss
loop. Feeds it fixture advisory JSONs shaped exactly like literature-grounding-worker's
real Part A / Part B output schemas (see its .md file) and checks:
correct provenance, only verified:true sources persisted, and idempotency (re-ingesting
the same advisory JSON is a no-op the second time)."""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))

import protocol_evidence as pe  # noqa: E402
import rules_common  # noqa: E402  -- pe calls through rules_common.canonicalize

FF_ADVISORY = {
    "polymer_name": "PMMA",
    "polymer_class": "PACR",
    "smiles": "*CC(*)(C)C(=O)OC",
    "generated_at": "2026-08-24T00:00:00Z",
    "forcefield": {
        "recommendation": "PCFF",
        "confidence": "high",
        "sources": [
            {"title": "Verified PMMA FF benchmark", "doi": "10.1/verified-ff", "url": "https://doi.org/10.1/verified-ff",
             "year": 2024, "trust_tier": "peer_reviewed_doi", "claim": "PCFF reproduces PMMA density within 2%.",
             "verified": True},
            {"title": "Unverified candidate", "doi": "10.1/unverified", "url": "https://doi.org/10.1/unverified",
             "year": 2023, "trust_tier": "preprint", "claim": "an unconfirmed claim", "verified": False},
        ],
    },
    "electrostatics": {"recommendation": None, "confidence": "low", "sources": []},
    "cooling_rate_K_per_ns": {"rates": None, "confidence": "low", "sources": []},
    "density_target_gcm3": {"range": None, "T_K": None, "confidence": "low", "sources": []},
    "tg_target_K": {"range": None, "confidence": "low", "sources": []},
    "cte_glass_melt": {"alpha_glass_per_K": None, "alpha_melt_per_K": None, "confidence": "low", "sources": []},
    "dominant_uncertainty": "electrostatics ungrounded",
    "notes": "test fixture",
}

SYSTEM_SIZE_ADVISORY = {
    "polymer_name": "PMMA",
    "polymer_class": "PACR",
    "smiles": "*CC(*)(C)C(=O)OC",
    "generated_at": "2026-08-24T00:00:00Z",
    "system_size": {
        "dp_typical": 60,
        "nchain": 40,
        "convergence_basis": "fox_flory_plateau",
        "confidence": "high",
        "me_estimated_gmol": None,
        "me_estimation_note": None,
        "sources": [
            {"title": "Verified DP convergence study", "doi": "10.1/verified-dp", "url": "https://doi.org/10.1/verified-dp",
             "year": 2022, "trust_tier": "peer_reviewed_doi",
             "claim": "Tg converges above DP=50 for PMMA.", "verified": True},
        ],
    },
    "dominant_uncertainty": "none",
    "notes": "test fixture",
}


def test_ff_ingest_adds_only_verified_sources(tmp_path):
    store_path = str(tmp_path / "protocol_evidence_ff.json")
    result = pe.ingest("ff", FF_ADVISORY, run_name="PE1", store_path=store_path)

    assert result["records_added"] == 1
    assert result["records_skipped_duplicate"] == 0
    assert result["records_rejected"] == []

    store = pe.load_store(store_path, with_methodology=True)
    assert len(store["records"]) == 1
    record = store["records"][0]
    assert record["field"] == "forcefield"
    assert record["doi"] == "10.1/verified-ff"
    assert record["polymer_class"] == "PACR"
    assert record["provenance"]["origin"] == "worker_run"
    assert record["provenance"]["source_run"] == "PE1"


def test_ff_ingest_is_idempotent(tmp_path):
    store_path = str(tmp_path / "protocol_evidence_ff.json")
    pe.ingest("ff", FF_ADVISORY, run_name="PE1", store_path=store_path)
    second = pe.ingest("ff", FF_ADVISORY, run_name="PE1", store_path=store_path)

    assert second["records_added"] == 0
    assert second["records_skipped_duplicate"] == 1
    store = pe.load_store(store_path, with_methodology=True)
    assert len(store["records"]) == 1


def test_ff_ingest_dry_run_does_not_write(tmp_path):
    store_path = str(tmp_path / "protocol_evidence_ff.json")
    result = pe.ingest("ff", FF_ADVISORY, run_name="PE1", store_path=store_path, dry_run=True)
    assert result["records_added"] == 1
    assert not Path(store_path).exists()


def test_system_size_ingest_populates_system_size_value(tmp_path):
    store_path = str(tmp_path / "protocol_evidence_system_size.json")
    result = pe.ingest("system_size", SYSTEM_SIZE_ADVISORY, run_name="PE1", store_path=store_path)

    assert result["records_added"] == 1
    store = pe.load_store(store_path)
    record = store["records"][0]
    assert record["field"] == "system_size"
    assert record["value"]["dp_typical"] == 60
    assert record["value"]["nchain"] == 40


def test_system_size_ingest_lifts_kuhn_fields_when_present(tmp_path):
    advisory = {**SYSTEM_SIZE_ADVISORY,
               "system_size": {**SYSTEM_SIZE_ADVISORY["system_size"],
                               "kuhn_length_A": 20.0, "kuhn_molar_mass_gmol": 1500.0,
                               "kuhn_source_note": "test fixture derivation"}}
    store_path = str(tmp_path / "protocol_evidence_system_size.json")
    pe.ingest("system_size", advisory, run_name="PE1", store_path=store_path)

    store = pe.load_store(store_path)
    value = store["records"][0]["value"]
    assert value["kuhn_length_A"] == 20.0
    assert value["kuhn_molar_mass_gmol"] == 1500.0
    assert value["kuhn_source_note"] == "test fixture derivation"


def test_system_size_ingest_kuhn_fields_default_to_none_when_absent(tmp_path):
    store_path = str(tmp_path / "protocol_evidence_system_size.json")
    pe.ingest("system_size", SYSTEM_SIZE_ADVISORY, run_name="PE1", store_path=store_path)

    store = pe.load_store(store_path)
    value = store["records"][0]["value"]
    assert value["kuhn_length_A"] is None
    assert value["kuhn_molar_mass_gmol"] is None


def test_ingest_canonicalizes_smiles_at_write_time(tmp_path, monkeypatch):
    # rules_common.canonicalize shells into a conda env; stub it so this test exercises
    # ingest's own call-and-store-result logic, not real RDKit.
    monkeypatch.setattr(rules_common, "canonicalize", lambda smi, *a, **k: "CANONICAL_FORM")
    store_path = str(tmp_path / "protocol_evidence_ff.json")
    pe.ingest("ff", FF_ADVISORY, run_name="PE1", store_path=store_path)

    store = pe.load_store(store_path, with_methodology=True)
    assert store["records"][0]["smiles"] == ["CANONICAL_FORM"]


def test_ingest_falls_back_to_raw_smiles_on_canonicalization_failure(tmp_path, monkeypatch):
    def _boom(smi, *a, **k):
        raise RuntimeError("conda env unavailable")

    monkeypatch.setattr(rules_common, "canonicalize", _boom)
    store_path = str(tmp_path / "protocol_evidence_ff.json")
    pe.ingest("ff", FF_ADVISORY, run_name="PE1", store_path=store_path)

    store = pe.load_store(store_path, with_methodology=True)
    assert store["records"][0]["smiles"] == [FF_ADVISORY["smiles"]]


def test_ingest_skips_source_folded_from_store_hit(tmp_path):
    # A source the worker folded in from a `protocol_evidence.py query` hit (marked with
    # origin_record_id) must never be re-ingested as a new record -- the record already
    # exists under that id. Without this, a paraphrased claim would content-hash to a
    # different record_id and silently duplicate the original finding.
    store_hit_advisory = {
        "polymer_name": "PMMA", "polymer_class": "PACR", "smiles": "*CC(*)(C)C(=O)OC",
        "generated_at": "2026-08-24T00:00:00Z",
        "forcefield": {
            "recommendation": "PCFF", "confidence": "high",
            "sources": [
                {"title": "Existing store record", "doi": "10.1/already-in-store",
                 "url": "https://doi.org/10.1/already-in-store", "year": 2025,
                 "trust_tier": "peer_reviewed_doi", "claim": "verbatim claim from the store hit",
                 "verified": True, "origin_record_id": "abc123def456"},
            ],
        },
        "electrostatics": {"recommendation": None, "confidence": "low", "sources": []},
        "cooling_rate_K_per_ns": {"rates": None, "confidence": "low", "sources": []},
        "density_target_gcm3": {"range": None, "T_K": None, "confidence": "low", "sources": []},
        "tg_target_K": {"range": None, "confidence": "low", "sources": []},
        "cte_glass_melt": {"alpha_glass_per_K": None, "alpha_melt_per_K": None, "confidence": "low", "sources": []},
        "dominant_uncertainty": "none", "notes": "test fixture",
    }
    store_path = str(tmp_path / "protocol_evidence_ff.json")
    result = pe.ingest("ff", store_hit_advisory, run_name="PE2", store_path=store_path)

    assert result["records_added"] == 0
    assert result["records_skipped_store_origin"] == 1
    assert result["records_skipped_duplicate"] == 0
    store = pe.load_store(store_path, with_methodology=True)
    assert store["records"] == []  # nothing written -- the finding already lives elsewhere


def test_ingest_still_ingests_genuinely_new_sources_alongside_store_hit_sources(tmp_path):
    mixed_advisory = dict(FF_ADVISORY)
    mixed_advisory["forcefield"] = {
        "recommendation": "PCFF", "confidence": "high",
        "sources": [
            {"title": "New finding", "doi": "10.1/genuinely-new", "url": "https://doi.org/10.1/genuinely-new",
             "year": 2026, "trust_tier": "peer_reviewed_doi", "claim": "a genuinely new claim",
             "verified": True},
            {"title": "Store hit", "doi": "10.1/store-hit", "url": "https://doi.org/10.1/store-hit",
             "year": 2024, "trust_tier": "peer_reviewed_doi", "claim": "verbatim store claim",
             "verified": True, "origin_record_id": "xyz789"},
        ],
    }
    store_path = str(tmp_path / "protocol_evidence_ff.json")
    result = pe.ingest("ff", mixed_advisory, run_name="PE2", store_path=store_path)

    assert result["records_added"] == 1
    assert result["records_skipped_store_origin"] == 1
    store = pe.load_store(store_path, with_methodology=True)
    assert len(store["records"]) == 1
    assert store["records"][0]["doi"] == "10.1/genuinely-new"


def test_ingest_rejects_record_missing_doi(tmp_path):
    broken_advisory = dict(FF_ADVISORY)
    broken_advisory["forcefield"] = {
        "recommendation": "PCFF", "confidence": "high",
        "sources": [{"title": "no doi", "doi": None, "year": 2024, "trust_tier": "preprint",
                     "claim": "a claim", "verified": True}],
    }
    store_path = str(tmp_path / "protocol_evidence_ff.json")
    result = pe.ingest("ff", broken_advisory, run_name="PE1", store_path=store_path)
    assert result["records_added"] == 0
    assert len(result["records_rejected"]) == 1
