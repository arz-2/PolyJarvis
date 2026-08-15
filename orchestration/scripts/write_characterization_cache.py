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
                  "validated_at", "protocol"}

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
    """Merge the characterized half. Gated on at least one derived_* field being non-null: the
    orchestrator's novelty check is bare key existence, so writing an entry that carries no
    usable knob would permanently mark this SMILES as no longer novel."""
    offending = sorted(VALIDATED_KEYS & set(fields))
    if offending:
        return {"written": False, "reason": "validated_fields_are_protocol_locker_owned",
                "offending_fields": offending}

    # Gate on what was actually derived, not on the reliability flags. The two are not
    # equivalent: every derivable knob needs probe_tau_relax_reliable (the K_deform pair needs
    # both flags), so a K0-reliable/tau-unreliable probe derives nothing yet still satisfied
    # any(flags) — writing an entry with no knobs in it and permanently marking this SMILES
    # non-novel, since the orchestrator's novelty check is bare key existence.
    derived = sorted(k for k in fields if k.startswith("derived_") and fields[k] is not None)
    if not derived:
        return {"written": False, "reason": "no_derived_field",
                "detail": "no derived_* field was produced (every knob requires "
                          "probe_tau_relax_reliable; the K_deform pair requires both flags) — "
                          "leaving the key absent so this SMILES stays novel",
                "reliability_flags": {f: fields.get(f) for f in RELIABILITY_FLAGS}}

    cache = _load(cache_path)
    existing = cache.get(smiles, {})
    preserved = {k: existing[k] for k in VALIDATED_KEYS if k in existing}
    cache[smiles] = {**existing, **fields, **preserved}
    _save(cache_path, cache)
    return {"written": True, "smiles": smiles, "mode": "characterization",
            "fields_written": sorted(fields), "validated_fields_preserved": sorted(preserved),
            "other_keys_preserved": sorted(k for k in cache if k != smiles),
            "cache_path": str(cache_path)}


def write_validated(cache_path: Path, smiles: str, run_name: str, properties: list,
                    protocol: dict = None) -> dict:
    """Merge the validated half. validated_properties is a union, not an overwrite — a SMILES
    validated for density+tg in one run and bulk_modulus in a later one ends up validated for all
    three, which is what planner/critic's plan_mode gate reads.

    `protocol` is the per-track frozen protocol (make_deterministic_plan.build_frozen_protocol):
    what this molecule ACTUALLY RAN, so a replicate can reproduce it with different seeds. Merged
    per track, not wholesale — a run that freezes only `thermal` must not drop a `mechanical`
    block an earlier run of the same SMILES already froze."""
    cache = _load(cache_path)
    existing = cache.get(smiles, {})
    merged_props = sorted(set(existing.get("validated_properties") or []) | set(properties))
    merged_protocol = {**(existing.get("protocol") or {}), **(protocol or {})}
    cache[smiles] = {**existing,
                     "protocol_validated": True,
                     "validated_properties": merged_props,
                     "validated_run_name": run_name,
                     "validated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    if merged_protocol:
        cache[smiles]["protocol"] = merged_protocol
    _save(cache_path, cache)
    return {"written": True, "smiles": smiles, "mode": "lock", "validated_run_name": run_name,
            "validated_properties": merged_props,
            "protocol_tracks_frozen": sorted(protocol or {}),
            "protocol_tracks_total": sorted(merged_protocol),
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
    p.add_argument("--plan", metavar="RUN_PLAN_JSON",
                   help="--lock only: the finished run's run_plan.json. Given this, the lock also "
                        "freezes the protocol this molecule ACTUALLY RAN, per track, gated on each "
                        "track's PHYSICAL VALIDITY verdicts (equil/SIZE/HOMOG, TG_REPORTABLE, "
                        "BM_/DEFORM_REPORTABLE) read from the run's own raw/*.json — never on "
                        "agreement with experiment.")
    p.add_argument("--raw-dir", help="--lock only: the run's raw/ dir (default: sibling of --plan).")
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
        protocol, gates = {}, None
        if args.plan:
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            from make_deterministic_plan import build_frozen_protocol
            from verify_protocol_replay import verify
            plan_path = Path(args.plan)
            raw_dir = Path(args.raw_dir) if args.raw_dir else plan_path.parent
            # Deck-replay gate: regenerate this run's decks from its own plan and diff. A track
            # whose plan values never reached its decks is not frozen, however good its physics.
            replay = verify(raw_dir.parent)
            protocol, gates = build_frozen_protocol(
                json.loads(plan_path.read_text()), raw_dir, args.run_name, replay)
            if not protocol:
                # Foundation is a prerequisite for every other track, so an unadjudicated or
                # failing foundation means nothing is freezable. Refuse loudly rather than
                # stamping a validated flag with no reproducible protocol behind it.
                print(json.dumps({"written": False, "reason": "no_freezable_track",
                                  "detail": "no track passed its physical validity gates "
                                            "(foundation is a prerequisite for all others)",
                                  "validity_gates": gates}, indent=2))
                sys.exit(1)
        result = write_validated(cache_path, args.smiles, args.run_name, props, protocol)
        if gates is not None:
            result["validity_gates"] = gates
    else:
        if not args.fields:
            p.error("--fields is required unless --lock is given")
        result = write_characterization(
            cache_path, args.smiles, json.loads(Path(args.fields).read_text()))

    print(json.dumps(result, indent=2))
    sys.exit(0 if result["written"] else 1)


if __name__ == "__main__":
    main()
