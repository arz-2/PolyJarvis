#!/usr/bin/env python3
"""
write_characterization_cache.py — freeze a completed campaign's validated protocol into
guides/system_characterization_cache.json, keyed by isomeric-canonical SMILES.

Called automatically by run_campaign.py's run_campaign_workflow() whenever WorkflowEngine.run()
returns status=="accepted". Never raises out of the campaign's success path -- any failure here
is caught by the caller and logged, not propagated.

decision_policy.json's confidence_gate already specifies the SMILES-keyed fast path this feeds:
plan_mode=deterministic when cache[canonical_smiles].protocol_validated is true AND
validated_properties covers the requested properties. make_deterministic_plan.py's
make_plan_from_cache() is the reader; this module is the writer.

Correctness note: freezes workflow_state.json's effective_parameters (decided_params AS AMENDED
BY ANY MID-RUN REMEDY), not run_plan.json's original decided_params -- a value a remedy changed
mid-run is the value that actually reached the deck, and the one worth replaying. See project
history: "decided_params can be decorative" (a recorded value that never reached the deck).
"""
from __future__ import annotations

import fcntl
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import track_registry  # noqa: E402
import rules_common  # noqa: E402  -- module import (not `from ... import canonicalize`) so tests can monkeypatch rules_common.canonicalize
from make_deterministic_plan import SNAPSHOT_KEYS  # noqa: E402  -- single source of truth, don't duplicate

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CACHE_PATH_DEFAULT = REPO_ROOT / "guides" / "system_characterization_cache.json"

# decided_params keys worth freezing as "the exact validated protocol." SNAPSHOT_KEYS plus
# T_workflow_K, which make_plan() computes AFTER the SNAPSHOT_KEYS comprehension
# (make_deterministic_plan.py) and which records the melt/production REFERENCE temperature the
# run actually used. It is NO LONGER the regime-determining field -- stage_params._regime asks
# final_T_K against Tg directly -- but it still defines the protocol that ran, which is what
# freezing is for. Not folded into SNAPSHOT_KEYS itself -- that constant's
# docstring guarantees decided_params-as-identity for an unmodified class scaffold, a narrower
# contract than "the protocol actually executed." If SNAPSHOT_KEYS gains a future key with a
# similar computed-after-the-fact sibling, FREEZE_KEYS needs the same treatment -- check both
# definitions together.
FREEZE_KEYS = SNAPSHOT_KEYS + ["T_workflow_K", "T_melt_hold_K", "preferred_ff"]
"""T_melt_hold_K joins T_workflow_K for the same reason: it is resolved by
temperature_schedule AFTER the SNAPSHOT_KEYS comprehension runs, and it is the
protocol-defining melt temperature -- a replayed protocol that did not carry it
would re-derive the melt from whatever the class says today.

preferred_ff joined them on 2026-09-12, and its absence was the sharpest bug in the replay
path. make_plan_from_cache's own comment reads "The field is frozen; everything it implies
is re-derived" -- but the field was never in SNAPSHOT_KEYS (that constant describes an
unmodified class scaffold, and D-01 RESOLVES the field rather than copying it), so a frozen
protocol carried preferred_ff=None. _derived_from_field(None) then resolved an empty family
and handed the replay charge_method="RESP" -- a QM charge model -- for three PCFF systems
that require bond-increment, while the replayed D-01 row still read "pcff". The plan was
internally inconsistent and the most important decision in it, the force field, was the one
thing NOT being replayed: it fell back to the class ff_accuracy_prior. That is invisible
while the adjudicated field equals the prior, as it did for all four rev2 systems, and
silently reverts the decision the moment a run moves the field OFF the prior -- which is
exactly what the D-01 probe cascade exists to do."""

# property -> the workflow_engine.py stage whose acceptance already proves that property's
# binding gate (equil_verdict / tg_gate_verdict / bm_gate_verdict|deform_gate_verdict) passed.
STAGE_FOR_PROPERTY = {p: track_registry.stage_for_property(p)
                      for p in sorted(track_registry.VALID_PROPERTIES)}


def _canonicalize_or_none(smiles: str) -> Optional[str]:
    try:
        return rules_common.canonicalize(smiles, isomeric=True)
    except (RuntimeError, subprocess.TimeoutExpired):
        return None


