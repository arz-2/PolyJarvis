# Deterministic replicate guide (Phase A/B, `plan_mode=="deterministic"`) — orchestrator-read

Read this instead of `FOUNDATION.md`/`THERMAL_TRACK.md`/`MECHANICAL_TRACK.md` for Phase A/B once
`CLAUDE.md`'s PLAN step has produced a `plan_mode=="deterministic"` `run_plan.json`
(this exact canonical SMILES's `guides/system_characterization_cache.json` entry has
`protocol_validated==true` covering the requested properties — the protocol is already
validated for THIS molecule, never a class-level signal). `SUMMARY.md`'s Phase C
is unchanged either way; the executor produces the same `raw/*.json` artifacts those steps already
consume.

## Invocation — one or two phases, split at the mandatory-refine boundary

A plain script cannot spawn `Agent(...)`. `system-characterization-analyzer`'s mandatory post-PASS
characterization (`FOUNDATION.md`'s `[Equilibration]` section) must still run inside the live
orchestrator session when this SMILES is novel — Build through Equil-check-PASS itself needs no
agent judgment (`do_equil_and_check()` runs its own EXTEND loop headlessly), so the split point
moves to *after* the equilibration chain PASSes, not before Build. The Novelty Gate (`CLAUDE.md`
SETUP) already determines `IS_NOVEL` before Phase A starts, so the split point is known up front:

- **`IS_NOVEL=false`** (the common replicate-2+ case — this exact SMILES already has a cached
  characterization from an earlier run): one invocation, end to end.
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
  1. `--phase equil` — runs Build → Equilibration → Equil-check (including its own EXTEND loop,
     up to the deterministic cap) and stops once `equil_verdict=PASS` (or halts on
     STRUCTURAL_FAIL/FAIL/EXTEND_EXHAUSTED, per the Halt contract below — same as any other
     stage). Prints `{"status": "equil_complete", "npt_prod_data_path": ...,
     "npt_prod_log_path": ..., "npt_prod_dump_path": ..., "density_gcm3": ...}` on success.
     BACKGROUND-WAIT on this invocation (the long one — it now includes the full equilibration
     chain, not just Build).
  2. Spawn `system-characterization-analyzer` exactly as `FOUNDATION.md`'s `[Equilibration]` mandatory
     refine step documents, reading the paths from step 1's printed output plus `data_path` from
     `executor_state.json`'s `build` stage result (for `inspect_data_file`'s `backbone_types`
     lookup — the original pre-simulation `.data` file, never a `write_data` output). No critic
     step follows — the characterization step was never critiqued (mechanical-track knobs only,
     narrowly-scoped numeric refinement of an already-approved plan).
  3. Re-invoke: `... run_deterministic_replicate.py --run_name <RUN> --polymer_class <CLASS>
     --plan PLAN_PATH --resume-from thermal` — `executor_state.json` already has `build` and
     `equil_check` marked `done`, so this picks up at Phase B with whatever
     `bm_pressures_atm`/`K_deform_rate_inv_s` the characterization step patched into `PLAN_PATH`
     (or left at class defaults, if unreliable). BACKGROUND-WAIT on this second invocation.

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
