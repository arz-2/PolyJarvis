#!/usr/bin/env python3
"""Pre-GPU verification of the Tg sensitivity legs. Runs nothing, claims no GPU.

Seven checks, ordered so the first failure is the one that should stop you:

  1. isolation  -- a leg's decided_params differ from its anchor's in EXACTLY the
                   manifest's override keys, and the seeds are NOT among them. This is
                   the artifact: a leg that moved two things measures neither.
  2. inode      -- every mutable file a leg owns is a distinct inode from the anchor's.
                   Guards the hardlink trap: sharing an inode with the anchor would make
                   writing the leg's plan truncate the anchor's.
  3. stages     -- enabled_stages() is (build, equilibration, thermal, summary): cooling
                   is absent, which is what makes a rate leg cost a sweep not a cooldown.
                   build/equilibration inherited as accepted; thermal/summary pending.
  4. manifest   -- the inherited manifests load and every artifact's sha256 still matches,
                   i.e. the anchor's melt cell is intact. This is the check that catches a
                   disk-retention pass having deleted the cell the leg descends from.
  5. feasible   -- steps_per_T >= tg_min_steps_per_T for the leg's own rate/grid/dt. The
                   planner enforces this at plan time; a fork bypasses the planner.
  6. hash       -- the recorded plan_hash equals _canonical_hash(plan), so _reconcile_plan
                   sees no spurious change and does not invalidate an inherited stage.
  7. cost       -- each leg prices against the manifest's own figure.

Usage:
    python3 benchmarks/tg_sensitivity/verify_matrix.py [--json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))

from workflow_engine import _canonical_hash, file_sha256  # noqa: E402
import rules_common, track_registry  # noqa: E402

SEED_KEYS = {"emc_seed", "velocity_seed"}
EXPECTED_STAGES = ("build", "equilibration", "thermal", "summary")
INHERITED = {"build", "equilibration"}


def load(p: Path) -> dict:
    return json.loads(p.read_text())


def leg_paths(entry: dict) -> tuple[Path, Path]:
    d = REPO_ROOT / "data" / entry["run_name"]
    return d / "raw" / "run_plan.json", d / "workflow_state.json"


def check_isolation(entries, manifest) -> list[str]:
    out = []
    for e in entries:
        plan = load(leg_paths(e)[0])
        anchor = load(REPO_ROOT / "data" / e["anchor"] / "raw" / "run_plan.json")
        ap, lp = anchor["decided_params"], plan["decided_params"]
        changed = {k for k in set(ap) | set(lp) if ap.get(k) != lp.get(k)}
        expected = set(e["override"])
        if changed != expected:
            out.append(f"{e['run_name']}: decided_params changed {sorted(changed)}, "
                       f"expected exactly {sorted(expected)}")
        if changed & SEED_KEYS:
            out.append(f"{e['run_name']}: a seed moved ({sorted(changed & SEED_KEYS)}) -- the "
                       f"axis must be the only thing that varies")
        for key in SEED_KEYS:
            if lp.get(key) != ap.get(key):
                out.append(f"{e['run_name']}: {key} differs from anchor")
    return out


def check_inode(entries) -> list[str]:
    out = []
    for e in entries:
        adir = REPO_ROOT / "data" / e["anchor"]
        for leg_file, anchor_file in ((leg_paths(e)[0], adir / "raw" / "run_plan.json"),
                                      (leg_paths(e)[1], adir / "workflow_state.json")):
            if leg_file.stat().st_ino == anchor_file.stat().st_ino:
                out.append(f"{e['run_name']}: {leg_file.name} SHARES AN INODE with the "
                           f"anchor's -- writing the leg would truncate the anchor")
    return out


def check_stages(entries) -> list[str]:
    out = []
    for e in entries:
        plan_path, state_path = leg_paths(e)
        plan, state = load(plan_path), load(state_path)
        enabled = track_registry.macro_stages_for(plan.get("properties") or ())
        if enabled != EXPECTED_STAGES:
            out.append(f"{e['run_name']}: enabled_stages {enabled} != {EXPECTED_STAGES}")
        if "cooling" in enabled:
            out.append(f"{e['run_name']}: cooling is enabled -- a rate leg would pay for a "
                       f"cooldown it does not need")
        if set(state["stages"]) != set(enabled):
            out.append(f"{e['run_name']}: state stages {sorted(state['stages'])} != "
                       f"enabled {sorted(enabled)}")
        for stage, rec in state["stages"].items():
            want = "accepted" if stage in INHERITED else "pending"
            if rec.get("status") != want:
                out.append(f"{e['run_name']}: stage {stage} is {rec.get('status')!r}, want {want!r}")
    return out


def check_manifest(entries) -> list[str]:
    """The anchor's melt cell must still be byte-identical to what it was accepted as."""
    out = []
    for e in entries:
        state = load(leg_paths(e)[1])
        for stage in INHERITED:
            rec = state["stages"][stage]
            path = Path(rec["attempts"][0]["manifest"])
            if not path.is_file():
                out.append(f"{e['run_name']}: {stage} manifest missing: {path}")
                continue
            for art in load(path).get("artifacts", []):
                ap = Path(art["path"])
                if not ap.is_absolute():
                    ap = path.parent / ap
                if not ap.is_file():
                    out.append(f"{e['run_name']}: {stage} artifact GONE: {ap}")
                elif file_sha256(ap) != art["sha256"]:
                    out.append(f"{e['run_name']}: {stage} artifact CHANGED: {ap}")
    return out


