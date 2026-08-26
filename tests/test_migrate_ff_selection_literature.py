"""migrate_ff_selection_literature.py — the one-time migration from the legacy flat
literature dump into the structured store. Runs against a small hand-built fixture
(not the real 174KB docs/ff_selection_literature.json) shaped like the real file's two
section styles (sub_questions.<key> and top-level numbered sections), covering: exact
class mapping via polymer_rules examples/member_smiles, the " -- " qualifier split that
keeps negation text out of the match (the real file's actual failure mode -- e.g. "X --
NOT studied"), section-key-hint fallback, unmapped-name logging (never guessed), and
determinism (two runs on unchanged input produce byte-identical records)."""
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))

import migrate_ff_selection_literature as mfsl  # noqa: E402

RULES = {
    "classes": {
        "PACR": {
            "examples": ["PMMA", "PMA", "PAA"],
            "member_smiles": {"PMMA": ["*CC(*)(C)C(=O)OC"]},
        },
        "PSIL": {
            "examples": ["PDMS", "PMHS"],
            "member_smiles": {"PDMS": ["*[Si](*)(C)C"]},
        },
        "PIMD": {
            "examples": ["PI", "PMDA-ODA", "Kapton"],
            "member_smiles": {"note": "structural class, no single member SMILES"},
        },
    }
}

FIXTURE_DOC = {
    "scope": "test scope",
    "generated_at": "2026-08-01T00:00:00Z",
    "sub_questions": {
        "1_benchmark_studies": {
            "findings": [
                {
                    "claim": "PDMS 5-force-field benchmark.",
                    "doi": "10.1021/example.pdms",
                    "title": "PDMS FF benchmark",
                    "year": 2025,
                    "doi_verified": True,
                    "polymers": ["PDMS"],
                    "fields": ["COMPASS", "OPLS-AA"],
                    "reported_errors": "density RMSE varies",
                    "relevance": "direct benchmark",
                },
                {
                    "claim": "Cross-polymer high-throughput screen, not per-polymer specific.",
                    "doi": "10.1021/example.crosspoly",
                    "title": "Cross-polymer screen",
                    "year": 2024,
                    "doi_verified": True,
                    "polymers": ["315 polymers, cross-chemistry screening set"],
                    "fields": ["GAFF2"],
                    "reported_errors": "n/a",
                    "relevance": "methodology only",
                },
            ],
            "synthesis": "narrative text not migrated",
            "gaps": "narrative text not migrated",
        },
    },
    "9_pacr_pcff_pmma_ester_2026_08": {
        "findings": [
            {
                "claim": "Class II fields reproduce PMMA density within 2%.",
                "doi": "10.1016/example.pmma",
                "title": "PMMA review",
                "year": 2025,
                "doi_verified": True,
                "polymers": ["PMMA"],
                "fields": ["PCFF/COMPASS (Class II)"],
                "reported_errors": "within 2%",
                "relevance": "direct",
            },
        ],
        "synthesis": "narrative", "gaps": "narrative",
    },
    "20_pimd_pcff_polyimide_kapton_2026_08": {
        "findings": [
            {
                "claim": "A different polyimide chemistry was studied, not Kapton itself.",
                "doi": "10.1002/example.polyimide",
                "title": "Different polyimide",
                "year": 2023,
                "doi_verified": True,
                "polymers": ["4,4'BPADA+DDS -- all aromatic polyetherimides; PMDA-ODA/Kapton NOT studied"],
                "fields": ["PCFF"],
                "reported_errors": "n/a",
                "relevance": "negative/scope-mismatch example",
            },
        ],
        "synthesis": "narrative", "gaps": "narrative",
    },
    "selection_criteria_extracted": [
        {"criterion": "prefer chemistry-matched benchmarks", "how_to_apply": "...",
         "evidence_strength": "moderate", "sources": ["10.1021/example.pdms"]},
    ],
    "contradictions_with_our_measurements": "narrative, not migrated",
    "overall_confidence": "narrative, not migrated",
}


def _write_fixture(tmp_path) -> str:
    path = tmp_path / "ff_selection_literature.json"
    path.write_text(json.dumps(FIXTURE_DOC))
    return str(path)


def test_direct_class_examples_match(tmp_path):
    store, report = mfsl.migrate(_write_fixture(tmp_path), RULES)
    pdms_records = [r for r in store["records"] if "PDMS" in r["polymer_names"]]
    assert len(pdms_records) == 1
    assert pdms_records[0]["polymer_class"] == "PSIL"
    assert pdms_records[0]["smiles"] == ["*[Si](*)(C)C"]


def test_direct_name_match_takes_priority_over_hint(tmp_path):
    store, report = mfsl.migrate(_write_fixture(tmp_path), RULES)
    pmma_records = [r for r in store["records"] if r["doi"] == "10.1016/example.pmma"]
    assert len(pmma_records) == 1
    assert pmma_records[0]["polymer_class"] == "PACR"
    assert not any(h["doi"] == "10.1016/example.pmma" for h in report["section_key_hint_findings"])


def test_qualifier_split_prevents_false_positive_negation_match_and_falls_to_hint(tmp_path):
    store, report = mfsl.migrate(_write_fixture(tmp_path), RULES)
    negated_record = next(r for r in store["records"] if r["doi"] == "10.1002/example.polyimide")
    # "PMDA-ODA/Kapton NOT studied" sits after " -- " and must not drive a direct-name
    # match; the part before " -- " ("4,4'BPADA+DDS") doesn't match PIMD's examples
    # either, so this must fall through to the section-key hint (PIMD from
    # "20_pimd_..."), not a false PIMD-via-Kapton "direct name" match that would
    # misleadingly look like stronger evidence than it is.
    assert negated_record["polymer_class"] == "PIMD"
    assert any(h["doi"] == "10.1002/example.polyimide" for h in report["section_key_hint_findings"])


def test_unmapped_cross_polymer_name_is_logged_not_guessed(tmp_path):
    store, report = mfsl.migrate(_write_fixture(tmp_path), RULES)
    crosspoly_records = [r for r in store["records"] if r["doi"] == "10.1021/example.crosspoly"]
    assert len(crosspoly_records) == 1
    assert crosspoly_records[0]["polymer_class"] is None
    assert any(u["doi"] == "10.1021/example.crosspoly" for u in report["unmapped_findings"])


def test_methodology_criteria_carried_over_verbatim(tmp_path):
    store, report = mfsl.migrate(_write_fixture(tmp_path), RULES)
    assert store["methodology_criteria"] == FIXTURE_DOC["selection_criteria_extracted"]


def test_narrative_fields_not_migrated_into_records(tmp_path):
    store, report = mfsl.migrate(_write_fixture(tmp_path), RULES)
    for record in store["records"]:
        assert "synthesis" not in record
        assert "gaps" not in record


def test_migration_is_deterministic_across_runs(tmp_path):
    fixture_path = _write_fixture(tmp_path)
    store1, _ = mfsl.migrate(fixture_path, RULES)
    store2, _ = mfsl.migrate(fixture_path, RULES)
    assert store1["records"] == store2["records"]


def test_report_counts_are_consistent(tmp_path):
    store, report = mfsl.migrate(_write_fixture(tmp_path), RULES)
    assert report["findings_processed"] == 4
    assert report["records_emitted"] == len(store["records"])
