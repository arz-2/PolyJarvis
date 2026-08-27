#!/usr/bin/env python3
"""
ingest_protocol_evidence.py — write-back a worker's advisory JSON into the persistent
protocol evidence store.

This is the ONLY writer of docs/protocol_evidence_ff.json / protocol_evidence_system_size.json
besides the one-time migrate_ff_selection_literature.py migration. ff-protocol-literature-worker
and system-size-literature-worker call this as their last step (via Bash) rather than
writing to the store directly — code, not the LLM subagent, owns the store's provenance
(CLAUDE.md), and this also sidesteps the two-workers-run-in-parallel race since each
worker only ever writes its own per-run advisory JSON plus calls this script against its
own store.

Only `verified: true` sources are ingested — an unverified candidate in the advisory JSON
is silently skipped (it was already excluded from backing any recommendation by the
worker itself; this script just declines to persist it). Idempotent: re-ingesting the
same advisory JSON adds nothing new the second time (dedup is on protocol_evidence_store's
content-hash record_id).

A source folded into the advisory JSON directly from a query_protocol_evidence.py store
hit (query_protocol_evidence.py's own instructions tell the worker to skip a field's
fresh search on a strong hit and fold that hit in) must carry `"origin_record_id":
"<the hit's record_id>"` — this script skips ingesting any such source entirely, since
the record already exists in the store under that id. Without this marker, a worker
paraphrasing the claim to note "found via the store" would content-hash to a NEW
record_id (the claim text differs from the original) and silently duplicate an existing
finding every time a future run hits the same store record and re-ingests it.

Usage:
  python3 orchestration/scripts/ingest_protocol_evidence.py \
      --store ff|system_size \
      --from data/<run>/raw/literature_grounding_ff_protocol.json \
      --run-name <run_name> \
      [--dry-run]
Prints JSON: {"records_added": N, "records_skipped_duplicate": N,
              "records_skipped_store_origin": N,
              "records_rejected": [{"reason": "...", "field": "...", "doi": "..."}],
              "store_path": "..."}
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import protocol_evidence_store as pes  # noqa: E402
from canon_smiles import canonicalize  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STORE_PATHS = {
    "ff": os.path.join(REPO, "docs", "protocol_evidence_ff.json"),
    "system_size": os.path.join(REPO, "docs", "protocol_evidence_system_size.json"),
}

# advisory-JSON field name -> value keys to lift into the record's `value` dict.
_FF_FIELD_VALUE_KEYS = {
    "forcefield": ("recommendation",),
    "electrostatics": ("recommendation",),
    "cooling_rate_K_per_ns": ("rates",),
    "density_target_gcm3": ("range", "T_K"),
    "tg_target_K": ("range",),
    "cte_glass_melt": ("alpha_glass_per_K", "alpha_melt_per_K"),
}
# advisory JSON key -> store `field` enum value (differs for a couple of keys).
_FF_FIELD_NAME_MAP = {
    "forcefield": "forcefield",
    "electrostatics": "electrostatics",
    "cooling_rate_K_per_ns": "cooling_rate",
    "density_target_gcm3": "density_target",
    "tg_target_K": "tg_target",
    "cte_glass_melt": "cte_glass_melt",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _canon_smiles_list(smiles: str | None) -> list[str]:
    """Canonicalize once at ingest time (isomeric=False, matching hw_common's existing
    member_smiles convention) so query_protocol_evidence.py's exact_smiles tier can do a
    plain string comparison instead of re-canonicalizing every stored record's smiles on
    every query — the store is written far less often than it's read. Falls back to the
    raw SMILES on a canonicalization failure (RDKit/conda unavailable, bad SMILES) rather
    than dropping it, since an uncanonicalized entry degrades to a possible exact_smiles
    miss, not silent data loss."""
    if not smiles:
        return []
    try:
        return [canonicalize(smiles, isomeric=False)]
    except (RuntimeError, subprocess.TimeoutExpired):
        return [smiles]


def _records_from_ff_advisory(advisory: dict, run_name: str) -> tuple[list[dict], list[str]]:
    """Returns (records_to_ingest, skipped_store_origin_record_ids)."""
    polymer_class = advisory.get("polymer_class")
    if polymer_class in (None, "UNKNOWN", "offtable"):
        polymer_class = None
    polymer_names = [advisory["polymer_name"]] if advisory.get("polymer_name") else []
    smiles = _canon_smiles_list(advisory.get("smiles"))

    records = []
    store_origin_ids = []
    for advisory_key, store_field in _FF_FIELD_NAME_MAP.items():
        block = advisory.get(advisory_key)
        if not isinstance(block, dict):
            continue
        for source in block.get("sources", []):
            if source.get("verified") is not True:
                continue
            if source.get("origin_record_id"):
                # Folded in from a query_protocol_evidence.py store hit rather than found
                # by fresh search this run -- the record already exists (that's what
                # origin_record_id points at). Re-ingesting it, even reworded to note the
                # store origin, would content-hash to a NEW record_id (the claim text
                # differs) and silently duplicate an existing finding.
                store_origin_ids.append(source["origin_record_id"])
                continue
            value = {k: block.get(k) for k in _FF_FIELD_VALUE_KEYS[advisory_key] if k in block}
            record = pes.build_record(
                field=store_field,
                polymer_class=polymer_class,
                polymer_names=polymer_names,
                smiles=smiles,
                claim=source.get("claim", ""),
                value=value,
                doi=source.get("doi"),
                url=source.get("url"),
                title=source.get("title"),
                year=source.get("year"),
                doi_verified=True,
                trust_tier=source.get("trust_tier", "preprint"),
                relevance=None,
                provenance={
                    "origin": "worker_run",
                    "source_run": run_name,
                    "migrated_from": None,
                    "added_at": _now_iso(),
                },
            )
            records.append(record)
    return records, store_origin_ids


def _records_from_system_size_advisory(advisory: dict, run_name: str) -> tuple[list[dict], list[str]]:
    """Returns (records_to_ingest, skipped_store_origin_record_ids)."""
    polymer_class = advisory.get("polymer_class")
    if polymer_class in (None, "UNKNOWN", "offtable"):
        polymer_class = None
    polymer_names = [advisory["polymer_name"]] if advisory.get("polymer_name") else []
    smiles = _canon_smiles_list(advisory.get("smiles"))

    system_size = advisory.get("system_size")
    if not isinstance(system_size, dict):
        return [], []

    records = []
    store_origin_ids = []
    for source in system_size.get("sources", []):
        if source.get("verified") is not True:
            continue
        if source.get("origin_record_id"):
            store_origin_ids.append(source["origin_record_id"])
            continue
        value = {
            "dp_typical": system_size.get("dp_typical"),
            "nchain": system_size.get("nchain"),
            "convergence_basis": system_size.get("convergence_basis"),
            "me_estimated_gmol": system_size.get("me_estimated_gmol"),
            "me_estimation_note": system_size.get("me_estimation_note"),
            "kuhn_length_A": system_size.get("kuhn_length_A"),
            "kuhn_molar_mass_gmol": system_size.get("kuhn_molar_mass_gmol"),
            "kuhn_source_note": system_size.get("kuhn_source_note"),
        }
        record = pes.build_record(
            field="system_size",
            polymer_class=polymer_class,
            polymer_names=polymer_names,
            smiles=smiles,
            claim=source.get("claim", ""),
            value=value,
            doi=source.get("doi"),
            url=source.get("url"),
            title=source.get("title"),
            year=source.get("year"),
            doi_verified=True,
            trust_tier=source.get("trust_tier", "preprint"),
            relevance=None,
            provenance={
                "origin": "worker_run",
                "source_run": run_name,
                "migrated_from": None,
                "added_at": _now_iso(),
            },
        )
        records.append(record)
    return records, store_origin_ids


def ingest(store_kind: str, advisory: dict, run_name: str, store_path: str,
           dry_run: bool = False) -> dict:
    if store_kind == "ff":
        new_records, store_origin_ids = _records_from_ff_advisory(advisory, run_name)
        with_methodology = True
    else:
        new_records, store_origin_ids = _records_from_system_size_advisory(advisory, run_name)
        with_methodology = False

    accepted, rejected = [], []
    for r in new_records:
        errors = pes.validate_record(r)
        if errors:
            rejected.append({"reason": "; ".join(errors), "field": r.get("field"), "doi": r.get("doi")})
        else:
            accepted.append(r)

    # Holding the lock across load+merge+save (not just save) is what actually prevents
    # the race: two concurrent ingests must not both load the pre-update store and then
    # each save their own merge, silently dropping whichever wrote second.
    with pes.locked_store(store_path):
        store = pes.load_store(store_path, with_methodology=with_methodology)
        merged, skipped_ids = pes.dedupe(store["records"], accepted)
        added = len(accepted) - len(skipped_ids)

        if not dry_run and (added or store.get("records") != merged):
            store["records"] = merged
            pes.save_store(store_path, store)

    return {
        "records_added": added,
        "records_skipped_duplicate": len(skipped_ids),
        "records_skipped_store_origin": len(store_origin_ids),
        "records_rejected": rejected,
        "store_path": store_path,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--store", choices=["ff", "system_size"], required=True)
    p.add_argument("--from", dest="from_path", required=True)
    p.add_argument("--run-name", required=True)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    try:
        with open(args.from_path) as f:
            advisory = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(json.dumps({"error": f"failed to read {args.from_path}: {e}"}))
        sys.exit(0)

    result = ingest(args.store, advisory, args.run_name, STORE_PATHS[args.store],
                     dry_run=args.dry_run)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
