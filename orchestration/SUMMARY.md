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
2. **Determine tg_path + slope_gate_pass with the helper** — do NOT hand-derive the path (the PLA3
   footgun); the helper encodes the slowest/highest-rate convention:
   ```
   eval "$(python3 orchestration/select_tg_path.py --plan PLAN_PATH --multirate data/RUN/raw/tg_multirate_result.json)"
   # → sets TG_PATH (slowest rate if gate passed, else the plan's tg_slope_gate_fallback rate,
   #   default highest) and SLOPE_GATE (true|false)
   ```
3. **Exp ranges:** thread each non-null exp-lookup field as a CLI override; omit nulls so gen_prompt
   falls back to its DB/polymer_rules ±5% band: `--exp_tg_min/--exp_tg_max`,
   `--exp_density_min/--exp_density_max`, `--exp_K_min/--exp_K_max` (else polymer_rules exp_K_GPa).

## [Run summary]

```
Agent(subagent_type="run-summary-worker", description="🟢 Run summary {polymer_name}",
      prompt=<gen_prompt.py --stage run-summary --plan PLAN_PATH
             --smiles ... --ff ... --tg_fit_quality ... --d05 equil_verdict
             --tg_path <TG_PATH> --slope_gate_pass <SLOPE_GATE>
             [--exp_tg_min ... --exp_tg_max ...] [--exp_density_min ... --exp_density_max ...]
             --exp_K_min ... --exp_K_max ...>)
  → RESULT → run_summary_path → write RESULTS to run_log.md
  → if run_summary tg.primary_fit_invalid==True, flag the headline Tg as unreliable in run_log.md
    (the fit violated a hard physics constraint and no valid alternative existed).
```

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
