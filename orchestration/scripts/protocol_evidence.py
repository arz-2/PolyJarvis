#!/usr/bin/env python3
"""
protocol_evidence.py — the protocol evidence stores: schema, both ingest paths, and retrieval.

One store format, two ways in, one way out. Until 2026-09-02 that was five files
(protocol_evidence_store.py, ingest_protocol_evidence.py, ingest_internal_run_evidence.py,
query_protocol_evidence.py, chem_similarity.py) whose only external consumers were this
cluster itself, run_campaign.py's post-run hook, and the literature-grounding-worker agent --
so answering "what is a record, and who may write one" meant opening four of them, and
_now_iso()/STORE_PATHS were each defined more than once.

Subcommands:
  ingest           fold the literature critic's advisory JSON into the ff store (DOI-verified
                   external sources; the critic writes the advisory, this validates it).
                   --store ff only: the critic stopped emitting a system-size advisory on
                   2026-09-02, so that store is now written by ingest-internal alone.
  ingest-internal  fold a COMPLETED, gate-passing run of this pipeline into the store as
                   internal_validated_run evidence
  query            tiered retrieval: exact_smiles > exact_class > similar_class

Sections below, in dependency order: STORE (schema, record construction, locking) ->
SIMILARITY -> INGEST: LITERATURE -> INGEST: INTERNAL RUNS -> QUERY -> CLI.
"""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rules_common  # noqa: E402  -- module import so tests can monkeypatch rules_common.canonicalize
from rules_common import load_rules  # noqa: E402
from mol_python import run_in_mol_env, RDKIT_CLI  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STORE_PATHS = {
    "ff": os.path.join(REPO, "docs", "protocol_evidence_ff.json"),
    "system_size": os.path.join(REPO, "docs", "protocol_evidence_system_size.json"),
}


# ===========================================================================
# STORE — record schema, trust tiers, locked read/write
#
# protocol_evidence_store.py — shared schema + file I/O for the protocol evidence stores.
#
# Single source of truth for the ProtocolEvidenceRecord shape and store file I/O, imported
# by migrate_ff_selection_literature.py, query_protocol_evidence.py, and
# ingest_protocol_evidence.py so the three scripts can't drift on record shape. stdlib only.
#
# Two store files exist, same record shape, different `field` values populated:
#   docs/protocol_evidence_ff.json          — forcefield, electrostatics, tg_target (plus
#                                              cooling_rate, density_target, cte_glass_melt on
#                                              records written before 2026-09-02: those three
#                                              fields were retired from the critic's schema as
#                                              non-essential to protocol adjustment, so nothing
#                                              writes them any more, but stored records stay
#                                              valid and queryable)
#   docs/protocol_evidence_system_size.json — system_size (ingest-internal only)
#
# Both stores hold ONLY already-verified findings (doi_verified: true) — they are a cache
# of verified evidence, not a scratchpad of candidates. An unverified source never enters
# either store; it stays in a run's own advisory JSON only. "Verified" has two forms:
# literature evidence is DOI-verified by the literature workers; internal-run evidence
# (ingest_internal_run_evidence.py, trust_tier "internal_validated_run") is verified by
# that run's own binding gate actually passing — doi_verified stays True for both, the
# verification method differs.
# ===========================================================================
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


