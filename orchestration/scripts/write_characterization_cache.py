#!/usr/bin/env python3
"""
write_characterization_cache.py — read-merge-write one SMILES key in
guides/system_characterization_cache.json.

The write side of apply_cached_characterization.py. Both of the agents that mutate this file
(system-characterization-analyzer, protocol-locker) are denied Read and Bash on `guides/**` by
.claude/hooks/agent_context_boundary.py, so neither could ever perform a read-verified merge:
the analyzer's `Write` was a full-file overwrite with no visibility into the other SMILES keys
already there, and protocol-locker's prescribed jq merge was refused outright. This script is on
both agents' bash_allow and does the merge for them.

Two modes, matching the two independent flags a cache entry carries:

  default   the `characterized` half — probe_*/derived_* Phase-A timing knobs
            (system-characterization-analyzer). Refuses to set any VALIDATED_KEY.
  --lock    the `validated` half — protocol_validated/validated_* (protocol-locker).
            Refuses to set any characterization field. Unions validated_properties.

Usage:
  python3 orchestration/scripts/write_characterization_cache.py \
      --smiles "<canonical smiles>" --fields data/<RUN>/raw/system_characterization.json
  python3 orchestration/scripts/write_characterization_cache.py \
      --smiles "<canonical smiles>" --lock --run_name <RUN> --properties density,tg

Prints a JSON result summary to stdout. Exit 1 on refusal.

The json.load/json.dump round-trip is safe on this file — it is machine-generated, with no
comments and no hand alignment. Never point --cache at guides/polymer_rules.json: that one IS
hand-formatted and the round-trip would destroy it, which is why --cache refuses any other path.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CACHE_PATH = REPO_ROOT / "guides" / "system_characterization_cache.json"

# Owned by protocol-locker.md, never by the characterization write (and vice versa). The split is
# the whole reason this script exists: system-characterization-analyzer.md states the boundary in
# prose, and prose cannot stop a full-file Write from carrying a stale validated stamp forward.
VALIDATED_KEYS = {"protocol_validated", "validated_properties", "validated_run_name",
                  "validated_at"}

RELIABILITY_FLAGS = ("probe_tau_relax_reliable", "probe_K0_reliable")


def _load(cache_path: Path) -> dict:
    if not cache_path.exists():
        return {}
    text = cache_path.read_text().strip()
    return json.loads(text) if text else {}


def _save(cache_path: Path, cache: dict) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, indent=2) + "\n")


def write_characterization(cache_path: Path, smiles: str, fields: dict) -> dict:
    """Merge the characterized half. Gated on the same reliability rule the orchestrator's
    novelty check depends on: that check is bare key existence, so writing an entry whose every
    measurement failed would permanently mark this SMILES as no longer novel."""
    offending = sorted(VALIDATED_KEYS & set(fields))
    if offending:
        return {"written": False, "reason": "validated_fields_are_protocol_locker_owned",
                "offending_fields": offending}

    if not any(fields.get(f) for f in RELIABILITY_FLAGS):
        return {"written": False, "reason": "no_reliable_measurement",
                "detail": f"none of {list(RELIABILITY_FLAGS)} is true — leaving the key absent "
                          f"so this SMILES stays novel"}

    cache = _load(cache_path)
    existing = cache.get(smiles, {})
    preserved = {k: existing[k] for k in VALIDATED_KEYS if k in existing}
    cache[smiles] = {**existing, **fields, **preserved}
    _save(cache_path, cache)
    return {"written": True, "smiles": smiles, "mode": "characterization",
            "fields_written": sorted(fields), "validated_fields_preserved": sorted(preserved),
            "other_keys_preserved": sorted(k for k in cache if k != smiles),
            "cache_path": str(cache_path)}


def write_validated(cache_path: Path, smiles: str, run_name: str, properties: list) -> dict:
    """Merge the validated half. validated_properties is a union, not an overwrite — a SMILES
    validated for density+tg in one run and bulk_modulus in a later one ends up validated for all
    three, which is what planner/critic's plan_mode gate reads."""
    cache = _load(cache_path)
    existing = cache.get(smiles, {})
    merged_props = sorted(set(existing.get("validated_properties") or []) | set(properties))
    cache[smiles] = {**existing,
                     "protocol_validated": True,
                     "validated_properties": merged_props,
                     "validated_run_name": run_name,
                     "validated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    _save(cache_path, cache)
    return {"written": True, "smiles": smiles, "mode": "lock", "validated_run_name": run_name,
            "validated_properties": merged_props,
            "characterization_fields_preserved": sorted(set(existing) - VALIDATED_KEYS),
            "other_keys_preserved": sorted(k for k in cache if k != smiles),
            "cache_path": str(cache_path)}


def main():
    p = argparse.ArgumentParser(
        description="Read-merge-write one SMILES key in the system characterization cache.")
    p.add_argument("--smiles", required=True, metavar="CANONICAL_SMILES",
                   help="Canonical SMILES key (orchestration/scripts/canon_smiles.py).")
    p.add_argument("--cache", default=str(CACHE_PATH),
                   help="Cache path. Defaults to guides/system_characterization_cache.json and "
                        "refuses anything else.")
    p.add_argument("--lock", action="store_true",
                   help="protocol-locker mode: write the validated_* stamp instead of the "
                        "characterization fields.")
    p.add_argument("--fields", metavar="JSON_FILE",
                   help="Default mode: JSON file of probe_*/derived_* fields to merge "
                        "(this run's system_characterization.json).")
    p.add_argument("--run_name", help="--lock only: the run that validated this SMILES.")
    p.add_argument("--properties", default="",
                   help="--lock only: comma-separated properties validated by this run.")
    args = p.parse_args()

    cache_path = Path(args.cache).resolve()
    if cache_path != CACHE_PATH.resolve():
        print(json.dumps({"written": False, "reason": "cache_path_not_allowed",
                          "detail": f"this script only writes {CACHE_PATH}"}))
        sys.exit(1)

    if args.lock:
        if not args.run_name:
            p.error("--lock requires --run_name")
        props = [s for s in (x.strip() for x in args.properties.split(",")) if s]
        result = write_validated(cache_path, args.smiles, args.run_name, props)
    else:
        if not args.fields:
            p.error("--fields is required unless --lock is given")
        result = write_characterization(
            cache_path, args.smiles, json.loads(Path(args.fields).read_text()))

    print(json.dumps(result, indent=2))
    sys.exit(0 if result["written"] else 1)


if __name__ == "__main__":
    main()