REPORTABLE_VERDICTS = {
    "tg_gate_verdict": {"TG_REPORTABLE"},
    "bm_gate_verdict": {"BM_REPORTABLE", "BM_FALLBACK_DEFORM"},
    "deform_gate_verdict": {"DEFORM_REPORTABLE"},
}
# Markers an accepted stage carries when it was accepted WITHOUT its binding gate passing:
# an advisory-gate replicate, an operator unblocking a downstream track, or the recovery
# agent's accept_with_caveat. Acceptance alone therefore does not prove the gate passed.
NOT_REPORTABLE_MARKERS = ("gate_verdict_advisory", "tg_not_reportable", "recovery_caveat")


def _accepted_outputs(run_dir: Optional[Path], record: dict) -> Optional[dict]:
    attempt_id = record.get("accepted_attempt")
    if run_dir is None or not attempt_id:
        return None
    stored = next((a.get("manifest") for a in record.get("attempts", ())
                   if a.get("attempt_id") == attempt_id and a.get("manifest")), None)
    try:
        return json.loads(Path(stored).read_text()).get("outputs") or {}
    except (OSError, TypeError, json.JSONDecodeError):
        return None


def _gate_passed(outputs: Optional[dict]) -> bool:
    if outputs is None:
        # No readable manifest: nothing proves the gate passed, and freezing is irreversible
        # in effect (the next same-SMILES plan replays it), so fail closed.
        return False
    if any(outputs.get(marker) for marker in NOT_REPORTABLE_MARKERS):
        return False
    bm = outputs.get("bm_gate_verdict")
    if bm == "BM_FALLBACK_DEFORM" and outputs.get("deform_gate_verdict") != "DEFORM_REPORTABLE":
        return False
    return all(outputs[key] in ok for key, ok in REPORTABLE_VERDICTS.items() if key in outputs)


def _validated_properties(plan: dict, workflow_state: dict, run_dir: Optional[Path] = None) -> set:
    requested = set(plan.get("properties") or ())
    stages = workflow_state.get("stages", {})
    validated = set()
    for prop, stage in STAGE_FOR_PROPERTY.items():
        record = stages.get(stage, {})
        if prop not in requested or record.get("status") != "accepted":
            continue
        if run_dir is not None and not _gate_passed(_accepted_outputs(run_dir, record)):
            continue
        validated.add(prop)
    return validated


def _accepted_run_summary_results(run_dir: Path, workflow_state: dict) -> dict:
    attempt_id = workflow_state.get("stages", {}).get("summary", {}).get("accepted_attempt")
    if not attempt_id:
        return {}
    path = run_dir / "attempts" / "summary" / attempt_id / "raw" / "run_summary.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text()).get("results", {})
    except json.JSONDecodeError:
        return {}


def _build_notes(workflow_state: dict, validated_properties: set) -> str:
    parts = [f"Validated properties: {sorted(validated_properties)}."]
    remedies = workflow_state.get("remedy_history") or []
    if remedies:
        summary = [f"{r.get('remedy_id')} on {r.get('finding', {}).get('stage')} "
                   f"(application {r.get('application')})" for r in remedies]
        parts.append(
            "Frozen decided_params reflect mid-run remedy application(s), not the original "
            f"plan's decided_params: {'; '.join(summary)}. See workflow_state.json.remedy_history "
            "on the source run for full detail."
        )
    return " ".join(parts)


class _NullLock:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _FileLock:
    """Exclusive advisory lock on a sidecar file, held for the full read-modify-write-replace.

    guides/system_characterization_cache.json is the first file in this repo written
    automatically by potentially-concurrent campaigns for different keys -- no existing
    cross-process lock precedent in orchestration/scripts/ to reuse (atomic_write_json elsewhere
    is temp-file-then-replace only, which is safe against partial writes but not against two
    processes racing a read-modify-write of the same dict).
    """

    def __init__(self, lock_path: Path):
        self._lock_path = lock_path
        self._fh = None

    def __enter__(self):
        self._fh = open(self._lock_path, "w")
        fcntl.flock(self._fh, fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc):
        fcntl.flock(self._fh, fcntl.LOCK_UN)
        self._fh.close()
        return False


def _lock_for(cache_path: Path):
    if not hasattr(fcntl, "flock"):  # pragma: no cover -- non-POSIX fallback
        return _NullLock()
    return _FileLock(cache_path.with_name(f".{cache_path.name}.lock"))


def _atomic_write(path: Path, value: dict) -> None:
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    tmp.replace(path)