# ===========================================================================
# SIMILARITY — Morgan/Tanimoto, the `similar_class` retrieval tier's admission test
#
# chem_similarity.py — SMILES structural similarity via RDKit Morgan/Tanimoto.
#
# RDKit lives in the `radonpy`/`mol-builder` conda envs, not `base` — same constraint
# rules_common.canonicalize documents. This reaches it via mol_python.run_in_mol_env(), invoking
# rdkit_cli.py's `similarity` subcommand and passing the candidate list through a temp JSON
# file (not argv) so a large batch (e.g. every class's member_smiles at once) never hits
# argv-length limits, and so SMILES stereo markers (forward and back slashes) stay out of
# shell text entirely.
#
# This module's compute_similarities() is the one seam every caller (query_protocol_evidence.py)
# goes through and the one seam tests monkeypatch — same convention already used for
# rules_common.canonicalize (see tests/test_make_deterministic_plan_from_cache.py etc.).
#
# Usage (CLI, for manual/real-env verification):
#   python3 orchestration/scripts/chem_similarity.py --smoke '<smiles1>' '<smiles2>' [...]
# Prints: {"<query>": {"<candidate>": <float 0..1>, ...}, "_errors": [...]}
# ===========================================================================
def compute_similarities(query_smiles: str, candidate_smiles: list[str],
                          env: str = "radonpy", timeout: int = 30,
                          radius: int = 2, n_bits: int = 2048) -> dict:
    """Tanimoto similarity of query_smiles against every candidate, computed in one
    subprocess call. Returns {"scores": {candidate: score, ...}, "errors": [str, ...]}.
    A candidate (or the query) that fails to parse is dropped from `scores` and noted in
    `errors` rather than raising — one bad SMILES in a large batch must not sink the
    whole retrieval call."""
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f_input:
        json.dump({"query": query_smiles, "candidates": list(candidate_smiles),
                    "radius": radius, "n_bits": n_bits}, f_input)
        input_path = f_input.name
    try:
        r = run_in_mol_env(script_path=RDKIT_CLI, args=["similarity", "--input", input_path],
                            env=env, timeout=timeout)
    finally:
        os.unlink(input_path)

    out = r.stdout.strip()
    if r.returncode != 0 or not out:
        raise RuntimeError(r.stderr.strip() or "empty output from RDKit similarity computation")
    return json.loads(out.splitlines()[-1])


# ===========================================================================
# INGEST: LITERATURE ADVISORIES  (`ingest`)
#
# ingest_protocol_evidence.py — write-back a worker's advisory JSON into the persistent
# protocol evidence store.
#
# This is the ONLY writer of docs/protocol_evidence_ff.json besides the one-time
# migrate_ff_selection_literature.py migration. literature-grounding-worker calls it once (via
# Bash) as its last step, rather than writing to the store directly — code, not the LLM subagent,
# owns the store's provenance (CLAUDE.md). `--store ff` is the only advisory path: the critic's
# system-size half was removed 2026-09-02 along with the literature->cell-size fold-in, so
# docs/protocol_evidence_system_size.json is now written exclusively by ingest-internal, from
# completed validated runs. Passing --store system_size here raises rather than quietly adding
# nothing.
#
# Only `verified: true` sources are ingested — an unverified candidate in the advisory JSON
# is silently skipped (it was already excluded from backing any recommendation by the
# worker itself; this script just declines to persist it). Idempotent: re-ingesting the
# same advisory JSON adds nothing new the second time (dedup is on protocol_evidence_store's
# content-hash record_id).
#
# A source folded into the advisory JSON directly from a query_protocol_evidence.py store
# hit (query_protocol_evidence.py's own instructions tell the worker to skip a field's
# fresh search on a strong hit and fold that hit in) must carry `"origin_record_id":
# "<the hit's record_id>"` — this script skips ingesting any such source entirely, since
# the record already exists in the store under that id. Without this marker, a worker
# paraphrasing the claim to note "found via the store" would content-hash to a NEW
# record_id (the claim text differs from the original) and silently duplicate an existing
# finding every time a future run hits the same store record and re-ingests it.
#
# Usage:
#   python3 orchestration/scripts/ingest_protocol_evidence.py \
#       --store ff \
#       --from data/<run>/raw/literature_grounding.json \
#       --run-name <run_name> \
#       [--dry-run]
# Prints JSON: {"records_added": N, "records_skipped_duplicate": N,
#               "records_skipped_store_origin": N,
#               "records_rejected": [{"reason": "...", "field": "...", "doi": "..."}],
#               "store_path": "..."}
# ===========================================================================
# advisory-JSON field name -> value keys to lift into the record's `value` dict.
# Narrowed 2026-09-02: cooling_rate_K_per_ns / density_target_gcm3 / cte_glass_melt were retired
# from the literature critic's schema as non-essential to protocol adjustment, so nothing emits
# them any more. They deliberately REMAIN in FIELDS below -- records already in the store stay
# valid and queryable; this map only governs what a fresh advisory JSON can add.
_FF_FIELD_VALUE_KEYS = {
    "forcefield": ("recommendation",),
    "electrostatics": ("recommendation",),
    "tg_target_K": ("range",),
}
# advisory JSON key -> store `field` enum value (differs for a couple of keys).
_FF_FIELD_NAME_MAP = {
    "forcefield": "forcefield",
    "electrostatics": "electrostatics",
    "tg_target_K": "tg_target",
}


