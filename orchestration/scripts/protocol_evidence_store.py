#!/usr/bin/env python3
"""
protocol_evidence_store.py — shared schema + file I/O for the protocol evidence stores.

Single source of truth for the ProtocolEvidenceRecord shape and store file I/O, imported
by migrate_ff_selection_literature.py, query_protocol_evidence.py, and
ingest_protocol_evidence.py so the three scripts can't drift on record shape. stdlib only.

Two store files exist, same record shape, different `field` values populated:
  docs/protocol_evidence_ff.json          — forcefield, electrostatics, cooling_rate,
                                             density_target, tg_target, cte_glass_melt
  docs/protocol_evidence_system_size.json — system_size

Both stores hold ONLY already-verified findings (doi_verified: true) — they are a cache
of verified evidence, not a scratchpad of candidates. An unverified source never enters
either store; it stays in a run's own advisory JSON only. "Verified" has two forms:
literature evidence is DOI-verified by the literature workers; internal-run evidence
(ingest_internal_run_evidence.py, trust_tier "internal_validated_run") is verified by
that run's own binding gate actually passing — doi_verified stays True for both, the
verification method differs.
"""
from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import re
from datetime import datetime, timezone

FIELDS = (
    "forcefield", "electrostatics", "cooling_rate", "density_target",
    "tg_target", "cte_glass_melt", "system_size",
)
# internal_validated_run ranks above peer_reviewed_doi: a finding this exact pipeline
# reproduced end-to-end under its own gates is stronger evidence for future planning here
# than a cited external study run under different conditions.
TRUST_TIERS = ("internal_validated_run", "peer_reviewed_doi", "preprint", "vendor", "educational")
TRUST_TIER_RANK = {t: i for i, t in enumerate(TRUST_TIERS)}
SCHEMA_VERSION = 1
_DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def make_record_id(doi: str, field: str, claim: str) -> str:
    """Stable 12-hex id for a record, used for dedup. Same (doi, field, claim) triple
    always yields the same id, so re-ingesting/re-migrating the same finding is a no-op
    rather than a duplicate."""
    key = f"{doi or ''}|{field or ''}|{claim or ''}".encode("utf-8")
    return hashlib.sha1(key).hexdigest()[:12]


def empty_store(with_methodology: bool = False) -> dict:
    store = {"schema_version": SCHEMA_VERSION, "generated_at": None, "records": []}
    if with_methodology:
        store["methodology_criteria"] = []
    return store


def load_store(path: str, with_methodology: bool = False) -> dict:
    """Parse a store file. A missing file scaffolds an empty store rather than raising —
    retrieval/ingest must never hard-fail just because a store hasn't been created yet."""
    if not os.path.exists(path):
        return empty_store(with_methodology)
    with open(path) as f:
        store = json.load(f)
    store.setdefault("schema_version", SCHEMA_VERSION)
    store.setdefault("records", [])
    if with_methodology:
        store.setdefault("methodology_criteria", [])
    return store


@contextlib.contextmanager
def locked_store(path: str):
    """Exclusive file lock (fcntl.flock) held for the duration of a load-modify-save
    cycle on `path`, so two concurrent sessions (e.g. two novel-run-plan invocations
    ingesting findings at the same time) can't silently clobber each other's write — the
    second session blocks until the first's save_store completes, rather than both
    load()ing the pre-update store and one's merge overwriting the other's on save().
    The lock file is a sibling `<path>.lock`, never deleted (that would reintroduce a
    race on recreation) — only ever opened, locked, and released."""
    lock_path = f"{path}.lock"
    os.makedirs(os.path.dirname(lock_path) or ".", exist_ok=True)
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def save_store(path: str, store: dict) -> None:
    """Atomic write: write to a sibling temp file, then os.replace over the target, so a
    crash mid-write never leaves a truncated/corrupt store file."""
    store = dict(store)
    store["generated_at"] = _now_iso()
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w") as f:
        json.dump(store, f, indent=2, sort_keys=False)
        f.write("\n")
    os.replace(tmp_path, path)


def validate_record(record: dict) -> list[str]:
    """Return a list of schema-violation strings; empty list means valid. The store only
    ever holds verified findings, so doi_verified must be literally True."""
    errors = []
    if not record.get("doi"):
        errors.append("missing 'doi'")
    if not record.get("claim"):
        errors.append("missing 'claim'")
    if record.get("doi_verified") is not True:
        errors.append("doi_verified is not True — unverified findings must not enter the store")
    field = record.get("field")
    if field not in FIELDS:
        errors.append(f"field '{field}' not one of {FIELDS}")
    trust_tier = record.get("trust_tier")
    if trust_tier not in TRUST_TIERS:
        errors.append(f"trust_tier '{trust_tier}' not one of {TRUST_TIERS}")
    if not isinstance(record.get("value"), dict):
        errors.append("missing/non-dict 'value'")
    if not isinstance(record.get("record_id"), str) or not record["record_id"]:
        errors.append("missing 'record_id'")
    return errors


def dedupe(existing_records: list[dict], new_records: list[dict]) -> tuple[list[dict], list[str]]:
    """Merge new_records into existing_records, first-write-wins on record_id.

    Returns (merged_records, skipped_ids) where skipped_ids are new_records' ids that
    were already present in existing_records (so the caller can report them as
    duplicates rather than silently dropping them)."""
    seen = {r["record_id"] for r in existing_records if r.get("record_id")}
    merged = list(existing_records)
    skipped = []
    for r in new_records:
        rid = r.get("record_id")
        if rid in seen:
            skipped.append(rid)
            continue
        merged.append(r)
        seen.add(rid)
    return merged, skipped


def build_record(*, field: str, polymer_class, polymer_names, smiles, claim, value,
                  doi, url=None, title=None, year=None, doi_verified, trust_tier,
                  relevance=None, provenance: dict) -> dict:
    """Construct a well-formed ProtocolEvidenceRecord dict (does not validate — call
    validate_record on the result if the caller needs to check it)."""
    return {
        "schema_version": SCHEMA_VERSION,
        "record_id": make_record_id(doi, field, claim),
        "field": field,
        "polymer_class": polymer_class,
        "polymer_names": list(polymer_names or []),
        "smiles": list(smiles or []),
        "claim": claim,
        "value": value or {},
        "doi": doi,
        "url": url or (f"https://doi.org/{doi}" if doi and _DOI_RE.match(doi) else None),
        "title": title,
        "year": year,
        "doi_verified": doi_verified,
        "trust_tier": trust_tier,
        "relevance": relevance,
        "provenance": provenance,
    }
