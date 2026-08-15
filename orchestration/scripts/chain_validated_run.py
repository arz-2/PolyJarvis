#!/usr/bin/env python3
"""
chain_validated_run.py — one command from "a novel system finished validating" to a completed
replicate. Chains every script in the path so none of them has to be invoked by hand:

  1. verify_protocol_replay.py     regenerate the source run's decks from its own plan and diff
  2. write_characterization_cache.py --lock --plan
                                   freeze, per track, gated on physical validity AND (1)
  3. make_deterministic_plan.py --canonical_smiles
                                   write the deterministic plan, built from what actually ran,
                                   carrying the resolved execution_chain
  4. run_deterministic_replicate.py
                                   execute that chain end to end

Each step's refusal stops the chain and is reported with the reason — a refusal at (1) or (2)
means the source run's recorded protocol is not the one it executed, which is exactly when a
replicate must not be launched.

Usage:
  chain_validated_run.py --source-run PLA1 --run_name PLA2 --polymer_class PEST \
      --smiles "*OC(C)C(=O)*" [--properties density,tg] [--no-run] [--seed-mode both|velocity]

--no-run stops after step 3 with a ready-to-run plan.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS = REPO_ROOT / "orchestration" / "scripts"
VENV_PY = REPO_ROOT / "mcp-servers" / ".venv" / "bin" / "python"


def _py() -> str:
    return str(VENV_PY) if VENV_PY.exists() else sys.executable


def _run(cmd: list, label: str) -> tuple:
    """Run one link of the chain. Returns (ok, parsed_json_or_raw)."""
    proc = subprocess.run([_py()] + cmd, capture_output=True, text=True)
    out = proc.stdout.strip()
    try:
        # These scripts print a JSON summary; some also print INFO lines to stdout first.
        parsed = json.loads(out[out.index("{"):]) if "{" in out else {}
    except (ValueError, json.JSONDecodeError):
        parsed = {"raw": out[-2000:]}
    return proc.returncode == 0, parsed


def canonical(smiles: str) -> str:
    ok, res = _run([str(SCRIPTS / "canon_smiles.py"), smiles], "canon")
    return (res or {}).get("canonical_smiles") or smiles


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--source-run", required=True,
                    help="The fully-validated novel run whose protocol to freeze and replicate.")
    ap.add_argument("--run_name", required=True, help="Name for the new replicate run.")
    ap.add_argument("--polymer_class", required=True)
    ap.add_argument("--smiles", required=True)
    ap.add_argument("--properties", default="all")
    ap.add_argument("--seed-mode", choices=["both", "velocity"], default="both")
    ap.add_argument("--no-run", action="store_true",
                    help="Stop after writing the plan; do not launch the replicate.")
    ap.add_argument("--emit-decks", metavar="DIR",
                    help="Run every link, but have step 4 generate decks instead of submitting. "
                         "Exercises the whole chain without consuming GPU-hours or disk.")
    ap.add_argument("--data-file", default=None, help="--emit-decks only: starting .data file.")
    ap.add_argument("--params-file", default=None, help="--emit-decks only: EMC .params file.")
    ap.add_argument("--skip-freeze", action="store_true",
                    help="The source run is already frozen; start at step 3.")
    a = ap.parse_args()

    src_dir = REPO_ROOT / "data" / a.source_run
    src_plan = src_dir / "raw" / "run_plan.json"
    smiles_canon = canonical(a.smiles)
    steps = []

    def fail(step, detail):
        steps.append({"step": step, "status": "refused", "detail": detail})
        print(json.dumps({"status": "halted", "at": step, "steps": steps,
                          "canonical_smiles": smiles_canon}, indent=2))
        sys.exit(1)

    if not a.skip_freeze:
        if not src_plan.exists():
            fail("verify_replay", f"no run_plan.json under {src_dir}")

        # 1. Deck replay — is the source run's recorded protocol the one it ran?
        ok, replay = _run([str(SCRIPTS / "verify_protocol_replay.py"),
                           "--run_dir", str(src_dir), "--json"], "replay")
        steps.append({"step": "verify_replay", "status": replay.get("status"),
                      "tracks": replay.get("tracks")})
        if replay.get("status") == "refused":
            fail("verify_replay", replay)

        # 2. Freeze, per track, on physical validity + the replay result.
        props = "" if a.properties == "all" else a.properties
        ok, lock = _run([str(SCRIPTS / "write_characterization_cache.py"), "--lock",
                         "--smiles", smiles_canon, "--run_name", a.source_run,
                         "--properties", props or "density,tg,bulk_modulus",
                         "--plan", str(src_plan)], "lock")
        steps.append({"step": "freeze_protocol", "status": "ok" if ok else "refused",
                      "tracks_frozen": lock.get("protocol_tracks_frozen"),
                      "reason": lock.get("reason")})
        if not ok:
            fail("freeze_protocol", lock)

    # 3. Deterministic plan, built from the frozen protocol, carrying the execution chain.
    ok, plan_res = _run([str(SCRIPTS / "make_deterministic_plan.py"),
                         "--run_name", a.run_name, "--polymer_class", a.polymer_class,
                         "--smiles", a.smiles, "--canonical_smiles", smiles_canon,
                         "--properties", a.properties], "plan")
    plan_path = plan_res.get("run_plan")
    steps.append({"step": "write_plan", "status": "ok" if ok else "failed",
                  "run_plan": plan_path, "plan_mode": plan_res.get("plan_mode")})
    if not ok or not plan_path:
        fail("write_plan", plan_res)

    frozen = json.loads(Path(plan_path).read_text()).get("frozen_protocol") or {}
    steps[-1]["frozen_tracks"] = sorted(frozen)
    if not frozen:
        fail("write_plan", {"reason": "plan carries no frozen_protocol — it would replicate "
                                      "class defaults, not this molecule's protocol"})

    if a.no_run:
        print(json.dumps({"status": "plan_ready", "run_plan": plan_path, "steps": steps,
                          "next": f"run_deterministic_replicate.py --run_name {a.run_name} "
                                  f"--polymer_class {a.polymer_class} --plan {plan_path}"},
                         indent=2))
        return

    # 4. Execute the chain end to end. Streamed, not captured: this runs for hours and its
    # progress must reach the caller as it happens.
    cmd = [_py(), str(SCRIPTS / "run_deterministic_replicate.py"),
           "--run_name", a.run_name, "--polymer_class", a.polymer_class,
           "--plan", plan_path, "--seed-mode", a.seed_mode]
    if a.emit_decks:
        cmd += ["--emit-decks", a.emit_decks]
        if a.data_file:
            cmd += ["--data-file", a.data_file]
        if a.params_file:
            cmd += ["--params-file", a.params_file]
    elif a.seed_mode == "velocity":
        cmd += ["--source-run", a.source_run]
    print(json.dumps({"status": "executing", "steps": steps, "cmd": " ".join(cmd)}, indent=2),
          flush=True)
    rc = subprocess.run(cmd).returncode
    steps.append({"step": "execute", "status": "ok" if rc == 0 else "failed", "returncode": rc})
    print(json.dumps({"status": "complete" if rc == 0 else "failed",
                      "run_name": a.run_name, "steps": steps}, indent=2))
    sys.exit(rc)


if __name__ == "__main__":
    main()