def _canon_smiles_list(smiles: str | None) -> list[str]:
    """Canonicalize once at ingest time (isomeric=False, matching rules_common's existing
    member_smiles convention) so query_protocol_evidence.py's exact_smiles tier can do a
    plain string comparison instead of re-canonicalizing every stored record's smiles on
    every query — the store is written far less often than it's read. Falls back to the
    raw SMILES on a canonicalization failure (RDKit/conda unavailable, bad SMILES) rather
    than dropping it, since an uncanonicalized entry degrades to a possible exact_smiles
    miss, not silent data loss."""
    if not smiles:
        return []
    try:
        return [rules_common.canonicalize(smiles, isomeric=False)]
    except (RuntimeError, subprocess.TimeoutExpired):
        return [smiles]


def _study_metadata_by_doi(advisory: dict) -> dict[str, dict]:
    """{bare doi -> md_studies[] entry} for title/url/year backfill.

    The literature critic writes each paper's metadata ONCE, in md_studies[], and its per-field
    sources[] entries carry only doi/claim/trust_tier/verified -- so the same paper cited for
    both `forcefield` and `electrostatics` cannot drift between the two. Resolving it back here
    keeps the store's records complete without asking the agent to retype anything.

    Keys are normalized to the bare 10.xxxx/... form: the PolyDatabase index hands out DOIs as
    full https://doi.org/... URLs, and a record whose doi carries the prefix content-hashes to a
    different record_id than the same paper stored bare.
    """
    out = {}
    for study in advisory.get("md_studies") or []:
        doi = _bare_doi(study.get("doi"))
        if doi:
            out[doi] = study
    return out


def _bare_doi(doi):
    """Strip a doi.org URL prefix. sha1(doi|field|claim) is the store's dedup key, so the URL
    and bare forms of one DOI would otherwise fork into two records for the same paper."""
    if not isinstance(doi, str):
        return doi
    d = doi.strip()
    for prefix in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "doi:"):
        if d.lower().startswith(prefix):
            return d[len(prefix):]
    return d


