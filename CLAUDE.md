# PolyJarvis

AI agent for autonomous polymer MD simulation. Given a SMILES string, runs the full pipeline — molecular construction (RadonPy/EMC MCP servers) → equilibration → Tg sweep → property extraction (LAMMPS engine MCP server, local GPU) — and reports Tg, density, and bulk modulus validated against experiment.

Read `guides/STAGE_INDEX.md` first on every task.

---

## Key Directories

| Path | Contents |
|------|----------|
| `guides/` | Stage-by-stage workflow guides; `STAGE_INDEX.md` is always read first |
| `guides/polymer_rules.json` | Per-class Tg ranges, density targets, DP defaults, annealing cycles |
| `data/TEMPLATE/run_log.md` | Run log template — copy to `data/[RUN]/run_log.md` at task start |
| `data/[RUN]/` | One directory per simulation run |
| `emc_pipeline.py` | EMC cell builder — 19 classes (PCFF: 15 classes; OPLS-AA: PHAL/PSTR; TraPPE-UA: PHYC/PDIE). RadonPy only: PSIL, PURA. |

---

## Run Log

Copy `data/TEMPLATE/run_log.md` to `data/[RUN]/run_log.md` at task start. Fill it in real time — not reconstructed at the end. The RECOVERIES section is the primary evidence of agent value — write a block immediately after resolving any failure.

---

## Orchestrator Pattern (Multi-Agent Mode)

The default mode is multi-agent. The orchestrator (this session) spawns specialist workers via `Agent(subagent_type=...)` calls. Workers are stateless — the orchestrator holds all state and recovery logic.

### Dispatch table

| After completing... | Spawn... |
|---|---|
| `classify_polymer` + `polymer_rules.json` lookup | `molecule-builder` |
| `molecule-builder` returns `data_path` | `equilibration-worker` → then Monitor |
| Monitor returns (equilibration done) | `check_equilibration_comprehensive` → if PASS, spawn `tg-sweep-worker` |
| Monitor returns (Tg sweep done) | `analysis-worker(tasks=[...])` |

See `guides/WORKER_CONFIGS.md` for prompt templates and RESULT block schemas for each worker.

### Orchestrator workflow

```
1. Read CLAUDE.md + STAGE_INDEX.md only (never read stage guides directly)
2. Copy data/TEMPLATE/run_log.md → data/[RUN]/run_log.md
3. classify_polymer(smiles) → extract class entry: `Bash: jq '.classes.CLASS_ID' guides/polymer_rules.json` → build run_params
4. Agent(subagent_type="molecule-builder", description="🔵 Build {polymer_name} cell", prompt=<smiles + run_params>)
     → parse RESULT block → extract data_path, lammps_flags
5. Agent(subagent_type="equilibration-worker", description="🟠 Equilibrate {polymer_name}", prompt=<data_path + params>)
     → parse RESULT block → extract chain_id, monitor_command
6. Write SIMULATION STATE to run_log.md (status=monitoring)
7. Monitor(command=monitor_command)          # orchestrator owns this
7a. /compact focus on simulation state, run IDs, and run_log.md checkpoint  # run before step 8 if context > 40%
8. get_run_status(chain_id) → check success/failure
9. check_equilibration_comprehensive(equil_log, dump, data, backbone_types) → PASS / EXTEND / ESCALATE
10. Agent(subagent_type="tg-sweep-worker", description="🟣 Tg sweep {polymer_name}", prompt=<equil_data_path + tg_params>)
      → parse RESULT block → extract run_id, monitor_command
11. Write SIMULATION STATE to run_log.md (status=monitoring)
12. Monitor(command=monitor_command)          # orchestrator owns this
12a. /compact focus on simulation state, run IDs, and run_log.md checkpoint  # run before step 13 if context > 40%
13. Agent(subagent_type="analysis-worker", description="🟢 Analyze {polymer_name} results", prompt=<logs + tasks=[...]>)
      → parse RESULT block → write RESULTS to run_log.md
```

### Analysis tasks construction

Build the `tasks` list from `polymer_rules.json` defaults plus any user-requested extras:
- Always include: `check_equilibration_comprehensive`, `extract_tg`, `extract_density`, `extract_bulk_modulus`
- Add per user request: `calculate_rdf`, `extract_end_to_end_vectors`
- For one-off non-standard requests (NEMD, literature search), handle inline — do not spawn a custom worker.

### Checkpoint protocol

Before every `Monitor` call, write to `run_log.md`:

```markdown
## SIMULATION STATE
| Stage         | chain_id / run_id | status     | output_path              |
|---------------|-------------------|------------|--------------------------|
| Equilibration | chain-abc123      | monitoring | /path/to/stages/         |
| Tg sweep      | —                 | pending    | —                        |
```

Update status to `done` after Monitor returns successfully, or `failed` on error. On session restart, read this table first — if a row shows `monitoring`, call `get_run_status(id)` to determine actual state before proceeding.

### Recovery ownership

The orchestrator decides all recovery actions. Workers are re-spawned with adjusted prompts:
- **Chain failed (Mode A):** Monitor fires → `get_run_status` returns FAILED → read error log → adjust params → re-spawn worker
- **Session ended mid-Monitor (Mode B):** On restart, read SIMULATION STATE → `get_run_status` → if still running, re-issue Monitor; if done, continue; if failed, enter recovery
- Max 2 recovery attempts per stage; after that, write `UNRESOLVED` and stop

---

## Auto-Continuation After Simulation

The orchestrator owns all `Monitor` calls. Workers (`equilibration-worker`, `tg-sweep-worker`) submit jobs and return `chain_id`/`run_id` + `monitor_command` without calling Monitor themselves.

```
1. result = Agent(subagent_type="equilibration-worker", ...)   # submits chain
2. chain_id = parse(result, "chain_id")
3. monitor_command = parse(result, "monitor_command")
4. write_checkpoint(run_log, chain_id, status="monitoring")
5. Monitor(command=monitor_command)   # block until done — harness re-invokes Claude
6. continue workflow                  # Claude picks up here automatically
```

Never poll `get_run_status` in a loop. The Monitor tool + sentinel file is how PolyJarvis avoids requiring the user to manually re-trigger Claude after each simulation stage.
