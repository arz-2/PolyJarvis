#!/usr/bin/env python3
"""Pre-GPU verification of the stereo_r2 matrix. Runs nothing, claims no GPU.

Six checks, in the order a failure should stop you:

  1. class      -- the polymer_class each plan was built with is the one the manifest states,
                   and the divergence from polyinfo_classifier is the documented one.
  2. structural -- validate_run_plan.py reports no finding above `info`.
  3. identity   -- within a system, replicate plans differ ONLY in run_name and the two
                   seeds. This is the artifact that answers reviewer comment 1.
  4. seeds      -- all 42 distinct, in range, and reproducible from the recorded master_seed.
  5. pins       -- every override in the manifest actually reached decided_params.
  6. cost       -- every plan prices, and the Murnaghan series is sized for all 7.

Usage:
    python3 benchmarks/stereo_r2/verify_matrix.py [--json]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from build_matrix import REPLICATE_VARYING, REPLICATES, diff_keys, seed_for  # noqa: E402

# validate_run_plan grades findings; anything above this is a reason not to launch.
ACCEPTABLE_SEVERITIES = {"info"}


def load(path: Path) -> dict:
    return json.loads(path.read_text())


def plan_path(run_name: str) -> Path:
    return REPO_ROOT / "data" / run_name / "raw" / "run_plan.json"


def check_class(manifest: dict) -> list[str]:
    failures = []
    for name, spec in manifest["systems"].items():
        for replicate in REPLICATES:
            plan = load(plan_path(f"{name}_{replicate}"))
            got = plan.get("polymer_class")
            if got != spec["polymer_class"]:
                failures.append(f"{name}_{replicate}: polymer_class {got!r} != "
                                f"{spec['polymer_class']!r}")
        if spec["classifier_says"] != spec["polymer_class"] and \
                "class_divergence_reason" not in spec:
            failures.append(f"{name}: classifier disagrees ({spec['classifier_says']}) with "
                            f"no recorded reason")
    return failures


def check_structural(manifest: dict) -> list[str]:
    """Scoped to this matrix's runs. data/ also holds older campaigns on schema 1.0, and
    their findings are not this campaign's business."""
    failures = []
    for name in manifest["systems"]:
      for replicate in REPLICATES:
        run_name = f"{name}_{replicate}"
        path = plan_path(run_name)
        proc = subprocess.run(
            [sys.executable, "orchestration/scripts/validate_run_plan.py",
             "--run_plan", str(path)],
            cwd=str(REPO_ROOT), capture_output=True, text=True)
        if proc.returncode != 0:
            failures.append(f"{run_name}: validator exited {proc.returncode}")
            continue
        for finding in json.loads(proc.stdout).get("findings", []):
            if finding.get("severity") not in ACCEPTABLE_SEVERITIES:
                failures.append(f"{run_name}: {finding.get('severity')} "
                                f"{finding.get('check')} -- {finding.get('detail','')[:120]}")
    return failures


def check_identity(manifest: dict) -> list[str]:
    failures = []
    for name in manifest["systems"]:
        first = load(plan_path(f"{name}_1"))
        for replicate in REPLICATES[1:]:
            other = load(plan_path(f"{name}_{replicate}"))
            changed = {path.split(".")[-1] for path in diff_keys(first, other)}
            unexpected = changed - REPLICATE_VARYING
            if unexpected:
                failures.append(f"{name}_{replicate}: differs from {name}_1 in "
                                f"{sorted(unexpected)}")
            if changed != REPLICATE_VARYING:
                missing = REPLICATE_VARYING - changed
                if missing:
                    failures.append(f"{name}_{replicate}: did NOT differ in {sorted(missing)} "
                                    f"-- a replicate sharing a seed is not a replicate")
    return failures


def check_seeds(manifest: dict) -> list[str]:
    failures, seen = [], {}
    master = manifest["master_seed"]
    for name in manifest["systems"]:
        for replicate in REPLICATES:
            run_name = f"{name}_{replicate}"
            decided = load(plan_path(run_name))["decided_params"]
            for kind, key in (("emc", "emc_seed"), ("velocity", "velocity_seed")):
                value = decided.get(key)
                expected = seed_for(master, name, replicate, kind)
                if value != expected:
                    failures.append(f"{run_name}.{key}={value} is not reproducible from "
                                    f"master_seed {master} (expected {expected})")
                if not isinstance(value, int) or not 1 <= value <= 999_999_999:
                    failures.append(f"{run_name}.{key}={value!r} outside the allowed range")
                if value in seen:
                    failures.append(f"{run_name}.{key} collides with {seen[value]}")
                seen[value] = f"{run_name}.{key}"
    return failures


def check_pins(manifest: dict) -> list[str]:
    failures = []
    for name, spec in manifest["systems"].items():
        decided = load(plan_path(f"{name}_1"))["decided_params"]
        for key, value in (spec.get("overrides") or {}).items():
            if decided.get(key) != value:
                failures.append(f"{name}: pinned {key}={value!r} but decided_params says "
                                f"{decided.get(key)!r}")
    return failures


def check_builds(manifest: dict) -> list[str]:
    """~5 s per system. The only check here that runs the real front end."""
    sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))
    import forcefield, rules_common  # noqa: PLC0415 -- needs the mol env on sys.path first
    classes = rules_common.load_rules()["classes"]
    failures = []
    for name, spec in manifest["systems"].items():
        field = load(plan_path(f"{name}_1"))["decided_params"]["preferred_ff"]
        prior = classes[spec["polymer_class"]].get("ff_accuracy_prior")
        if field != prior:
            failures.append(f"{name}: plan field {field!r} != class prior {prior!r} -- "
                            f"check this was a deliberate override")
        result = forcefield.check_typing(spec["smiles"], field)
        if not result["types_smiles"]:
            failures.append(f"{name}: {field} cannot build {spec['smiles']} -- "
                            f"{str(result['typing_error'])[:140]}")
    return failures


def check_cost(manifest: dict) -> tuple[list[str], float]:
    failures, total = [], 0.0
    for name in manifest["systems"]:
        for replicate in REPLICATES:
            run_name = f"{name}_{replicate}"
            cost = load(plan_path(run_name)).get("cost_estimate") or {}
            hours = cost.get("total_gpu_hours")
            if hours is None:
                failures.append(f"{run_name}: unpriceable (total_gpu_hours is null)")
                continue
            total += hours
            unpriced = [s for s in (cost.get("unpriced_stages") or [])
                        if "murnaghan" in str(s)]
            if unpriced:
                failures.append(f"{run_name}: Murnaghan series not sized -- {unpriced}")
    return failures, total


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    manifest = load(HERE / "MANIFEST.json")
    cost_failures, total_hours = check_cost(manifest)
    results = {
        "class": check_class(manifest),
        "structural": check_structural(manifest),
        "identity": check_identity(manifest),
        "seeds": check_seeds(manifest),
        "pins": check_pins(manifest),
        "cost": cost_failures,
        "builds": check_builds(manifest),
    }
    failed = sum(len(v) for v in results.values())

    if args.json:
        print(json.dumps({"failures": results,
                          "priced_gpu_hours_total": round(total_hours, 2)}, indent=2))
    else:
        for check, failures in results.items():
            print(f"{'FAIL' if failures else 'PASS'}  {check}"
                  + (f" ({len(failures)})" if failures else ""))
            for failure in failures:
                print(f"      {failure}")
        print(f"\npriced GPU-hours across the matrix: {total_hours:.1f} "
              f"(LOWER BOUND -- equilibration is never priced, see select_hardware.py)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