def write_characterization_cache(
    run_name: str, *, repo_root: Path = REPO_ROOT, cache_path: Optional[Path] = None,
) -> Optional[dict]:
    """Freeze run_name's executed protocol into the system characterization cache.

    Returns the written entry dict, or None if nothing was written (no smiles, RDKit
    canonicalization failed, or no requested property's stage actually reached "accepted").
    Never raises -- every failure mode degrades to "wrote nothing."
    """
    run_dir = Path(repo_root) / "data" / run_name
    try:
        plan = json.loads((run_dir / "raw" / "run_plan.json").read_text())
        workflow_state = json.loads((run_dir / "workflow_state.json").read_text())
    except (OSError, json.JSONDecodeError):
        return None

    if plan.get("tg_sensitivity"):
        # A benchmarks/tg_sensitivity leg is its anchor's protocol with one knob deliberately
        # moved. Freezing it would overwrite the anchor SMILES' validated protocol with the
        # perturbed one, and the next same-SMILES plan would replay the perturbation.
        return None

    smiles = plan.get("smiles")
    if not smiles:
        return None
    canonical = _canonicalize_or_none(smiles)
    if canonical is None:
        return None

    validated_properties = _validated_properties(plan, workflow_state, run_dir)
    if not validated_properties:
        # WorkflowEngine.run() only returns status=="accepted" once every stage
        # enabled_stages() derives from plan["properties"] is itself accepted, so this branch
        # is unreachable for a genuinely accepted campaign except a malformed plan/state pair.
        # Write nothing rather than assert protocol_validated: false for a state that can't occur.
        return None

    effective_params = workflow_state.get("effective_parameters", {})
    decided_params = {k: effective_params[k] for k in FREEZE_KEYS if k in effective_params}
    decisions = [dict(d) for d in plan.get("decisions", []) if d.get("id") != "D-08_hardware"]
    simulated_properties = _accepted_run_summary_results(run_dir, workflow_state)
    notes = _build_notes(workflow_state, validated_properties)

    cache_path = Path(cache_path) if cache_path else CACHE_PATH_DEFAULT
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    with _lock_for(cache_path):
        cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
        existing = cache.get(canonical, {})
        # requires_* (e.g. cis-PBD1's requires_cis_lock) documents a precondition this generic
        # writer cannot verify was met -- EMC ignores SMILES double-bond stereo, so a plain
        # build/equil for that SMILES yields a mixed cis/trans cell and its own note explicitly
        # says protocol_validated is deliberately NOT set. Never silently flip that to true.
        blocked_by = next((k for k in existing if k.startswith("requires_") and existing[k]), None)
        entry = dict(existing)  # preserve legacy fields (probe_*, derived_*, note, requires_*, ...)
        now = datetime.now(timezone.utc).isoformat()
        if blocked_by:
            entry.update({
                "protocol_validated": False,
                "polymer_class": plan.get("polymer_class"),
                "source_run_name": run_name,
                "validated_at": now,
                "notes": f"BLOCKED by existing '{blocked_by}': this run's protocol was NOT "
                         f"frozen as validated because a precondition this writer cannot verify "
                         f"may not have been met. {notes}",
            })
        else:
            entry.update({
                "protocol_validated": True,
                "validated_properties": sorted(validated_properties),
                "polymer_class": plan.get("polymer_class"),
                "source_run_name": run_name,
                "validated_at": now,
                "protocol": {
                    "decided_params": decided_params,
                    "decisions": decisions,
                    "planned_stages": plan.get("planned_stages", []),
                },
                "simulated_properties": simulated_properties,
                "notes": notes,
            })
        cache[canonical] = entry
        _atomic_write(cache_path, cache)
        return entry


def main():
    import argparse
    p = argparse.ArgumentParser(
        description="Freeze a completed run's protocol into system_characterization_cache.json.")
    p.add_argument("--run_name", required=True)
    p.add_argument("--cache_path", default=None)
    args = p.parse_args()
    entry = write_characterization_cache(
        args.run_name, cache_path=Path(args.cache_path) if args.cache_path else None)
    if entry is None:
        print(json.dumps({"status": "skipped", "run_name": args.run_name}))
    else:
        print(json.dumps({"status": "written", "run_name": args.run_name,
                          "protocol_validated": entry.get("protocol_validated")}))


if __name__ == "__main__":
    main()