def _records_from_ff_advisory(advisory: dict, run_name: str) -> tuple[list[dict], list[str]]:
    """Returns (records_to_ingest, skipped_store_origin_record_ids)."""
    polymer_class = advisory.get("polymer_class")
    if polymer_class in (None, "UNKNOWN", "offtable"):
        polymer_class = None
    polymer_names = [advisory["polymer_name"]] if advisory.get("polymer_name") else []
    smiles = _canon_smiles_list(advisory.get("smiles"))

    studies = _study_metadata_by_doi(advisory)

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
            doi = _bare_doi(source.get("doi"))
            study = studies.get(doi, {})
            record = build_record(
                field=store_field,
                polymer_class=polymer_class,
                polymer_names=polymer_names,
                smiles=smiles,
                claim=source.get("claim", ""),
                value=value,
                doi=doi,
                url=source.get("url") or study.get("url"),
                title=source.get("title") or study.get("title"),
                year=source.get("year") or study.get("year"),
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
    # `ff` is the only advisory ingest path since 2026-09-02: the literature critic no longer
    # emits a system-size advisory (the DP/nchain/convergence fields it fed were retired). The
    # system_size store is still written -- but only by ingest-internal, from completed runs.
    if store_kind != "ff":
        raise ValueError(
            f"no advisory ingest path for --store {store_kind!r}; system_size records come from "
            "`ingest-internal` (completed validated runs) only")
    new_records, store_origin_ids = _records_from_ff_advisory(advisory, run_name)
    with_methodology = True

    accepted, rejected = [], []
    for r in new_records:
        errors = validate_record(r)
        if errors:
            rejected.append({"reason": "; ".join(errors), "field": r.get("field"), "doi": r.get("doi")})
        else:
            accepted.append(r)

    # Holding the lock across load+merge+save (not just save) is what actually prevents
    # the race: two concurrent ingests must not both load the pre-update store and then
    # each save their own merge, silently dropping whichever wrote second.
    with locked_store(store_path):
        store = load_store(store_path, with_methodology=with_methodology)
        merged, skipped_ids = dedupe(store["records"], accepted)
        added = len(accepted) - len(skipped_ids)

        if not dry_run and (added or store.get("records") != merged):
            store["records"] = merged
            save_store(store_path, store)

    return {
        "records_added": added,
        "records_skipped_duplicate": len(skipped_ids),
        "records_skipped_store_origin": len(store_origin_ids),
        "records_rejected": rejected,
        "store_path": store_path,
    }


# ===========================================================================
# INGEST: INTERNAL VALIDATED RUNS  (`ingest-internal`)
#
# ingest_internal_run_evidence.py — turn a completed, validated PolyJarvis run into
# protocol evidence for planning OTHER polymers.
#
# write_characterization_cache.py already freezes a completed run's exact executed
# protocol into guides/system_characterization_cache.json, keyed by isomeric-canonical
# SMILES — but that's a same-SMILES-only replay cache (make_deterministic_plan.py's
# make_plan_from_cache() is its only reader). It never becomes evidence for a DIFFERENT,
# chemically-related polymer's novel-run-plan grounding. This script closes that gap: it
# reads a run's frozen system_characterization_cache.json entry and emits
# ProtocolEvidenceRecords into the same docs/protocol_evidence_ff.json /
# protocol_evidence_system_size.json stores query_protocol_evidence.py already reads —
# tagged provenance.origin="internal_run", trust_tier="internal_validated_run" (ranked
# above peer_reviewed_doi, since it's directly reproduced in this exact pipeline, not
# merely cited).
#
# This is deliberately a SEPARATE script, not inlined into write_characterization_cache.py
# — same layering as ingest_protocol_evidence.py vs the literature workers: one script
# owns "freeze what ran," a second, independently callable/testable script owns "turn that
# into cross-polymer evidence." run_campaign.py calls both after an accepted campaign, each
# in its own try/except, so a failure in either never affects the other or the campaign.
#
# Only ever acts on a run whose system_characterization_cache.json entry has
# protocol_validated: true (never a blocked entry, e.g. one held back by a requires_*
# precondition like cis-PBD's requires_cis_lock).
#
# Only emits protocol-CHOICE fields (forcefield, electrostatics, system_size, cooling_rate)
# — never density_target/tg_target/cte_glass_melt. A run's acceptance certifies that its
# binding gate(s) passed, i.e. that the protocol choices produced a valid simulation; it
# does NOT certify that a measured property value is accurate against experiment. Gates
# bind on validity, not accuracy (PE1's own history: Tg 220.6 K passed its fit-quality gate
# but grades FAIL against experiment as a single-rate artifact; PCFF's density has a
# documented ~6% systematic deficit). Emitting measured values as *_target records at the
# top trust tier — where a worker's skip-rule lets them stand in for a fresh literature
# search — would institutionalize this pipeline's own known biases as its own highest-trust
# targets for the next polymer. What the gate DOES certify (FF/electrostatics/system-size
# choice worked; a cooling-rate schedule produced a well-fit Tg extrapolation) is safe to
# record and is what this module emits.
#
# Re-ingesting the same run_name (e.g. after a re-validation with different measured
# values or decisions) REPLACES that run's prior generation of internal-run records rather
# than accumulating alongside it — matching system_characterization_cache.json's own
# overwrite-on-revalidation semantics. Without this, two internal_validated_run-tier
# records for the same run could disagree, both sitting at the top trust tier, with the
# disagreement resolved only by insertion-order tie-break.
#
# Usage:
#   python3 orchestration/scripts/ingest_internal_run_evidence.py --run_name <run_name> [--dry-run]
# Prints JSON: {"status": "written"|"skipped", "reason": <str, if skipped>,
#               "records_added": N, "records_skipped_duplicate": N, "records_rejected": [...]}
# ===========================================================================
REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# decisions[].id -> the store `field` it grounds. Only D-01/D-03/D-04 map onto this
# schema's fields (D-02_charges, D-05..D-08 aren't part of the FIELDS enum — see
# literature-grounding-worker.md's own field table (Part A) for the same scope).
_DECISION_ID_TO_FIELD = {
    "D-01_ff": "forcefield",
    "D-03_electrostatics": "electrostatics",
    "D-04_system_size": "system_size",
}


def _canonicalize_or_none(smiles: str, *, isomeric: bool) -> Optional[str]:
    try:
        return rules_common.canonicalize(smiles, isomeric=isomeric)
    except (RuntimeError, subprocess.TimeoutExpired):
        return None


def _year_from_iso(iso_ts: Optional[str]) -> Optional[int]:
    if not iso_ts:
        return None
    try:
        return int(iso_ts[:4])
    except ValueError:
        return None


def evidence_records_from_completed_run(entry: dict, run_name: str, smiles: str) -> list[dict]:
    """Build ProtocolEvidenceRecords from a system_characterization_cache.json entry.

    `entry` must be a non-blocked, protocol_validated: true entry (the caller is
    responsible for that check — this function itself is defensive and returns [] if
    it isn't, so a caller passing a blocked entry by mistake fails safe rather than
    fabricating internal-run evidence for a precondition this writer never verified)."""
    if entry.get("protocol_validated") is not True:
        return []

    polymer_class = entry.get("polymer_class")
    validated_properties = entry.get("validated_properties") or []
    protocol = entry.get("protocol") or {}
    decided_params = protocol.get("decided_params") or {}
    decisions = protocol.get("decisions") or []
    year = _year_from_iso(entry.get("validated_at"))

    pseudo_doi = f"internal-run:{run_name}"
    title = f"PolyJarvis internal run {run_name} (in-pipeline validation)"
    relevance = ("First-party evidence: validated in this exact build/FF/gate pipeline, "
                 "not cited from an external study under different conditions.")

    def _provenance():
        return {"origin": "internal_run", "source_run": run_name, "migrated_from": None,
                 "added_at": _now_iso()}

    records = []

    decisions_by_id = {d.get("id"): d for d in decisions}
    for decision_id, field in _DECISION_ID_TO_FIELD.items():
        decision = decisions_by_id.get(decision_id)
        if not decision or not decision.get("choice"):
            continue
        choice = decision["choice"]
        if field == "system_size":
            value = {"dp_typical": decided_params.get("dp_typical"),
                      "nchain": decided_params.get("nchain"),
                      "convergence_basis": "internal_run_validated"}
            claim = (f"PolyJarvis validated {polymer_class} ({smiles}) at "
                     f"dp_typical={value['dp_typical']}, nchain={value['nchain']} in run "
                     f"{run_name}; validated properties: {sorted(validated_properties)}.")
        else:
            value = {"recommendation": choice}
            claim = (f"PolyJarvis validated {choice} for {field} on {polymer_class} "
                     f"({smiles}) in run {run_name}; validated properties: "
                     f"{sorted(validated_properties)}.")
        records.append(build_record(
            field=field, polymer_class=polymer_class, polymer_names=[], smiles=[smiles],
            claim=claim, value=value, doi=pseudo_doi, url=None, title=title, year=year,
            doi_verified=True, trust_tier="internal_validated_run", relevance=relevance,
            provenance=_provenance(),
        ))

    if "tg" in validated_properties and decided_params.get("tg_rates_K_per_ns"):
        rates = decided_params["tg_rates_K_per_ns"]
        records.append(build_record(
            field="cooling_rate", polymer_class=polymer_class, polymer_names=[], smiles=[smiles],
            claim=(f"PolyJarvis validated Tg using cooling rate(s) {rates} K/ns for "
                   f"{polymer_class} ({smiles}) in run {run_name}."),
            value={"rates_K_per_ns": rates}, doi=pseudo_doi, url=None, title=title, year=year,
            doi_verified=True, trust_tier="internal_validated_run", relevance=relevance,
            provenance=_provenance(),
        ))

    # Deliberately NOT emitted: density_target, tg_target, cte_glass_melt. These would be
    # this pipeline's own MEASURED values, not protocol choices the gate certifies as
    # sound — see the module docstring's "gates bind on validity, not accuracy" note.

    return records


def ingest_from_completed_run(run_name: str, *, repo_root: Path = REPO_ROOT,
                               cache_path: Optional[Path] = None,
                               ff_store_path: Optional[Path] = None,
                               system_size_store_path: Optional[Path] = None,
                               dry_run: bool = False) -> dict:
    repo_root = Path(repo_root)
    run_dir = repo_root / "data" / run_name
    try:
        plan = json.loads((run_dir / "raw" / "run_plan.json").read_text())
    except (OSError, json.JSONDecodeError) as e:
        return {"status": "skipped", "reason": f"could not read run_plan.json: {e}"}

    smiles_raw = plan.get("smiles")
    if not smiles_raw:
        return {"status": "skipped", "reason": "no smiles in run_plan.json"}

    canonical_isomeric = _canonicalize_or_none(smiles_raw, isomeric=True)
    if canonical_isomeric is None:
        return {"status": "skipped", "reason": "canonicalization (isomeric) failed"}

    # Derived from repo_root, not a fixed module-level constant -- a caller (test or
    # otherwise) passing a non-default repo_root must stay fully isolated to it, never
    # silently fall through to the real guides/docs files.
    cache_path = Path(cache_path) if cache_path else repo_root / "guides" / "system_characterization_cache.json"
    try:
        cache = json.loads(cache_path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        return {"status": "skipped", "reason": f"could not read {cache_path}: {e}"}

    entry = cache.get(canonical_isomeric)
    if not entry or entry.get("protocol_validated") is not True:
        return {"status": "skipped", "reason": "no protocol_validated cache entry for this run"}

    canonical_evidence_smiles = _canonicalize_or_none(smiles_raw, isomeric=False) or smiles_raw
    records = evidence_records_from_completed_run(entry, run_name, canonical_evidence_smiles)
    if not records:
        return {"status": "skipped", "reason": "no mappable decisions/measurements to record"}

    ff_records = [r for r in records if r["field"] != "system_size"]
    size_records = [r for r in records if r["field"] == "system_size"]

    ff_store_path = Path(ff_store_path) if ff_store_path else repo_root / "docs" / "protocol_evidence_ff.json"
    size_store_path = (Path(system_size_store_path) if system_size_store_path
                        else repo_root / "docs" / "protocol_evidence_system_size.json")

    result = {"status": "written", "records_added": 0, "records_skipped_duplicate": 0,
              "records_rejected": [], "records_replaced": 0}

    for store_path, group, with_methodology in (
        (ff_store_path, ff_records, True), (size_store_path, size_records, False),
    ):
        if not group:
            continue
        accepted, rejected = [], []
        for r in group:
            errors = validate_record(r)
            if errors:
                rejected.append({"reason": "; ".join(errors), "field": r.get("field")})
            else:
                accepted.append(r)
        result["records_rejected"].extend(rejected)

        with locked_store(str(store_path)):
            store = load_store(str(store_path), with_methodology=with_methodology)
            # Re-ingesting this run_name REPLACES its prior internal-run generation rather
            # than accumulating alongside it (see module docstring) -- only strips records
            # this exact mechanism wrote for this exact run, never a literature worker's
            # findings that happen to share the same source_run.
            existing = store["records"]
            kept = [r for r in existing
                    if not (r.get("provenance", {}).get("origin") == "internal_run"
                            and r.get("provenance", {}).get("source_run") == run_name)]
            result["records_replaced"] += len(existing) - len(kept)

            merged, skipped_ids = dedupe(kept, accepted)
            added = len(accepted) - len(skipped_ids)
            result["records_added"] += added
            result["records_skipped_duplicate"] += len(skipped_ids)
            if not dry_run and (merged != existing):
                store["records"] = merged
                save_store(str(store_path), store)

    return result


# ===========================================================================
# QUERY  (`query`)
#
# query_protocol_evidence.py — deterministic retrieval over the protocol evidence stores.
#
# Replaces "the literature-grounding-worker reads the whole legacy JSON file and reasons
# over it" with a real query. Always exits 0; errors surface as {"error": ...} in the JSON
# payload printed to stdout (same convention as select_forcefield.py/select_system_size.py)
# so callers parse JSON, never a traceback.
#
# Tier order (highest priority first), computed non-exclusively — a query can produce hits
# in more than one tier, all returned together, tier-ordered:
#   exact_smiles   — the query SMILES (canonicalized, isomeric=False) appears in a record's
#                    own `smiles[]` list (stored already-canonicalized at write time).
#   exact_class    — record's polymer_class matches --polymer-class (no SMILES hit).
#   similar_class  — record's polymer_class belongs to some OTHER class whose member_smiles
#                    scores >= --similarity-threshold against the query SMILES via
#                    chem_similarity.compute_similarities (one batched call, not one per
#                    class).
#
# Within a tier, records are sorted by trust_tier rank (internal_validated_run first, then
# peer_reviewed_doi — see protocol_evidence_store.TRUST_TIERS), then year
# descending, then doi ascending — fully deterministic, no tie resolved by file order.
#
# Usage:
#   python3 orchestration/scripts/query_protocol_evidence.py \
#       --store ff|system_size \
#       [--polymer-class CLASS] [--smiles '<repeat-unit SMILES>'] \
#       [--field forcefield|electrostatics|cooling_rate|density_target|tg_target|cte_glass_melt|system_size] \
#       [--methodology-only] [--top-k 5] [--similarity-threshold 0.4] [--no-chem-similarity]
# ===========================================================================
def _canon(smiles: str | None):
    if not smiles:
        return None
    try:
        return rules_common.canonicalize(smiles, isomeric=False)
    except (RuntimeError, subprocess.TimeoutExpired):
        return None


def _sort_key(hit: dict):
    r = hit["record"]
    tier_rank = {"exact_smiles": 0, "exact_class": 1, "similar_class": 2}[hit["tier"]]
    trust_rank = TRUST_TIER_RANK.get(r.get("trust_tier"), len(TRUST_TIERS))
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
        # migrate_ff_selection_literature.py, both isomeric=False, matching rules_common's
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
                result = compute_similarities(
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


# ===========================================================================
# CLI
# ===========================================================================
def _cmd_ingest(args) -> int:
    try:
        with open(args.from_path) as f:
            advisory = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(json.dumps({"error": f"failed to read {args.from_path}: {e}"}))
        return 0

    result = ingest(args.store, advisory, args.run_name, STORE_PATHS[args.store],
                     dry_run=args.dry_run)
    print(json.dumps(result, indent=2))
    return 0


def _cmd_ingest_internal(args) -> int:
    result = ingest_from_completed_run(
        args.run_name, cache_path=Path(args.cache_path) if args.cache_path else None,
        dry_run=args.dry_run)
    print(json.dumps(result, indent=2))
    return 0


def _cmd_query(args) -> int:
    store_path = STORE_PATHS[args.store]
    with_methodology = args.store == "ff"
    query_desc = {"store": args.store, "polymer_class": args.polymer_class,
                  "smiles": args.smiles, "field": args.field}

    try:
        store = load_store(store_path, with_methodology=with_methodology)
    except (OSError, json.JSONDecodeError) as e:
        print(json.dumps({"error": f"failed to load store: {e}", "query": query_desc}))
        return 0

    if args.methodology_only:
        print(json.dumps({
            "query": query_desc,
            "methodology_criteria": store.get("methodology_criteria", []),
        }, indent=2))
        return 0

    if not args.polymer_class and not args.smiles:
        print(json.dumps({
            "query": query_desc, "hits": [], "similarity_errors": [],
            "note": "no --polymer-class or --smiles given; nothing to query on",
        }, indent=2))
        return 0

    try:
        rules = load_rules()
    except (OSError, json.JSONDecodeError) as e:
        print(json.dumps({"error": f"failed to load polymer_rules.json: {e}", "query": query_desc}))
        return 0

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
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)

    c = sub.add_parser("ingest", help="fold a literature-grounding advisory JSON into a store")
    c.add_argument("--store", choices=["ff"], required=True)
    c.add_argument("--from", dest="from_path", required=True)
    c.add_argument("--run-name", required=True)
    c.add_argument("--dry-run", action="store_true")
    c.set_defaults(func=_cmd_ingest)

    c = sub.add_parser("ingest-internal", help="fold a completed validated run into the store")
    c.add_argument("--run_name", required=True)
    c.add_argument("--cache_path", default=None)
    c.add_argument("--dry-run", action="store_true")
    c.set_defaults(func=_cmd_ingest_internal)

    c = sub.add_parser("query", help="tiered retrieval over a store")
    c.add_argument("--store", choices=["ff", "system_size"], required=True)
    c.add_argument("--polymer-class")
    c.add_argument("--smiles")
    c.add_argument("--field", choices=FIELDS)
    c.add_argument("--methodology-only", action="store_true")
    c.add_argument("--top-k", type=int)
    c.add_argument("--similarity-threshold", type=float, default=0.4)
    c.add_argument("--no-chem-similarity", action="store_true")
    c.add_argument("--sim-env", default="radonpy")
    c.set_defaults(func=_cmd_query)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