def check_feasible(entries) -> list[str]:
    """steps_per_T = t_step / (rate * dt * 1e-6), floored at the class's tg_min_steps_per_T."""
    out = []
    classes = rules_common.load_rules()["classes"]
    for e in entries:
        plan = load(leg_paths(e)[0])
        dp = plan["decided_params"]
        cls = classes.get(plan.get("polymer_class"), {})
        rate, step = dp.get("tg_rate_K_per_ns"), dp.get("tg_t_step_K")
        dt = dp.get("dt_fs") or cls.get("dt_fs", 1.0)
        floor = dp.get("tg_min_steps_per_T", cls.get("tg_min_steps_per_T", 200000))
        if not rate or not step:
            out.append(f"{e['run_name']}: no rate/grid to check ({rate!r}/{step!r})")
            continue
        steps = int(step / (rate * dt * 1e-06))
        if steps < floor:
            out.append(f"{e['run_name']}: {steps} steps/T < floor {floor} "
                       f"(t_step={step} K, rate={rate} K/ns, dt={dt} fs). Raise the grid or "
                       f"lower the rate -- do NOT lower tg_min_steps_per_T.")
    return out


def check_hash(entries) -> list[str]:
    out = []
    for e in entries:
        plan, state = load(leg_paths(e)[0]), load(leg_paths(e)[1])
        if state.get("plan_hash") != _canonical_hash(plan):
            out.append(f"{e['run_name']}: plan_hash stale -- _reconcile_plan would fire and "
                       f"could invalidate an inherited stage")
        if state.get("effective_parameters") != plan.get("decided_params"):
            out.append(f"{e['run_name']}: effective_parameters != decided_params")
    return out


def check_cost(entries, manifest) -> tuple[list[str], float]:
    priced = {leg["id"]: leg["gpu_h"] for leg in manifest["legs"]}
    total = sum(priced.get(e["leg"], 0.0) for e in entries)
    missing = [f"{e['run_name']}: leg {e['leg']} not priced in MANIFEST"
               for e in entries if e["leg"] not in priced]
    return missing, total


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    manifest = load(HERE / "MANIFEST.json")
    matrix_path = HERE / "matrix.json"
    if not matrix_path.is_file():
        print("no matrix.json -- run build_matrix.py first")
        return 1
    entries = load(matrix_path)["legs"]
    if not entries:
        print("matrix.json has no legs")
        return 1

    cost_failures, total = check_cost(entries, manifest)
    results = {
        "isolation": check_isolation(entries, manifest),
        "inode": check_inode(entries),
        "stages": check_stages(entries),
        "manifest": check_manifest(entries),
        "feasible": check_feasible(entries),
        "hash": check_hash(entries),
        "cost": cost_failures,
    }
    failed = sum(len(v) for v in results.values())
    if args.json:
        print(json.dumps({"failures": results, "legs": len(entries),
                          "priced_gpu_hours": round(total, 2)}, indent=2))
    else:
        for name, fails in results.items():
            print(f"{'FAIL' if fails else 'PASS'}  {name}" + (f" ({len(fails)})" if fails else ""))
            for f in fails:
                print(f"      {f}")
        print(f"\n{len(entries)} leg(s), {total:.2f} priced GPU-hours "
              f"(LOWER BOUND -- tg_per_t_max_extensions=2 per bin is unpriced)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
