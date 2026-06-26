#!/usr/bin/env python3
"""
PreToolUse hook — warn when bash is used for operations covered by mcp-lammps-engine.
Reads the tool call from stdin (JSON), prints a warning if a covered script or direct
lammps invocation is detected, then exits 0 (warn-only, never blocks).
"""
import sys
import json
import re

try:
    data = json.load(sys.stdin)
    tool_input = data.get("tool_input", {})
    cmd = tool_input.get("command", "")
except Exception:
    sys.exit(0)

# BACKGROUND-WAIT launch: a backgrounded sentinel-watch waiter (build_watch_command).
# Detect by the stable tokens that command always echoes. Re-homes the run_log checkpoint
# that the now-removed Monitor PreToolUse hook used to do, AND injects the end-turn contract
# at point-of-use — the exact late-stage failure (acting early after launch). Warn-only.
if tool_input.get("run_in_background") and (
    "PROCESS_DEAD_NO_SENTINEL" in cmd or "RUN_COMPLETE" in cmd
):
    print(
        "BACKGROUND-WAIT launched. (1) Write/update run_log.md SIMULATION STATE now "
        "(status=monitoring, run_id, bg task id). (2) END YOUR TURN — do NOT get_run_status / "
        "spawn the next stage / release a GPU this turn (acting early consumes an incomplete "
        "result). The harness wakes you once on exit."
    )
    sys.exit(0)

SCRIPT_TO_TOOL = [
    ("mda_rdf.py",                      "calculate_rdf"),
    ("mda_end_to_end.py",               "extract_end_to_end_vectors"),
    ("mda_msd.py",                      "calculate_msd"),
    ("mda_radius_of_gyration.py",       "extract_radius_of_gyration"),
    ("mda_orientation_order.py",        "check_orientation_order"),
    ("mda_density_homogeneity.py",      "check_density_homogeneity"),
    ("check_equilibration.py",          "check_equilibration_comprehensive"),
    ("extract_thermal.py",              "extract_thermal"),
    ("extract_bulk_modulus.py",         "extract_bulk_modulus"),
    ("extract_equilibrated_density.py", "extract_equilibrated_density"),
    ("unwrap_dump.py",                  "unwrap_coordinates"),
]

for script, tool in SCRIPT_TO_TOOL:
    if script in cmd:
        print(
            f"TOOL GUARD: '{script}' has an MCP equivalent. "
            f"Use mcp-lammps-engine '{tool}' instead — "
            f"it handles job submission, GPU allocation, monitoring, and output parsing. "
            f"Only proceed with bash if the MCP tool genuinely cannot cover this use case."
        )
        sys.exit(0)

if re.search(r"\blammps\b", cmd) and "lammps-engine" not in cmd and "mcp" not in cmd:
    print(
        "TOOL GUARD: Detected direct LAMMPS invocation via bash. "
        "Use mcp-lammps-engine 'run_lammps_chain' (pipeline) or 'run_lammps_script' (single script) instead — "
        "they manage GPU IDs, nohup, chain restarts, and crash recovery. "
        "Only proceed with bash if submitting a workflow the MCP server cannot handle."
    )
