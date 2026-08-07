#!/usr/bin/env python3
"""
PreToolUse hook — runs nvidia-smi and injects live GPU status right before any
LAMMPS submission call (run_lammps_script, run_lammps_chain,
run_bulk_modulus_series — used by deform-worker, tg-sweep-worker,
equilibration-worker, and murnaghan-worker respectively), so the agent gets
availability info for free instead of needing to remember a separate manual
check.
"""
import json
import subprocess
import sys

try:
    json.load(sys.stdin)
except Exception:
    sys.exit(0)

try:
    out = subprocess.run(
        ["nvidia-smi", "--query-gpu=index,memory.used,memory.free",
         "--format=csv,noheader"],
        capture_output=True, text=True, timeout=10,
    ).stdout.strip()
except Exception:
    sys.exit(0)

if not out:
    sys.exit(0)

print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "additionalContext": (
            f"GPU status (index, memory.used, memory.free) right before submission:\n{out}\n"
            f"Confirm the gpu_ids you're about to pass are actually free before proceeding."
        ),
    }
}))
