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

Thread these ranges into run-summary via the CLI overrides below. Never hand-enter a tight single
floor. When match_confidence=none or a field is null, **OMIT** that override — gen_prompt then
falls back to its DB lookup / polymer_rules median ±5% band.

## Before spawning run-summary-worker

1. **Verify the lammps-engine MCP server is live** (long sessions >12 h drop the connection
   silently): a minimal call (e.g. `list_templates`) must return; if it hangs/errors, restart the
   MCP server first.
2. **TG_PATH**: the thermal track's own `tg-analysis-worker` RESULT's `output_dir` field (held
   from Phase B) + `/tg_summary.json`.
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
             [--exp_K_min ... --exp_K_max ...]>)
  → RESULT → run_summary_path → write RESULTS to run_log.md
  → if run_summary tg.primary_fit_invalid==True, flag the headline Tg as unreliable in run_log.md
    (the fit violated a hard physics constraint and no valid alternative existed).
```

## [Campaign hooks — after run-summary, before memory capture]

Only relevant when the orchestrator's task input names a multi-run replicate set; harmless no-ops
for a single-run task.

1. **Lock the protocol, if this run just validated it.**
   `jq -r '.plan_mode' data/<RUN>/raw/run_plan.json` — only proceed if `"reasoned"`. Then check every
   requested property PASSed: `jq -r '[.results[] | .status] | all(. == "PASS")'
   data/<RUN>/raw/run_summary.json` (check only the `results.<prop>` blocks for
   `properties_requested`, not properties this run didn't request/report. If `true`:
   ```
   Agent(subagent_type="protocol-locker", description="🔴 Lock protocol {polymer_class}",
         prompt="run_plan_path: data/<RUN>/raw/run_plan.json\npolymer_class: <CLASS>\n"
                "run_log_path: data/<RUN>/run_log.md")
     → RESULT → status: locked | refused, changes, note_written
   ```
   See `protocol-locker.md` for what it does with this (own doc owns the procedure). Write its
   `changes`/note to `run_log.md` (a new `## PROTOCOL LOCKED` block). If not all requested
   properties PASSed, do **not** spawn it — continue via RECOVERY's `plan_mode=="reasoned"`
   ladder instead.


## [Capture errors + improvements — to MEMORY ONLY, last action of the run]

Before declaring the run done, save pipeline-level lessons (errors: symptom → root cause → fix;
codebase friction: bad guide, MCP quirk, wrong polymer_rules param) as `feedback` memory — the
orchestrator's own auto-memory dir and/or the worker's canonical `.claude/agent-memory/<worker>/`
dir, never under `data/<run>/`. Not run_log.md (RECOVERY blocks excepted).
