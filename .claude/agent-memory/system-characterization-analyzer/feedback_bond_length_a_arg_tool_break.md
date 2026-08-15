---
name: feedback-bond-length-a-arg-tool-break
description: check_equilibration_comprehensive MCP tool broke mid-session (passes --bond_length_A that a concurrent refactor removed from the analysis script)
metadata:
  type: project
---

2026-08-14, PLA1 run: the loaded `mcp-lammps-engine` server for `check_equilibration_comprehensive`
passed `--bond_length_A` to `analysis_scripts/check_equilibration_comprehensive.py`, which a
concurrent session had removed that argument from at 13:29 the same day. The tool is unusable until
the server process is restarted against the current script (or the script/server are reconciled).
Orchestrator worked around it by running the on-disk script directly and handing this agent the
precomputed JSON result instead of a live tool call — that workaround is recorded in this run's
`run_log.md` RECOVERY block, not duplicated here.

**Why:** cross-session concurrent edits to a script the MCP server subprocess-calls with fixed flags
is a known failure mode (see repo-wide `feedback_concurrent_session_silent_edit_loss` memory
pattern in other agents) — a live server can silently go stale against its own script.

**How to apply:** if `check_equilibration_comprehensive` errors on an unrecognized/missing
`--bond_length_A` (or similar) flag, don't retry blindly — check whether the on-disk analysis
script's argument list has diverged from what the loaded server passes, and if the orchestrator has
already supplied a precomputed result file, read and trust it rather than re-attempting the broken
tool call.
