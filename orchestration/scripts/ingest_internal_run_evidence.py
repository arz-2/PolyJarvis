#!/usr/bin/env python3
"""
ingest_internal_run_evidence.py — turn a completed, validated PolyJarvis run into
protocol evidence for planning OTHER polymers.

write_characterization_cache.py already freezes a completed run's exact executed
protocol into guides/system_characterization_cache.json, keyed by isomeric-canonical
SMILES — but that's a same-SMILES-only replay cache (make_deterministic_plan.py's
make_plan_from_cache() is its only reader). It never becomes evidence for a DIFFERENT,
chemically-related polymer's novel-run-plan grounding. This script closes that gap: it
reads a run's frozen system_characterization_cache.json entry and emits
ProtocolEvidenceRecords into the same docs/protocol_evidence_ff.json /
protocol_evidence_system_size.json stores query_protocol_evidence.py already reads —
tagged provenance.origin="internal_run", trust_tier="internal_validated_run" (ranked
above peer_reviewed_doi, since it's directly reproduced in this exact pipeline, not
merely cited).

This is deliberately a SEPARATE script, not inlined into write_characterization_cache.py
— same layering as ingest_protocol_evidence.py vs the literature workers: one script
owns "freeze what ran," a second, independently callable/testable script owns "turn that
into cross-polymer evidence." run_campaign.py calls both after an accepted campaign, each
in its own try/except, so a failure in either never affects the other or the campaign.

Only ever acts on a run whose system_characterization_cache.json entry has
protocol_validated: true (never a blocked entry, e.g. one held back by a requires_*
precondition like cis-PBD's requires_cis_lock).

Only emits protocol-CHOICE fields (forcefield, electrostatics, system_size, cooling_rate)
— never density_target/tg_target/cte_glass_melt. A run's acceptance certifies that its
binding gate(s) passed, i.e. that the protocol choices produced a valid simulation; it
does NOT certify that a measured property value is accurate against experiment. Gates
bind on validity, not accuracy (PE1's own history: Tg 220.6 K passed its fit-quality gate
but grades FAIL against experiment as a single-rate artifact; PCFF's density has a
documented ~6% systematic deficit). Emitting measured values as *_target records at the
top trust tier — where a worker's skip-rule lets them stand in for a fresh literature
search — would institutionalize this pipeline's own known biases as its own highest-trust
targets for the next polymer. What the gate DOES certify (FF/electrostatics/system-size
choice worked; a cooling-rate schedule produced a well-fit Tg extrapolation) is safe to
record and is what this module emits.

Re-ingesting the same run_name (e.g. after a re-validation with different measured
values or decisions) REPLACES that run's prior generation of internal-run records rather
than accumulating alongside it — matching system_characterization_cache.json's own
overwrite-on-revalidation semantics. Without this, two internal_validated_run-tier
records for the same run could disagree, both sitting at the top trust tier, with the
disagreement resolved only by insertion-order tie-break.

Usage:
  python3 orchestration/scripts/ingest_internal_run_evidence.py --run_name <run_name> [--dry-run]
Prints JSON: {"status": "written"|"skipped", "reason": <str, if skipped>,
              "records_added": N, "records_skipped_duplicate": N, "records_rejected": [...]}
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import canon_smiles  # noqa: E402
import protocol_evidence_store as pes  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# decisions[].id -> the store `field` it grounds. Only D-01/D-03/D-04 map onto this
# schema's fields (D-02_charges, D-05..D-08 aren't part of the FIELDS enum — see
# ff-protocol-literature-worker.md's own field table for the same scope).
_DECISION_ID_TO_FIELD = {
    "D-01_ff": "forcefield",
    "D-03_electrostatics": "electrostatics",
    "D-04_system_size": "system_size",
}


def _canonicalize_or_none(smiles: str, *, isomeric: bool) -> Optional[str]:
    try:
        return canon_smiles.canonicalize(smiles, isomeric=isomeric)
    except (RuntimeError, subprocess.TimeoutExpired):
        return None


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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
        records.append(pes.build_record(
            field=field, polymer_class=polymer_class, polymer_names=[], smiles=[smiles],
            claim=claim, value=value, doi=pseudo_doi, url=None, title=title, year=year,
            doi_verified=True, trust_tier="internal_validated_run", relevance=relevance,
            provenance=_provenance(),
        ))

    if "tg" in validated_properties and decided_params.get("tg_rates_K_per_ns"):
        rates = decided_params["tg_rates_K_per_ns"]
        records.append(pes.build_record(
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
            errors = pes.validate_record(r)
            if errors:
                rejected.append({"reason": "; ".join(errors), "field": r.get("field")})
            else:
                accepted.append(r)
        result["records_rejected"].extend(rejected)

        with pes.locked_store(str(store_path)):
            store = pes.load_store(str(store_path), with_methodology=with_methodology)
            # Re-ingesting this run_name REPLACES its prior internal-run generation rather
            # than accumulating alongside it (see module docstring) -- only strips records
            # this exact mechanism wrote for this exact run, never a literature worker's
            # findings that happen to share the same source_run.
            existing = store["records"]
            kept = [r for r in existing
                    if not (r.get("provenance", {}).get("origin") == "internal_run"
                            and r.get("provenance", {}).get("source_run") == run_name)]
            result["records_replaced"] += len(existing) - len(kept)

            merged, skipped_ids = pes.dedupe(kept, accepted)
            added = len(accepted) - len(skipped_ids)
            result["records_added"] += added
            result["records_skipped_duplicate"] += len(skipped_ids)
            if not dry_run and (merged != existing):
                store["records"] = merged
                pes.save_store(str(store_path), store)

    return result


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--run_name", required=True)
    p.add_argument("--cache_path", default=None)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    result = ingest_from_completed_run(
        args.run_name, cache_path=Path(args.cache_path) if args.cache_path else None,
        dry_run=args.dry_run)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
