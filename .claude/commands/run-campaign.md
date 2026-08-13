---
description: Kick off a full PolyJarvis simulation campaign for a SMILES — reads orchestration/ORCHESTRATOR.md and runs SETUP through PHASE C as the orchestrator session.
allowed-tools: Read, Write, Edit, Bash, Agent
---

**Arguments:** `<smiles> <properties_csv> [run_name]` — e.g.
`/run-campaign "*CC(F)(F)*" Tg,density,bulk_modulus pvdf1`. `properties_csv` is a comma-separated
list drawn from the properties the pipeline supports (Tg, density, bulk_modulus). If `run_name`
is omitted, ask the user for one rather than inventing it — there is no default-naming convention
in this repo to fall back on.

This session becomes the orchestrator for the rest of the campaign: it holds all run state and
recovery authority until every requested property completes or the run is written UNRESOLVED.

1. `Read` `orchestration/ORCHESTRATOR.md` now. It owns the worker roster and the full
   SETUP → GATE & PLAN → THREAD THE PLAN → HARDWARE → BACKGROUND-WAIT → RECOVERY → PHASE A/B/C
   workflow — follow it exactly as written from here on.
2. Execute its `SETUP` step using the `smiles`, `properties_csv`, and `run_name` given above
   verbatim as `properties_requested` — do not re-derive them from freeform chat.
3. Continue through `GATE & PLAN`, `THREAD THE PLAN`, `HARDWARE`, and `PHASE A`/`B`/`C` exactly as
   `orchestration/ORCHESTRATOR.md` specifies, spawning workers via `Agent(subagent_type=...)` and
   following its `BACKGROUND-WAIT`/`RECOVERY` sections by name whenever they're referenced from a
   phase guide.
