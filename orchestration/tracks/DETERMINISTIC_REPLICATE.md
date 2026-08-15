# Deterministic replicate guide (Phase A/B, `plan_mode=="deterministic"`) — orchestrator-read

Read this instead of `FOUNDATION.md`/`THERMAL_TRACK.md`/`MECHANICAL_TRACK.md` for Phase A/B once
`ORCHESTRATOR.md`'s PLAN step has produced a `plan_mode=="deterministic"` `run_plan.json`
(this exact canonical SMILES's `guides/system_characterization_cache.json` entry has
`protocol_validated==true` covering the requested properties). `SUMMARY.md`'s Phase C is
unchanged either way; the executor produces the same `raw/*.json` artifacts those steps already
consume.

## One command, validated run → completed replicate

```
chain_validated_run.py --source-run <VALIDATED_RUN> --run_name <RUN> \
    --polymer_class <CLASS> --smiles "<smiles>" [--properties ...] [--no-run]
```

Chains every link: **replay-verify** the source run's decks against its own plan →
**freeze** the protocol per track → **write** the deterministic plan → **execute** it.
A refusal at any link stops the chain and names the reason; a replay or freeze refusal means the
source run's recorded protocol is not the one it executed, which is exactly when a replicate must
not launch. `--no-run` stops after the plan. `--emit-decks DIR` runs all four links but generates
decks instead of submitting.

It canonicalizes the SMILES for you. Never hand-type a cache key — `*OC(C)C(=O)*` and
`*OC(=O)C(*)C` are different molecules.

The steps below are what that command runs; use them directly only to re-do one link.

## Protocol source

Generate the plan with `--canonical_smiles`. When this exact SMILES has a frozen `protocol` block
in `guides/system_characterization_cache.json`, the plan is built from what that molecule
**actually ran** — resolved equilibration step counts and the executed route — instead of from
`polymer_rules.json` class defaults:

```
make_deterministic_plan.py --run_name <RUN> --polymer_class <CLASS> --smiles "<smiles>" \
    --canonical_smiles "<canonical>" --properties <props>
```

The plan carries `execution_chain`: every stage in order with fully-resolved arguments, and
placeholders for what is deliberately not frozen — `<VARY:*>` (seeds, which must differ per
replicate) and `<HOST:*>` (engine/mpi/gpu, re-derived from `hardware_policy`).

Freezing is per track and per exact SMILES, so a class's second validated molecule never
overwrites its first. An unfrozen track falls back to class defaults.

## Invocation

One invocation, end to end:
```
<repo>/mcp-servers/.venv/bin/python orchestration/scripts/run_deterministic_replicate.py \
    --run_name <RUN> --polymer_class <CLASS> --plan PLAN_PATH [--seed-mode both|velocity]
```

`--seed-mode both` (default) rebuilds the cell with a fresh EMC seed and redraws velocities —
independent configurations, so the spread across replicates is an honest uncertainty estimate.
`--seed-mode velocity --source-run <RUN>` branches from that run's equilibrated cell and varies
only the velocity seed; the shared packing makes the spread understate true uncertainty.

The executor halts if EMC's echoed `resolved_seed` equals the frozen protocol's seed — EMC has
returned a previous run's seed while reporting a fresh draw, which silently destroys replicate
independence.

`--emit-decks DIR` generates every deck without submitting, for diffing a replicate's decks
against the source run's. (`--dry-run` only resolves params; it writes no decks.)

## Route forcing

`frozen_protocol.<track>.route` records the branch the source run took. The replicate reproduces
it rather than re-deciding — a K from the deform fallback and a K from Murnaghan are not the same
measurement. Where the replicate's own gate disagrees, `route_forced` / `route_diverged` and
`own_gate_said` are written to `executor_state.json`, so forcing never silently discards the
acceptance signal.
Write SIMULATION STATE to run_log.md (status=monitoring), launch this detached
(`Bash(command="nohup <cmd> & disown", run_in_background=true)`), then **BACKGROUND-WAIT**
(canonical pattern, `ORCHESTRATOR.md`) on its own completion — the script blocks internally through
every stage and prints one final JSON line (`{"status": "complete", ...}` or
`{"status": "halted", ...}`) on exit.

`system-characterization-analyzer` is a reasoned-path-only step (`FOUNDATION.md`'s
`[Equilibration]` mandatory refine, for `IS_NOVEL=true` runs that are *not* deterministic); this
script never spawns it.

## Resumability

`data/<RUN>/raw/executor_state.json` tracks per-stage status (`build`, `equil_check`, `thermal`,
`mechanical`, `summary`). A stage marked `"done"` is never re-run. On session restart mid-replicate:
read this file the same way `ORCHESTRATOR.md`'s existing SIMULATION STATE restart protocol reads the
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
per `recover.md`'s deterministic-mode rule. Do **not** re-invoke with a changed protocol.

## Scope

EMC build path only (18 of ~19 supported classes). `PURA` (the one RadonPy-only class —
`preferred_builder != "emc"`) is not supported by the scripted path; `do_build()` raises a
clear error rather than attempting it. Run PURA through the normal agent-driven pipeline
(a validated SMILES in this class still skips planner/critic via `ORCHESTRATOR.md`'s existing
shortcut; only the execution-stage agent spawns happen for this one class).
