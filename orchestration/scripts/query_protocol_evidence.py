#!/usr/bin/env python3
"""
query_protocol_evidence.py — deterministic retrieval over the protocol evidence stores.

Replaces "the literature-grounding-worker reads the whole legacy JSON file and reasons
over it" with a real query. Always exits 0; errors surface as {"error": ...} in the JSON
payload printed to stdout (same convention as select_forcefield.py/select_system_size.py)
so callers parse JSON, never a traceback.

Tier order (highest priority first), computed non-exclusively — a query can produce hits
in more than one tier, all returned together, tier-ordered:
  exact_smiles   — the query SMILES (canonicalized, isomeric=False) appears in a record's
                   own `smiles[]` list (stored already-canonicalized at write time).
  exact_class    — record's polymer_class matches --polymer-class (no SMILES hit).
  similar_class  — record's polymer_class belongs to some OTHER class whose member_smiles
                   scores >= --similarity-threshold against the query SMILES via
                   chem_similarity.compute_similarities (one batched call, not one per
                   class).

Within a tier, records are sorted by trust_tier rank (internal_validated_run first, then
peer_reviewed_doi — see protocol_evidence_store.TRUST_TIERS), then year
descending, then doi ascending — fully deterministic, no tie resolved by file order.

Usage:
  python3 orchestration/scripts/query_protocol_evidence.py \
      --store ff|system_size \
      [--polymer-class CLASS] [--smiles '<repeat-unit SMILES>'] \
      [--field forcefield|electrostatics|cooling_rate|density_target|tg_target|cte_glass_melt|system_size] \
      [--methodology-only] [--top-k 5] [--similarity-threshold 0.4] [--no-chem-similarity]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import chem_similarity  # noqa: E402
import protocol_evidence_store as pes  # noqa: E402
from canon_smiles import canonicalize  # noqa: E402
from hw_common import load_rules  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STORE_PATHS = {
    "ff": os.path.join(REPO, "docs", "protocol_evidence_ff.json"),
    "system_size": os.path.join(REPO, "docs", "protocol_evidence_system_size.json"),
}


def _canon(smiles: str | None):
    if not smiles:
        return None
    try:
        return canonicalize(smiles, isomeric=False)
    except (RuntimeError, subprocess.TimeoutExpired):
        return None


def _sort_key(hit: dict):
    r = hit["record"]
    tier_rank = {"exact_smiles": 0, "exact_class": 1, "similar_class": 2}[hit["tier"]]
    trust_rank = pes.TRUST_TIER_RANK.get(r.get("trust_tier"), len(pes.TRUST_TIERS))
    return (tier_rank, trust_rank, -(r.get("year") or 0), r.get("doi") or "")


def _class_member_smiles(rules: dict, exclude_class: str | None) -> dict:
    """{smiles: polymer_class} across every class's member_smiles table, excluding
    exclude_class (the query's own class, if known — we only want OTHER classes for the
    similar_class tier)."""
    out = {}
    for cls_name, cls in rules.get("classes", {}).items():
        if cls_name == exclude_class:
            continue
        member_smiles = cls.get("member_smiles")
        if not isinstance(member_smiles, dict):
            continue
        for member, variants in member_smiles.items():
            if member == "note" or not isinstance(variants, list):
                continue
            for smi in variants:
                out[smi] = cls_name
    return out


def query(store: dict, *, polymer_class: str | None, smiles: str | None, field: str | None,
          rules: dict, similarity_threshold: float, use_chem_similarity: bool,
          top_k: int | None, sim_env: str = "radonpy") -> dict:
    records = store.get("records", [])
    if field:
        records = [r for r in records if r.get("field") == field]

    canon_query = _canon(smiles) if smiles else None
    hits = []
    matched_ids = set()

    if canon_query:
        # Stored smiles[] are canonicalized once at write time (ingest_protocol_evidence.py /
        # migrate_ff_selection_literature.py, both isomeric=False, matching hw_common's
        # member_smiles convention) — a plain string comparison here, not a re-canonicalize
        # per record, is what keeps this query fast as the store grows.
        for r in records:
            if canon_query in r.get("smiles", []):
                hits.append({"tier": "exact_smiles", "similarity": 1.0, "record": r})
                matched_ids.add(r["record_id"])

    if polymer_class:
        for r in records:
            if r["record_id"] in matched_ids:
                continue
            if r.get("polymer_class") == polymer_class:
                hits.append({"tier": "exact_class", "similarity": None, "record": r})
                matched_ids.add(r["record_id"])

    similarity_errors = []
    if canon_query and use_chem_similarity:
        candidate_map = _class_member_smiles(rules, exclude_class=polymer_class)
        if candidate_map:
            try:
                result = chem_similarity.compute_similarities(
                    canon_query, list(candidate_map.keys()), env=sim_env)
                scores = result.get("scores", {})
                similarity_errors = result.get("errors", [])
            except (RuntimeError, subprocess.TimeoutExpired) as e:
                scores = {}
                similarity_errors = [str(e)]

            best_score_by_class: dict[str, float] = {}
            for cand_smi, score in scores.items():
                if score < similarity_threshold:
                    continue
                cand_class = candidate_map[cand_smi]
                if score > best_score_by_class.get(cand_class, -1.0):
                    best_score_by_class[cand_class] = score

            for r in records:
                if r["record_id"] in matched_ids:
                    continue
                r_class = r.get("polymer_class")
                if r_class in best_score_by_class:
                    hits.append({"tier": "similar_class",
                                 "similarity": best_score_by_class[r_class], "record": r})
                    matched_ids.add(r["record_id"])

    hits.sort(key=_sort_key)
    if top_k:
        hits = hits[:top_k]

    return {"hits": hits, "similarity_errors": similarity_errors}


def main():
    p = argparse.ArgumentParser(description="Query the protocol evidence store.")
    p.add_argument("--store", choices=["ff", "system_size"], required=True)
    p.add_argument("--polymer-class")
    p.add_argument("--smiles")
    p.add_argument("--field", choices=pes.FIELDS)
    p.add_argument("--methodology-only", action="store_true")
    p.add_argument("--top-k", type=int)
    p.add_argument("--similarity-threshold", type=float, default=0.4)
    p.add_argument("--no-chem-similarity", action="store_true")
    p.add_argument("--sim-env", default="radonpy")
    args = p.parse_args()

    store_path = STORE_PATHS[args.store]
    with_methodology = args.store == "ff"
    query_desc = {"store": args.store, "polymer_class": args.polymer_class,
                  "smiles": args.smiles, "field": args.field}

    try:
        store = pes.load_store(store_path, with_methodology=with_methodology)
    except (OSError, json.JSONDecodeError) as e:
        print(json.dumps({"error": f"failed to load store: {e}", "query": query_desc}))
        sys.exit(0)

    if args.methodology_only:
        print(json.dumps({
            "query": query_desc,
            "methodology_criteria": store.get("methodology_criteria", []),
        }, indent=2))
        return

    if not args.polymer_class and not args.smiles:
        print(json.dumps({
            "query": query_desc, "hits": [], "similarity_errors": [],
            "note": "no --polymer-class or --smiles given; nothing to query on",
        }, indent=2))
        return

    try:
        rules = load_rules()
    except (OSError, json.JSONDecodeError) as e:
        print(json.dumps({"error": f"failed to load polymer_rules.json: {e}", "query": query_desc}))
        sys.exit(0)

    result = query(
        store, polymer_class=args.polymer_class, smiles=args.smiles, field=args.field,
        rules=rules, similarity_threshold=args.similarity_threshold,
        use_chem_similarity=not args.no_chem_similarity, top_k=args.top_k,
        sim_env=args.sim_env,
    )
    output = {"query": query_desc, **result}
    if args.store == "ff":
        output["methodology_criteria"] = store.get("methodology_criteria", [])
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
