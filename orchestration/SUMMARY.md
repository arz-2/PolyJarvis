# SUMMARY track guide (Phase C) — orchestrator-read

Read this at **Phase C entry** (always runs). It owns experimental lookup → tg_path selection →
run-summary → memory capture. Worker prompts come from `gen_prompt.py --stage run-summary --plan
PLAN_PATH ...`. Run the experimental lookup **before** run-summary so grading uses condition-matched
DB ranges.

## [Experimental lookup]

```
Agent(subagent_type="exp-lookup-worker", description="🟢 Exp lookup {polymer_name}",
      prompt="polymer_name: <canonical name>\npolymer_class: <CLASS>\nT_sim_K: <300 or T_workflow>\n"
             "is_glassy: <from thermal track>\nproperties: <comma-joined>\n"
             "output_path: data/<RUN>/raw/exp_lookup.json")
  → RESULT → exp_lookup_path, match_confidence, exp_{tg,density,K}_{min,max}.
```

Thread these ranges into run-summary via the CLI overrides below. **NEVER hand-enter a tight single
floor** (a too-tight 1.35 density floor caused a 0.07% false FAIL, PVC2). When match_confidence=none
or a field is null, **OMIT** that override — gen_prompt then falls back to its DB lookup /
polymer_rules median ±5% band, which is correctly wide.

## Before spawning run-summary-worker

1. **Verify the lammps-engine MCP server is live** (long sessions >12 h drop the connection
   silently): a minimal call (e.g. `list_templates`) must return; if it hangs/errors, restart the
   MCP server first.
2. **TG_PATH is already known** — single-rate-primary means there's no rate ambiguity to resolve:
   it's the thermal track's own `tg-analysis-worker` RESULT's `output_dir` field (held from Phase
   B) + `/tg_summary.json`. No extra resolution step, no `select_tg_path.py` call — that helper
   still exists for the legacy/opt-in multirate path only.
3. **Exp ranges:** thread each non-null exp-lookup field as a CLI override; omit nulls so gen_prompt
   falls back to its DB/polymer_rules ±5% band: `--exp_tg_min/--exp_tg_max`,
   `--exp_density_min/--exp_density_max`, `--exp_K_min/--exp_K_max` (else polymer_rules exp_K_GPa).

## [Run summary]

```
Agent(subagent_type="run-summary-worker", description="🟢 Run summary {polymer_name}",
      prompt=<gen_prompt.py --stage run-summary --plan PLAN_PATH
             --smiles ... --ff ... --tg_fit_quality ... --d05 equil_verdict
             --tg_path <TG_PATH>
             [--exp_tg_min ... --exp_tg_max ...] [--exp_density_min ... --exp_density_max ...]
             --exp_K_min ... --exp_K_max ...>)
  → RESULT → run_summary_path → write RESULTS to run_log.md
  → if run_summary tg.primary_fit_invalid==True, flag the headline Tg as unreliable in run_log.md
    (the fit violated a hard physics constraint and no valid alternative existed).
```

## [Campaign hooks — after run-summary, before memory capture]

Only relevant when this run is part of the two-speed campaign workflow
(`.claude/plans/generic-beaming-mitten.md`); harmless no-ops otherwise.

1. **Lock the protocol, if this run just validated it.**
   `jq -r '.plan_mode' data/<RUN>/raw/run_plan.json` — only proceed if `"reasoned"` (a
   `deterministic` run is already a locked replay; nothing to lock). Then check every
   requested property PASSed: `jq -r '[.results[] | .status] | all(. == "PASS")'
   data/<RUN>/raw/run_summary.json` (check only the `results.<prop>` blocks for
   `properties_requested`, not properties this run didn't request/report). If `true`:
   ```
   Agent(subagent_type="protocol-locker", description="🔴 Lock protocol {polymer_class}",
         prompt="run_plan_path: data/<RUN>/raw/run_plan.json\npolymer_class: <CLASS>\n"
                "run_log_path: data/<RUN>/run_log.md")
     → RESULT → status: locked | refused, changes, note_written
   ```
   It re-derives the same gate itself (never trust the caller), runs
   `make_deterministic_plan.py --lock-from` as its mechanical backbone (identical patch to what
   was previously called directly here), then replaces the script's auto-generated one-liner
   with a curated write-up of what changed and why, read from this run's `decisions[]` +
   `RECOVERY` blocks. Write its `changes`/note to `run_log.md` (a new `## PROTOCOL LOCKED`
   block). If not all requested properties PASSed, do **not** spawn it — this run's protocol
   isn't perfected yet; continue diagnosing per `/recover`'s `plan_mode=="reasoned"` ladder
   instead.

2. **Aggregate, if this was the last replicate of a class's campaign set.** When the
   orchestrator's task input names a full replicate set (e.g. 4 run names for a class) and this
   run is the last one to complete:
   ```
   python3 orchestration/aggregate_replicates.py --polymer_class <CLASS> \
     --run_names <RUN1,RUN2,RUN3,RUN4>
   ```
   → `data/<CLASS>_campaign_summary.json`. Write the mean±SD summary to `run_log.md`. Skip if
   any replicate in the set hasn't finished yet — the script only needs the ones that exist,
   but a premature aggregate (missing values silently treated as "runs_missing_value") is
   misleading if reported as final.

## [Capture errors + improvements — to MEMORY ONLY, last action of the run]

Before declaring the run done, promote pipeline-level lessons to memory as `feedback` entries (per
the `# Memory` rules) so `/ingest-memory` can act on them later: (1) errors encountered (symptom →
root cause → fix/workaround); (2) codebase friction (confusing/wrong guide, MCP-tool quirk,
missing/incorrect polymer_rules param, awkward worker contract). Write them to the orchestrator's own
auto-memory dir and/or the relevant worker's canonical repo-root `.claude/agent-memory/<worker>/`
dir (the absolute path named in that worker's agent definition — never a `.claude/` created under a
work_dir or `data/<run>/` subdir); these are the inputs `/ingest-memory` consumes. Do **not** put any
of this in run_log.md — the run log is for users to interpret the simulation, not to fix the workflow
(RECOVERIES stays, per cross-track rule 1).
