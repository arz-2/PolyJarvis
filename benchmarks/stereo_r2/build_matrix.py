#!/usr/bin/env python3
"""Build the stereo_r2 benchmark matrix: 7 systems x 3 seeded replicates.

One canonical plan per system, then three run directories whose plans differ from it in
exactly the run name and the two seeds. That last property is the artifact answering
reviewer comment 1, so it is asserted here rather than left to inspection.

Order matters and is not negotiable:

  1. Every plan is generated BEFORE any campaign executes. make_deterministic_plan's
     _try_cache replays guides/system_characterization_cache.json keyed by isomeric
     canonical SMILES; once a replicate completes, write_characterization_cache populates
     it and a later run-plan for the same SMILES replays the cache instead of planning.
  2. Seeds are pinned before the first non-dry-run of a run dir. workflow_state.json's
     plan_hash is written on first real execution (workflow_engine._reconcile_plan); a
     seed edit after that invalidates stage state.
  3. Execution is via `agent_api.py resume <RUN>`, never `start`. resume calls
     run_campaign_workflow directly and does NOT re-materialize -- no re-solve of system
     size, no re-probe of D-01, no re-read of the class table. Re-materializing per
     replicate is exactly the drift vector revision.md section A blames for round 1.

Usage:
    python3 benchmarks/stereo_r2/build_matrix.py [--dry-run] [--only iPMMA,PE]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
MANIFEST = HERE / "MANIFEST.json"
PLANS = HERE / "plans"
REPLICATES = (1, 2, 3)

# The only keys allowed to differ between a system's replicates. Anything else means the
# fixed-protocol claim is false for that system.
REPLICATE_VARYING = {"run_name", "emc_seed", "velocity_seed"}


def seed_for(master: int, system: str, replicate: int, kind: str) -> int:
    """Reproducible from the single recorded master_seed, distinct per (system, rep, kind).

    Deliberately NOT the run_name sha256 fallback in run_campaign.py:314 /
    stage_params.py:406: those produce distinct seeds too, but implicitly. A campaign that
    claims independent seeds has to be able to state them.
    """
    digest = hashlib.sha256(f"{master}|{system}|{replicate}|{kind}".encode()).hexdigest()
    return 1 + int(digest, 16) % 999_999_999


def run(cmd: list[str], *, cwd: Path = REPO_ROOT) -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
    if proc.returncode != 0:
        sys.stderr.write(f"FAILED: {' '.join(cmd)}\n{proc.stdout}\n{proc.stderr}\n")
    return proc


def make_scaffold(name: str, spec: dict) -> Path:
    """Deterministic plan, class passed explicitly, no LLM in the loop.

    --polymer_class is stated rather than classified: polyinfo_classifier returns PHAL for
    the sPVC dyad (see MANIFEST.polymer_class_is_passed_explicitly).
    """
    out = PLANS / f"{name}.scaffold.json"
    proc = run([sys.executable, "orchestration/scripts/make_deterministic_plan.py", "run-plan",
                "--run_name", f"{name}_1", "--polymer_class", spec["polymer_class"],
                "--smiles", spec["smiles"], "--properties", "density,tg,bulk_modulus",
                "--with-ff-probe", "--baseline", "--out", str(out), "--force"])
    proc.check_returncode()
    return out


def materialize(name: str, replicate: int, spec: dict, plan_in: Path) -> Path:
    """agent_api start --dry-run: writes raw/run_plan.json and stops before WorkflowEngine.

    Nothing under data/<run>/attempts is created and no GPU is claimed
    (run_campaign.run_campaign_workflow returns resolved stage params on dry_run).
    """
    run_name = f"{name}_{replicate}"
    proc = run([sys.executable, "orchestration/scripts/agent_api.py", "start",
                "--run-name", run_name, "--smiles", spec["smiles"],
                "--properties", "density,tg,bulk_modulus",
                # Identical across replicates on purpose: the goal is part of the frozen
                # protocol, and a replicate index in it would show up in the identity diff.
                "--goal", f"density, Tg and bulk modulus for {spec['polymer']} "
                          f"({spec['stereochemistry']}), stereo_r2",
                "--plan", str(plan_in), "--dry-run"])
    proc.check_returncode()
    return REPO_ROOT / "data" / run_name / "raw" / "run_plan.json"


def seeded_copy(canonical: dict, name: str, replicate: int, master: int, dest: Path) -> dict:
    """Canonical plan + this replicate's identity. Five edits, no more.

    run_name is written in both places it can be read from: run_campaign_workflow reads
    plan["run_name"], NOT the directory name, so a stale value silently mislabels the
    replicate and re-points its work dirs.
    """
    plan = json.loads(json.dumps(canonical))
    plan["run_name"] = f"{name}_{replicate}"
    for kind, key in (("emc", "emc_seed"), ("velocity", "velocity_seed")):
        value = seed_for(master, name, replicate, kind)
        plan.setdefault("overrides", {})[key] = value
        plan.setdefault("decided_params", {})[key] = value
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(plan, indent=2))
    return plan


def diff_keys(a: dict, b: dict, prefix: str = "") -> set[str]:
    """Leaf-level key paths whose values differ. Used for the replicate identity assertion."""
    keys = set(a) | set(b)
    out: set[str] = set()
    for key in keys:
        path = f"{prefix}{key}"
        left, right = a.get(key), b.get(key)
        if isinstance(left, dict) and isinstance(right, dict):
            out |= diff_keys(left, right, path + ".")
        elif left != right:
            out.add(path)
    return out


def build_system(name: str, spec: dict, master: int, dry_run: bool) -> dict:
    print(f"=== {name} ({spec['polymer_class']}, {spec['stereochemistry']})")
    scaffold_path = make_scaffold(name, spec)
    scaffold = json.loads(scaffold_path.read_text())

    # The overrides ride on the plan's own top-level `overrides` block, which
    # PlanDecision.from_run_plan reads and materialize_plan merges into decided_params
    # after validate_overrides. Editing decided_params directly would skip both the
    # whitelist and the derived-parameter bindings.
    scaffold["overrides"] = dict(scaffold.get("overrides") or {})
    scaffold["overrides"].update(spec.get("overrides") or {})
    scaffold_path.write_text(json.dumps(scaffold, indent=2))

    canonical_out = PLANS / f"{name}_canonical.json"
    if dry_run:
        print(f"    dry-run: would materialize {name}_1..3")
        return {"system": name, "skipped": True}

    materialized = materialize(name, 1, spec, scaffold_path)
    canonical = json.loads(materialized.read_text())
    shutil.copy(materialized, canonical_out)
    print(f"    canonical -> {canonical_out.relative_to(REPO_ROOT)}")

    records = []
    for replicate in REPLICATES:
        staged = PLANS / "_seeded" / f"{name}_{replicate}.json"
        plan = seeded_copy(canonical, name, replicate, master, staged)
        out_path = materialize(name, replicate, spec, staged)
        final = json.loads(out_path.read_text())
        records.append({
            "run_name": final["run_name"],
            "emc_seed": final["decided_params"]["emc_seed"],
            "velocity_seed": final["decided_params"]["velocity_seed"],
            "run_plan": str(out_path.relative_to(REPO_ROOT)),
            "total_gpu_hours": (final.get("cost_estimate") or {}).get("total_gpu_hours"),
        })
        print(f"    {final['run_name']}: emc_seed={records[-1]['emc_seed']} "
              f"velocity_seed={records[-1]['velocity_seed']}")

    # The fixed-protocol assertion, made here so a violation never reaches a GPU.
    first = json.loads((REPO_ROOT / records[0]["run_plan"]).read_text())
    for record in records[1:]:
        other = json.loads((REPO_ROOT / record["run_plan"]).read_text())
        changed = {path.split(".")[-1] for path in diff_keys(first, other)}
        unexpected = changed - REPLICATE_VARYING
        if unexpected:
            raise SystemExit(f"{name}: replicates differ beyond seeds and run name: "
                             f"{sorted(unexpected)}")
    print(f"    identity check: replicates differ only in {sorted(REPLICATE_VARYING)}")
    return {"system": name, "polymer_class": spec["polymer_class"],
            "smiles": spec["smiles"], "stereochemistry": spec["stereochemistry"],
            "canonical_plan": str(canonical_out.relative_to(REPO_ROOT)),
            "replicates": records}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="Generate scaffolds only; do not materialize run directories.")
    parser.add_argument("--only", default=None, help="Comma-separated system ids.")
    args = parser.parse_args()

    manifest = json.loads(MANIFEST.read_text())
    master = manifest["master_seed"]
    systems = manifest["systems"]
    if args.only:
        wanted = {s.strip() for s in args.only.split(",") if s.strip()}
        unknown = wanted - set(systems)
        if unknown:
            parser.error(f"unknown systems: {sorted(unknown)}")
        systems = {k: v for k, v in systems.items() if k in wanted}

    PLANS.mkdir(parents=True, exist_ok=True)
    built = [build_system(name, spec, master, args.dry_run) for name, spec in systems.items()]

    seeds = [(r["emc_seed"], r["velocity_seed"])
             for entry in built for r in entry.get("replicates", [])]
    flat = [value for pair in seeds for value in pair]
    if len(set(flat)) != len(flat):
        raise SystemExit("seed collision across the matrix")
    print(f"\n{len(seeds)} run directories, {len(set(flat))} distinct seeds")

    out = HERE / "matrix.json"
    out.write_text(json.dumps({"master_seed": master, "systems": built}, indent=2))
    print(f"wrote {out.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
