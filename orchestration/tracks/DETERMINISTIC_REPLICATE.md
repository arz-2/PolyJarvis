# Deterministic replicate guide (Phase A/B, `plan_mode=="deterministic"`) — orchestrator-read

Read this instead of `FOUNDATION.md`/`THERMAL_TRACK.md`/`MECHANICAL_TRACK.md` for Phase A/B once
`CLAUDE.md`'s PLAN step has produced a `plan_mode=="deterministic"` `run_plan.json`
(this exact canonical SMILES's `guides/system_characterization_cache.json` entry has
`protocol_validated==true` covering the requested properties — the protocol is already
validated for THIS molecule, never a class-level signal). `SUMMARY.md`'s Phase C
is unchanged either way; the executor produces the same `raw/*.json` artifacts those steps already
consume.

## Invocation

One invocation, end to end:
```
<repo>/mcp-servers/.venv/bin/python orchestration/scripts/run_deterministic_replicate.py \
    --run_name <RUN> --polymer_class <CLASS> --plan PLAN_PATH
```
Write SIMULATION STATE to run_log.md (status=monitoring), launch this detached
(`Bash(command="nohup <cmd> & disown", run_in_background=true)`), then **BACKGROUND-WAIT**
(canonical pattern, `CLAUDE.md`) on its own completion — the script blocks internally through
every stage and prints one final JSON line (`{"status": "complete", ...}` or
`{"status": "halted", ...}`) on exit.

This path's SMILES is always already covered by a `system_characterization_cache.json` entry
(that's what `protocol_validated==true`, required for `plan_mode=="deterministic"`, implies) —
`system-characterization-analyzer` is a reasoned-path-only step (`FOUNDATION.md`'s
`[Equilibration]` mandatory refine, for `IS_NOVEL=true` runs that are *not* deterministic); this
script never spawns it.

## Resumability

`data/<RUN>/raw/executor_state.json` tracks per-stage status (`build`, `equil_check`, `thermal`,
`mechanical`, `summary`). A stage marked `"done"` is never re-run. On session restart mid-replicate:
read this file the same way `CLAUDE.md`'s existing SIMULATION STATE restart protocol reads the
run_log table — find the first stage that isn't `"done"`, and if the background process is no
longer running (`get_run_status`/process check), just re-invoke the same command; the script
self-determines the resume point from this file.

## Halt contract — never auto-changes a locked protocol

Recovery scope matches `.claude/commands/recover.md`'s `plan_mode=="deterministic"` rule exactly:
only EXTEND-type recovery (a parameter tweak that never touches `decided_params`, e.g. a longer
300 K hold) auto-applies, capped at 2 attempts. Any of the following halts immediately — the
script prints `{"status": "halted", "stage": ..., "detail": ...}` and exits without submitting
anything further:
- `equil_verdict == STRUCTURAL_FAIL` (or `FAIL`), or EXTEND exhausted at 2 attempts
- (implicitly, via the artifact-shape check in `enforce_gate.py`'s retrospective mode) any stage
  whose `run_log.md` write didn't land cleanly

On a halt, `executor_state.json["halted"]` carries the stage, reason, and full diagnostic detail
(the same fields `enforce_equilibration_gate` already returns) — write this to
`run_log.md` as a "protocol did not reproduce on this seed" finding and surface for human review,
per `recover.md`'s deterministic-mode rule. Do **not** re-invoke with a changed protocol; changing
`decided_params` on a locked replicate breaks the fixed-protocol-across-replicates invariant the
whole campaign depends on.

## Scope

EMC build path only (18 of ~19 supported classes). `PURA` (the one RadonPy-only class —
`preferred_builder != "emc"`) is not yet supported by the scripted path; `do_build()` raises a
clear error rather than attempting it. Run PURA through the normal agent-driven pipeline
(a validated SMILES in this class still skips planner/critic via `CLAUDE.md`'s existing
shortcut; only the execution-stage agent spawns still happen for this one class, for now).
