#!/usr/bin/env python3
"""Build the Tg sensitivity legs: thermal-stage-only forks off a gated melt cell.

A leg is NOT a new campaign. It is a run directory holding two files -- its own
run_plan.json and its own workflow_state.json -- whose state records `build` and
`equilibration` as already accepted, pointing at the ANCHOR's executor_state.json.
Consequences, all deliberate:

  * No rebuild, no re-equilibration, no cooling. properties=["tg"] makes
    enabled_stages() == (build, equilibration, thermal, summary), and
    stages_for("tg_rate_K_per_ns") == ("thermal", "cooling") then filters cooling out
    via `affected & set(enabled)` -- so a rate change costs a sweep, not a cooldown.
  * No copied trajectories. The leg reads the anchor's melt cell in place, so a leg
    costs ~8 kB of disk. workflow_engine._accepted_manifest re-verifies every artifact's
    sha256 on load, so a leg fails loudly rather than silently running against a cell
    that was moved, truncated or garbage-collected.
  * The anchor is never written to. Nothing here opens a file under the anchor's tree.

Only ONE decided_params key moves per leg (two for the PE t-grid legs, which pin the rate
they hold fixed). verify_matrix.py asserts that, and asserts the seeds did NOT move.

Usage:
    python3 benchmarks/tg_sensitivity/build_matrix.py [--dry-run] [--only L1,L4]
                                                      [--anchor-override iPMMA_1=PLLA_1]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
MANIFEST = HERE / "MANIFEST.json"
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))

from workflow_engine import ENGINE_VERSION, _canonical_hash  # noqa: E402
import track_registry  # noqa: E402

# The stages a leg inherits rather than runs. Everything else in enabled_stages() starts pending.
INHERITED = ("build", "equilibration")


def load(path: Path) -> dict:
    return json.loads(path.read_text())


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def leg_name(leg: dict, anchor: str) -> str:
    """Anchor-qualified, so swapping iPMMA_1 -> PLLA_1 does not collide with an earlier build."""
    key, value = next(iter(leg["override"].items()))
    tag = "r" if key == "tg_rate_K_per_ns" else "dT"
    return f"TGS_{anchor}_{leg['id']}_{tag}{value}"


def inherited_stage_record(anchor_state: dict, stage: str) -> dict:
    """The anchor's own record for a stage it has already accepted, carried over verbatim.

    Verbatim matters: `manifest` is the absolute path _accepted_manifest reads, and
    `input_hash` is what tells the engine this stage does not need re-running. Rewriting
    either would either re-run the stage or point it at nothing.
    """
    record = anchor_state["stages"][stage]
    accepted = record.get("accepted_attempt")
    if not accepted:
        raise SystemExit(f"anchor stage {stage!r} has no accepted attempt -- not forkable yet")
    entry = next((a for a in record["attempts"] if a.get("attempt_id") == accepted), None)
    if entry is None:
        raise SystemExit(f"anchor stage {stage!r} names accepted attempt {accepted!r} "
                         f"but has no matching attempt record")
    manifest = Path(entry["manifest"])
    if not manifest.is_file():
        raise SystemExit(f"anchor stage {stage!r} manifest missing: {manifest}")
    return {"accepted_attempt": accepted,
            "attempts": [dict(entry)],
            "input_hash": record.get("input_hash"),
            "status": "accepted"}


def build_leg(leg: dict, anchor: str, dry_run: bool) -> dict:
    anchor_dir = REPO_ROOT / "data" / anchor
    anchor_plan = load(anchor_dir / "raw" / "run_plan.json")
    anchor_state = load(anchor_dir / "workflow_state.json")

    name = leg_name(leg, anchor)
    leg_dir = REPO_ROOT / "data" / name

    plan = json.loads(json.dumps(anchor_plan))
    plan["run_name"] = name
    # Tg only. This is what drops `cooling` from enabled_stages, and it is the whole
    # reason a rate leg costs one sweep instead of a sweep plus a cooldown.
    plan["properties"] = ["tg"]
    plan["decided_params"] = {**plan.get("decided_params", {}), **leg["override"]}
    # Recorded on the plan as well as in decided_params, so the axis is auditable as an
    # override rather than looking like a differently-planned protocol.
    plan["overrides"] = {**(plan.get("overrides") or {}), **leg["override"]}
    plan["tg_sensitivity"] = {"leg": leg["id"], "axis": leg["axis"], "anchor": anchor,
                              "override": leg["override"],
                              "anchor_plan": f"data/{anchor}/raw/run_plan.json",
                              "built_at": now()}

    enabled = track_registry.macro_stages_for(plan["properties"])
    stages = {}
    for stage in enabled:
        stages[stage] = (inherited_stage_record(anchor_state, stage) if stage in INHERITED
                         else {"status": "pending", "attempts": []})

    state = {
        "schema_version": anchor_state.get("schema_version", 1),
        "engine_version": ENGINE_VERSION,
        "run_name": name,
        "plan_hash": _canonical_hash(plan),
        "effective_parameters": dict(plan["decided_params"]),
        "stages": stages,
        "remedy_counters": {"total": 0, "by_id": {}, "by_route": {}},
        "agent_escalations": [],
        "created_at": now(),
        "updated_at": now(),
    }

    melt = load(Path(stages["equilibration"]["attempts"][0]["manifest"]))
    melt_cell = (melt.get("outputs") or {}).get("melt_start_data_path")
    if not melt_cell or not Path(melt_cell).is_file():
        raise SystemExit(f"{name}: anchor's melt_start_data_path is missing: {melt_cell!r}")

    if dry_run:
        print(f"  {name:34s} would fork {anchor} @ {leg['override']}")
        print(f"  {'':34s} melt cell: {melt_cell}")
        return {"leg": leg["id"], "run_name": name, "anchor": anchor, "dry_run": True}

    (leg_dir / "raw").mkdir(parents=True, exist_ok=True)
    (leg_dir / "raw" / "run_plan.json").write_text(json.dumps(plan, indent=2) + "\n")
    (leg_dir / "workflow_state.json").write_text(json.dumps(state, indent=2) + "\n")
    print(f"  {name:34s} <- {anchor} @ {leg['override']}")
    return {"leg": leg["id"], "axis": leg["axis"], "run_name": name, "anchor": anchor,
            "override": leg["override"], "gpu_h": leg["gpu_h"],
            "melt_cell": melt_cell,
            "run_plan": f"data/{name}/raw/run_plan.json"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--only", help="Comma-separated leg ids, e.g. L1,L4")
    parser.add_argument("--anchor-override", action="append", default=[],
                        metavar="FROM=TO", help="Substitute an anchor, e.g. iPMMA_1=PLLA_1")
    args = parser.parse_args()

    manifest = load(MANIFEST)
    subs = dict(pair.split("=", 1) for pair in args.anchor_override)
    legs = manifest["legs"]
    if args.only:
        wanted = {s.strip() for s in args.only.split(",") if s.strip()}
        unknown = wanted - {leg["id"] for leg in legs}
        if unknown:
            parser.error(f"unknown legs: {sorted(unknown)}")
        legs = [leg for leg in legs if leg["id"] in wanted]

    built, skipped = [], []
    for leg in legs:
        anchor = subs.get(leg["anchor"], leg["anchor"])
        state_path = REPO_ROOT / "data" / anchor / "workflow_state.json"
        if not state_path.is_file():
            skipped.append((leg["id"], anchor, "anchor has not run"))
            continue
        if load(state_path)["stages"].get("equilibration", {}).get("status") != "accepted":
            skipped.append((leg["id"], anchor, "anchor equilibration not yet accepted"))
            continue
        built.append(build_leg(leg, anchor, args.dry_run))

    for leg_id, anchor, why in skipped:
        print(f"  {leg_id:4s} SKIPPED -- {anchor}: {why}")

    if built and not args.dry_run:
        out = HERE / "matrix.json"
        out.write_text(json.dumps({"built_at": now(), "legs": built}, indent=2) + "\n")
        print(f"\nwrote {out.relative_to(REPO_ROOT)}")
    print(f"\n{len(built)} leg(s) ready, {len(skipped)} waiting on an anchor"
          + (f", {sum(l.get('gpu_h', 0) for l in built):.2f} GPU-h" if not args.dry_run else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
