#!/usr/bin/env python3
"""
migrate_ff_selection_literature.py — one-time migration of docs/ff_selection_literature.json
into the structured docs/protocol_evidence_ff.json store.

docs/ff_selection_literature.json is a flat, narrative-shaped literature-review dump:
top-level `sub_questions.<key>` AND top-level numbered section keys (e.g.
"9_pacr_pcff_pmma_ester_2026_08") each hold {findings: [...], synthesis, gaps}. Every
`findings[]` entry maps to one ProtocolEvidenceRecord (field="forcefield" — the legacy
file is entirely FF-selection-scoped). `selection_criteria_extracted` carries over
verbatim into the new store's `methodology_criteria` (it's methodology, not a per-study
finding, so it doesn't belong in `records[]`). `synthesis`/`gaps`/
`contradictions_with_our_measurements`/`overall_confidence` have no clean per-record
home and are intentionally left behind in the legacy file, which stays in the repo
(frozen, not deleted) as the historical narrative record.

Deterministic and re-runnable: given the same source content, output is byte-identical
(stable sort: polymer_class, then year desc, then record_id). Never guesses a class —
an unmappable polymer name is logged in the migration report and left `polymer_class:
null`, never silently assigned.

Usage:
  python3 orchestration/scripts/migrate_ff_selection_literature.py \
      [--source docs/ff_selection_literature.json] \
      [--output docs/protocol_evidence_ff.json] \
      [--report-path docs/protocol_evidence_ff_migration_report.json] \
      [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hw_common import load_rules  # noqa: E402
import protocol_evidence_store as pes  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_SOURCE = os.path.join(REPO, "docs", "ff_selection_literature.json")
DEFAULT_OUTPUT = os.path.join(REPO, "docs", "protocol_evidence_ff.json")
DEFAULT_REPORT = os.path.join(REPO, "docs", "protocol_evidence_ff_migration_report.json")

_TOP_LEVEL_SKIP = {
    "scope", "generated_at", "sub_questions", "selection_criteria_extracted",
    "contradictions_with_our_measurements", "overall_confidence",
}

# The legacy file consistently delimits a descriptive/negation qualifier with " -- ",
# e.g. "4,4'BPADA+DDS -- all aromatic polyetherimides; PMDA-ODA/Kapton NOT studied".
# Matching against the qualifier text would produce false-positive class assignments
# (that example is explicitly NOT about PMDA-ODA/Kapton) — so only the text before the
# first " -- " is used as the matchable "core name".
_QUALIFIER_SPLIT = re.compile(r"\s+--\s+")


def _iter_sections(doc: dict):
    """Yield (section_key, section_dict) for every findings-bearing section: both
    sub_questions.<key> entries and top-level numbered sections."""
    for key, section in doc.get("sub_questions", {}).items():
        yield key, section
    for key, section in doc.items():
        if key in _TOP_LEVEL_SKIP or key == "sub_questions":
            continue
        if isinstance(section, dict) and "findings" in section:
            yield key, section


def _core_name(raw_name: str) -> str:
    return _QUALIFIER_SPLIT.split(raw_name, maxsplit=1)[0].strip()


def _normalize(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def _build_class_lookup(rules: dict) -> dict:
    """normalized name -> polymer_class, built from every class's `examples` list and
    `member_smiles` keys. A name that normalizes to a collision between two different
    classes is dropped from the lookup entirely (ambiguous exact names must not be
    guessed either) — checked via a sentinel."""
    lookup: dict[str, str | None] = {}
    for cls_name, cls in rules.get("classes", {}).items():
        names = list(cls.get("examples") or [])
        member_smiles = cls.get("member_smiles")
        if isinstance(member_smiles, dict):
            names.extend(k for k in member_smiles if k != "note")
        for name in names:
            norm = _normalize(name)
            if not norm:
                continue
            if norm in lookup and lookup[norm] != cls_name:
                lookup[norm] = None  # ambiguous — collides across classes
            else:
                lookup[norm] = cls_name
    return lookup


def _match_class(raw_polymer_names: list[str], lookup: dict):
    """Try to resolve a finding's free-text polymer names to a single polymer_class via
    exact normalized-name match against `examples`/`member_smiles`.

    Returns (polymer_class_or_None, class_source, unmapped_names). class_source is
    "examples_or_member_table" on a hit, else None (the caller tries the section-key-hint
    fallback itself when this returns None)."""
    unmapped = []
    for raw in raw_polymer_names:
        core = _core_name(raw)
        norm = _normalize(core)
        cls = lookup.get(norm)
        if cls:
            return cls, "examples_or_member_table", unmapped
        unmapped.append(raw)
    return None, None, unmapped


def _known_classes(rules: dict) -> set[str]:
    return set(rules.get("classes", {}).keys())


def migrate(source_path: str, rules: dict) -> tuple[dict, dict]:
    """Returns (new_store, report)."""
    with open(source_path) as f:
        doc = json.load(f)

    lookup = _build_class_lookup(rules)
    known_classes = _known_classes(rules)

    records = []
    report = {
        "source": source_path,
        "sections_processed": 0,
        "findings_processed": 0,
        "records_emitted": 0,
        "class_source_counts": {"examples_or_member_table": 0, "section_key_hint": 0, "unmapped": 0},
        "unmapped_findings": [],  # {section, doi, polymers}
        "section_key_hint_findings": [],  # {section, doi, polymer_class}
        "trust_tier_heuristic": "doi_verified True -> peer_reviewed_doi; else -> preprint "
                                 "(legacy file has no trust-tier field; this is a coarse "
                                 "default, reviewable per-record via the report)",
    }

    for section_key, section in _iter_sections(doc):
        report["sections_processed"] += 1
        for finding in section.get("findings", []):
            report["findings_processed"] += 1
            raw_names = finding.get("polymers") or []
            polymer_class, class_source, _ = _match_class(raw_names, lookup)

            if polymer_class is None:
                # Section-key hint fallback, only tried here (after per-name matching
                # found nothing at all).
                m = re.match(r"^\d+_([a-z]+)_", section_key)
                hinted = m.group(1).upper() if m else None
                if hinted and hinted in known_classes:
                    polymer_class, class_source = hinted, "section_key_hint"
                    report["section_key_hint_findings"].append({
                        "section": section_key, "doi": finding.get("doi"),
                        "polymer_class": polymer_class,
                    })

            if polymer_class is None:
                report["unmapped_findings"].append({
                    "section": section_key, "doi": finding.get("doi"),
                    "polymers": raw_names,
                })

            report["class_source_counts"][class_source or "unmapped"] = (
                report["class_source_counts"].get(class_source or "unmapped", 0) + 1
            )

            polymer_smiles = []
            if polymer_class:
                cls = rules["classes"].get(polymer_class, {})
                member_smiles = cls.get("member_smiles")
                if isinstance(member_smiles, dict):
                    for raw in raw_names:
                        norm_core = _normalize(_core_name(raw))
                        for member, variants in member_smiles.items():
                            if member == "note" or not isinstance(variants, list):
                                continue
                            if _normalize(member) == norm_core:
                                polymer_smiles.extend(variants)

            doi_verified = bool(finding.get("doi_verified"))
            trust_tier = "peer_reviewed_doi" if doi_verified else "preprint"

            record = pes.build_record(
                field="forcefield",
                polymer_class=polymer_class,
                polymer_names=raw_names,
                smiles=polymer_smiles,
                claim=finding.get("claim", ""),
                value={
                    "fields_compared": finding.get("fields", []),
                    "reported_errors": finding.get("reported_errors"),
                },
                doi=finding.get("doi"),
                title=finding.get("title"),
                year=finding.get("year"),
                doi_verified=doi_verified,
                trust_tier=trust_tier,
                relevance=finding.get("relevance"),
                provenance={
                    "origin": "migration",
                    "source_run": None,
                    "migrated_from": f"docs/ff_selection_literature.json#{section_key}"
                                      f".findings[{section['findings'].index(finding)}]",
                    "added_at": None,  # stamped by save_store's generated_at at file level
                },
            )
            errors = pes.validate_record(record)
            if errors:
                report.setdefault("validation_rejected", []).append({
                    "section": section_key, "doi": finding.get("doi"), "errors": errors,
                })
                continue
            records.append(record)

    # Deterministic order: polymer_class (None last), year desc, record_id asc.
    records.sort(key=lambda r: (
        r["polymer_class"] is None, r["polymer_class"] or "",
        -(r["year"] or 0), r["record_id"],
    ))

    store = pes.empty_store(with_methodology=True)
    store["records"] = records
    store["methodology_criteria"] = doc.get("selection_criteria_extracted", [])
    report["records_emitted"] = len(records)
    return store, report


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--source", default=DEFAULT_SOURCE)
    p.add_argument("--output", default=DEFAULT_OUTPUT)
    p.add_argument("--report-path", default=DEFAULT_REPORT)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    rules = load_rules()
    store, report = migrate(args.source, rules)

    if args.dry_run:
        print(json.dumps({"dry_run": True, "report": report}, indent=2))
        return

    pes.save_store(args.output, store)
    with open(args.report_path, "w") as f:
        json.dump(report, f, indent=2)
        f.write("\n")
    print(json.dumps({"output": args.output, "report_path": args.report_path, "report": report}, indent=2))


if __name__ == "__main__":
    main()
