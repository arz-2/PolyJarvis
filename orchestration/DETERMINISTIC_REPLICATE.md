# Deterministic replicate guide (Phase A/B, `plan_mode=="deterministic"`) — orchestrator-read

Read this instead of `FOUNDATION.md`/`THERMAL_TRACK.md`/`MECHANICAL_TRACK.md` for Phase A/B once
`CLAUDE.md`'s PLAN step has produced a `plan_mode=="deterministic"` `run_plan.json`
(`confidence=="high"` for this class — the protocol is already validated). `SUMMARY.md`'s Phase C
is unchanged either way; the executor produces the same `raw/*.json` artifacts those steps already
consume.

**Why this exists:** every execution-stage worker (molecule-builder, equilibration-worker,
equilibration-checker, tg-sweep-worker, tg-analysis-worker, murnaghan-worker, deform-worker,
bulk-modulus-extractor, exp-lookup-worker, run-summary-worker) used to spawn as a full Claude
subagent every single run, confidence=high or not — its prompt was byte-identical every time and
it made no real judgment call. `orchestration/run_deterministic_replicate.py` replaces that
~10-agent-spawn chain with one plain Python process that calls the same underlying MCP-server
functions directly (verified safe: FastMCP's `@mcp.tool()` returns the original function
unchanged; `mcp-lammps-engine/tests/test_watch_run.py` already imports `server.py` directly as
precedent). It consumes `orchestration/gen_prompt.py`'s `resolve_stage_params()` — the same
per-stage parameter resolution the agent-prompt text path uses — so a routing bug fix in
`gen_prompt.py` can never silently diverge between the two paths.

## Invocation — one or two phases, split at the system-probe boundary

A plain script cannot spawn `Agent(...)`. The system-probe agent trio
(`system-probe-worker`/`system-probe-analyzer`/post-probe `critic`) must still run inside the live
orchestrator session when this SMILES is novel — `FOUNDATION.md`'s `[System probe]` and
`[Post-probe critic review]` sections govern that, **unchanged**, regardless of confidence. The
Novelty Gate (`CLAUDE.md` SETUP) already determines `IS_NOVEL` before Phase A starts, so the split
point is known up front:

- **`IS_NOVEL=false`** (the common replicate-2+ case — this exact SMILES was already probed on an
  earlier run): one invocation, end to end.
  ```
  <repo>/mcp-servers/.venv/bin/python orchestration/run_deterministic_replicate.py \
      --run_name <RUN> --polymer_class <CLASS> --plan PLAN_PATH
  ```
  Write SIMULATION STATE to run_log.md (status=monitoring), launch this detached
  (`Bash(command="nohup <cmd> & disown", run_in_background=true)`), then **BACKGROUND-WAIT**
  (canonical pattern, `CLAUDE.md`) on its own completion — the script blocks internally through
  every stage and prints one final JSON line (`{"status": "complete", ...}` or
  `{"status": "halted", ...}`) on exit. One `BACKGROUND-WAIT` for the whole multi-hour replicate,
  down from ~10.

- **`IS_NOVEL=true`**: two invocations.
  1. `--phase build_only` — submits the build, stops, prints `{"status": "build_only_complete",
     "data_path": ..., "n_atoms": ...}`. BACKGROUND-WAIT on this (short) invocation.
  2. Run `FOUNDATION.md`'s `[System probe]` → `[Post-probe critic review]` exactly as documented
     there, against the `data_path` from step 1's output — no changes to that agent sequence.
  3. Once the post-probe critic approves (`decided_params` is now probe-patched in `PLAN_PATH`),
     re-invoke: `... run_deterministic_replicate.py --run_name <RUN> --polymer_class <CLASS>
     --plan PLAN_PATH --resume-from equil` — `executor_state.json` already has `build` marked
     `done`, so this picks up at Equilibration. BACKGROUND-WAIT on this second, longer invocation.

  `FOUNDATION.md`'s optional `refine_from_equil` re-probe (a third, optional probe-analyzer
  re-spawn after equil-check PASSes, upgrading BM-sensitive knobs from the real chain's longer
  hold) is **not supported on this path** — it would need a third phase split for marginal value.
  Skip it for `plan_mode=="deterministic"` runs; it remains available on the reasoned path.

## Resumability

`data/<RUN>/raw/executor_state.json` tracks per-stage status (`build`, `equil_check`, `thermal`,
`mechanical`, `summary`). A stage marked `"done"` is never re-run. On session restart mid-replicate:
read this file the same way `CLAUDE.md`'s existing SIMULATION STATE restart protocol reads the
run_log table — find the first stage that isn't `"done"`, and if the background process is no
longer running (`get_run_status`/process check), just re-invoke the same command (no
`--resume-from` needed — the script self-determines the resume point from this file).

## Halt contract — never auto-changes a locked protocol

Recovery scope matches `.claude/commands/recover.md`'s `plan_mode=="deterministic"` rule exactly:
only EXTEND-type recovery (a parameter tweak that never touches `decided_params`, e.g. a longer
300 K hold) auto-applies, capped at 2 attempts. Any of the following halts immediately — the
script prints `{"status": "halted", "stage": ..., "detail": ...}` and exits without submitting
anything further:
- `equil_verdict == STRUCTURAL_FAIL` (or `FAIL`), or EXTEND exhausted at 2 attempts
- a glassy slope-gate failure with no `tg_slope_gate_fallback` named for the class
- (implicitly, via the artifact-shape check in `enforce_gate.py`'s retrospective mode) any stage
  whose `run_log.md` write didn't land cleanly

On a halt, `executor_state.json["halted"]` carries the stage, reason, and full diagnostic detail
(the same fields `enforce_equilibration_gate`/multirate results already return) — write this to
`run_log.md` as a "protocol did not reproduce on this seed" finding and surface for human review,
per `recover.md`'s deterministic-mode rule. Do **not** re-invoke with a changed protocol; changing
`decided_params` on a locked replicate breaks the fixed-protocol-across-replicates invariant the
whole campaign depends on.

## Scope

EMC build path only (18 of ~19 supported classes). `PURA` (the one RadonPy-only class —
`preferred_builder != "emc"`) is not yet supported by the scripted path; `do_build()` raises a
clear error rather than attempting it. Run PURA through the normal agent-driven pipeline
(confidence=high still skips planner/critic via `CLAUDE.md`'s existing shortcut; only the
execution-stage agent spawns still happen for this one class, for now).
