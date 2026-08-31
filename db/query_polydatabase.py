#!/usr/bin/env python3
"""
Query db/polydatabase_md.sqlite for candidate DOIs from the PolyDatabase MD-simulation-
literature index — a fast local pre-filter for the literature-grounding-worker subagent,
run *before* its open WebSearch fan-out.

This is a lead-finder, not a grading source (contrast db/query_best_match.py, which ranks
and returns real experimental measurements): it returns candidate DOIs plus the force field
and properties each one reports, grouped so a worker gets a short list, not raw rows. Every
candidate still requires the worker's own WebFetch-verify-DOI step before being cited —
a PolyDatabase hit carries no trust_tier of its own.

Matching priority (mirrors db/query_best_match.py, reusing its name-matching helpers):
  1. --polymer_name  → exact/LIKE against polymer_name, abbreviation, common_trade_name,
                        source_monomer (plus Poly(X)/PolyX variants)      → match_confidence=high
  2. --polymer_class → CLASS_CANONICAL_PATTERN fallback against polymer_name  → match_confidence=medium
  3. no match        → prints {match_method: "none", candidates: []} and exits 0
  4. db not yet built (db/polydatabase_md.sqlite missing) → prints {error: "not_ingested", ...}
     and exits 0 — never blocks the caller; the worker falls straight through to WebSearch.

Usage:
  python3 db/query_polydatabase.py --polymer-name "Poly(methyl methacrylate)" --polymer-class PACR
  python3 db/query_polydatabase.py --polymer-name PE --force-field OPLS --output-path out.json

Limitations (known gaps, same root cause as query_best_match.py):
  - No SMILES in the dataset — matching is name-based only.
  - LLM-mined, not exhaustive: 1,095 records / 198 DOIs (1995-2025) as of the source
    dataset's Zenodo snapshot. Absence of a hit means nothing beyond "not in this snapshot".
"""

import argparse
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db.query_best_match import CLASS_CANONICAL_PATTERN, _name_variants, _normalize_loose  # noqa: E402

DB_PATH = os.path.join(os.path.dirname(__file__), "polydatabase_md.sqlite")

_MAX_CANDIDATES = 15


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _match_rows_by_name(conn: sqlite3.Connection, polymer_name: str) -> list[sqlite3.Row]:
    seen_ids: set[int] = set()
    rows: list[sqlite3.Row] = []

    for variant in _name_variants(polymer_name):
        found = conn.execute(
            """SELECT * FROM md_records
               WHERE polymer_name = ? COLLATE NOCASE
                  OR abbreviation = ? COLLATE NOCASE
                  OR common_trade_name LIKE ? COLLATE NOCASE
                  OR source_monomer = ? COLLATE NOCASE""",
            (variant, variant, f"%{variant}%", variant),
        ).fetchall()
        if not found:
            found = conn.execute(
                """SELECT * FROM md_records
                   WHERE polymer_name LIKE ? COLLATE NOCASE
                      OR abbreviation LIKE ? COLLATE NOCASE""",
                (f"%{variant}%", f"%{variant}%"),
            ).fetchall()
        for r in found:
            if r["id"] not in seen_ids:
                seen_ids.add(r["id"])
                rows.append(r)

    if rows:
        return rows

    # Loose-normalized pass — catches spacing/punctuation-only splits.
    target = _normalize_loose(polymer_name)
    for r in conn.execute("SELECT * FROM md_records").fetchall():
        candidates = (r["polymer_name"], r["abbreviation"] or "")
        if any(_normalize_loose(c) == target for c in candidates) and r["id"] not in seen_ids:
            seen_ids.add(r["id"])
            rows.append(r)

    return rows


def _match_rows_by_class(conn: sqlite3.Connection, polymer_class: str) -> list[sqlite3.Row]:
    if polymer_class not in CLASS_CANONICAL_PATTERN:
        return []
    seen_ids: set[int] = set()
    rows: list[sqlite3.Row] = []
    for canonical in CLASS_CANONICAL_PATTERN[polymer_class]:
        for variant in _name_variants(canonical):
            found = conn.execute(
                "SELECT * FROM md_records WHERE polymer_name LIKE ? COLLATE NOCASE",
                (f"%{variant}%",),
            ).fetchall()
            for r in found:
                if r["id"] not in seen_ids:
                    seen_ids.add(r["id"])
                    rows.append(r)
        if rows:
            break
    return rows


def find_candidates(
    conn: sqlite3.Connection,
    polymer_name: str | None,
    polymer_class: str | None,
    force_field: str | None,
) -> tuple[list[dict], str, str]:
    """Returns (candidates, match_method, match_confidence)."""
    rows: list[sqlite3.Row] = []
    match_method = "none"
    match_confidence = "none"

    if polymer_name:
        rows = _match_rows_by_name(conn, polymer_name)
        if rows:
            match_method, match_confidence = "name_match", "high"

    if not rows and polymer_class:
        rows = _match_rows_by_class(conn, polymer_class)
        if rows:
            match_method, match_confidence = "class_representative", "medium"

    if force_field:
        rows = [r for r in rows if r["force_field"] and force_field.lower() in r["force_field"].lower()]

    # Group by (doi, force_field) so a worker gets one entry per candidate paper/FF pair.
    grouped: dict[tuple[str, str], dict] = {}
    for r in rows:
        doi = r["doi"] or "unknown"
        ff = r["force_field"] or "unknown"
        key = (doi, ff)
        if key not in grouped:
            grouped[key] = {
                "doi": r["doi"],
                "polymer_name_matched": r["polymer_name"],
                "force_field": r["force_field"],
                "force_field_type": r["force_field_type"],
                "properties": [],
                "extra_info": r["extra_info"],
                "source_type": "polydatabase_llm_mined",
            }
        grouped[key]["properties"].append(
            {"property": r["property"], "value": r["value"], "unit": r["unit"]}
        )

    candidates = sorted(grouped.values(), key=lambda c: len(c["properties"]), reverse=True)
    return candidates[:_MAX_CANDIDATES], match_method, match_confidence


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Query the local PolyDatabase MD-literature index for candidate DOIs"
    )
    parser.add_argument("--polymer-name", default=None)
    parser.add_argument("--polymer-class", default=None, help="PolyJarvis class code (fallback)")
    parser.add_argument("--force-field", default=None, help="Filter candidates to this force field (substring match)")
    parser.add_argument("--output-path", default=None, help="Write JSON here instead of stdout")
    args = parser.parse_args()

    if not os.path.exists(DB_PATH):
        result = {
            "error": "not_ingested",
            "match_method": "none",
            "match_confidence": "none",
            "candidates": [],
        }
    else:
        conn = _connect()
        candidates, match_method, match_confidence = find_candidates(
            conn, args.polymer_name, args.polymer_class, args.force_field
        )
        result = {
            "match_method": match_method,
            "match_confidence": match_confidence,
            "candidates": candidates,
        }

    output = json.dumps(result, indent=2, default=str)
    if args.output_path:
        with open(args.output_path, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"Wrote {len(result['candidates'])} candidates ({result['match_method']}) to {args.output_path}")
    else:
        print(output)


if __name__ == "__main__":
    main()
