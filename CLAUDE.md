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
| `data/[RUN]/` | All run files: `run_log.md`, `lammps/`, `raw/`, `graphs/` (git-excluded) |

---

## Path Convention

All run files live under `data/<run_name>/` (repo-relative, git-excluded). Use absolute paths in all tool calls.

`<lammps_base>` = `/home/arz2/PolyJarvis/data/<run_name>/lammps/`

**Cross-stage derived paths** follow `<lammps_base>/<NN_stage>/<NN_stage>[_out].{data,log,dump}`.
Exceptions: `tg_log = tg/tg_sweep/tg_sweep.log`, `deform_log = prop/05_deform/05_deform.log` (null if rubbery).

---

## Run Log

Copy `data/TEMPLATE/run_log.md` to `data/[RUN]/run_log.md` at task start. Fill it in real time — not reconstructed at the end. The RECOVERIES section is the primary evidence of agent value — write a block immediately after resolving any failure.

---

## Orchestrator Pattern (Multi-Agent Mode)

The default mode is multi-agent. The orchestrator (this session) spawns specialist workers via `Agent(subagent_type=...)` calls. Workers are stateless — the orchestrator holds all state and recovery logic.

| Worker | Color | Role |
|--------|-------|------|
| `molecule-builder` | 🔵 blue | SMILES → `.data` file (EMC or RadonPy) |
| `equilibration-worker` | 🟠 orange | `.data` → submitted equilibration chain |
| `tg-sweep-worker` | 🟣 purple | equil `.data` → submitted Tg sweep run |
| `tg-analysis-worker` | 🟢 green | Tg sweep log → Tg_K + fit quality |
| `deform-worker` | 🔵 blue | NPT `.data` → submitted uniaxial deformation run (glassy only) |
| `property-analysis-worker` | 🟢 green | simulation logs → density, bulk modulus, run summary |

### Orchestrator workflow

```
1. Read CLAUDE.md + STAGE_INDEX.md only (never read stage guides directly)
2. Copy data/TEMPLATE/run_log.md → data/[RUN]/run_log.md
3. classify_polymer(smiles) → extract class entry: `Bash: jq '.classes.CLASS_ID' guides/polymer_rules.json` → build run_params
3a. Check builder_status: `jq -r '.classes.CLASS_ID.builder_status // "supported"' guides/polymer_rules.json`
    If result == "unsupported": write UNRESOLVED to run_log.md and stop — no builder path exists for this class.
3b. Generate worker prompts with `scripts/gen_prompt.py` — do NOT read WORKER_CONFIGS.md or polymer_rules.json manually:
    `Bash: python3 scripts/gen_prompt.py --stage <STAGE> --run_name <RUN> --polymer_class <CLASS> [--smiles ...] [--data_path ...]`
    Each call prints a ready-to-use prompt block. Override any field by passing the flag explicitly.
    The script inlines STAGE_INDEX.md (cross-stage rules) so workers receive full context.
3c. Parse requested properties from task TARGET_PROPERTIES field:
    properties_requested = {"density", "tg", "bulk_modulus"}  # default: all three
    If task says "all" or field is absent/empty → use full set (unchanged behavior)
    Otherwise normalize to lowercase set (e.g. "Tg, density" → {"tg", "density"})
    Write "Requested: {properties_requested}" to run_log.md metadata line.
    If "tg" not in properties_requested:
      # derive glassy_hint from polymer_rules.json experimental Tg
      Bash: jq -r '.classes.CLASS_ID.experimental_tg_K // 350' guides/polymer_rules.json
      If result is a number: glassy_hint = (result > 300)
      If result is an object (dict of variants): use first numeric value; default True if absent
      # glassy_hint used at step 14 in place of Tg sweep result
4. Agent(subagent_type="molecule-builder", description="🔵 Build {polymer_name} cell", prompt=<output of gen_prompt.py --stage build>)
     → parse RESULT block → extract data_path, lammps_flags
5. Agent(subagent_type="equilibration-worker", description="🟠 Equilibrate {polymer_name}", prompt=<output of gen_prompt.py --stage equil --data_path ...>)
     → parse RESULT block → extract chain_id, monitor_command, expected_equil_data
6. Write SIMULATION STATE to run_log.md (status=monitoring)
7. Monitor(command=monitor_command)          # orchestrator owns this
7a. /compact Preserve: workflow step number, run_name, all chain_id/run_id values, is_glassy (if known), properties_requested, run_log.md absolute path, last worker RESULT block  # run before step 8 if context > 40%
8. get_run_status(chain_id) → check success/failure
9. check_equilibration_comprehensive(equil_log, dump, data, backbone_types) → PASS / EXTEND / ESCALATE
10. if "tg" in properties_requested:
      Agent(subagent_type="tg-sweep-worker", description="🟣 Tg sweep {polymer_name}", prompt=<output of gen_prompt.py --stage tg --data_path equil_data_path>)
        → parse RESULT block → extract run_id, monitor_command
11.   Write SIMULATION STATE to run_log.md (status=monitoring)
12.   Monitor(command=monitor_command)          # orchestrator owns this
12a.  /compact Preserve: workflow step number, run_name, all chain_id/run_id values, is_glassy (if known), properties_requested, run_log.md absolute path, last worker RESULT block  # run before step 13 if context > 40%
13.   Agent(subagent_type="tg-analysis-worker", description="🟢 Extract Tg {polymer_name}", prompt=<output of gen_prompt.py --stage analyze-tg --data_path tg_log_path>)
        → parse RESULT block → extract Tg_K, Tg_fit_quality → write D-06 to run_log.md
14. is_glassy determination:
    if "tg" in properties_requested:
      is_glassy = (Tg_K > 300)          # safe default: True if Tg_K is None or fit ABORT
    else:
      is_glassy = glassy_hint            # from step 3c; write D-06 = "N/A — tg not requested"
      Tg_K = None; Tg_fit_quality = "N/A (not requested)"
15. if "bulk_modulus" in properties_requested AND is_glassy:
      Agent(subagent_type="deform-worker", description="🔵 Deform {polymer_name}", prompt=<output of gen_prompt.py --stage deform --data_path npt_prod_data_path>)
        → parse RESULT block → extract run_id_deform, monitor_command_deform
      Write SIMULATION STATE to run_log.md (status=monitoring)
      Monitor(command=monitor_command_deform)   # orchestrator owns this
      /compact Preserve: workflow step number, run_name, all chain_id/run_id values, is_glassy (if known), properties_requested, run_log.md absolute path, last worker RESULT block  # run before step 16 if context > 40%
16. Agent(subagent_type="property-analysis-worker", description="🟢 Analyze {polymer_name} properties",
          prompt=<output of gen_prompt.py --stage analyze-full --data_path npt_prod_data_path --is_glassy true|false --smiles ... --ff ... --tg_fit_quality ... --properties <comma-joined properties_requested> [--deform_log ...]>)
      → parse RESULT block → write RESULTS to run_log.md; run_summary.json written to raw_dir
```

### Checkpoint protocol

Before every `Monitor` call, write SIMULATION STATE to `run_log.md` (see `data/TEMPLATE/run_log.md` for format). Update status to `done` or `failed` after Monitor returns.

On session restart: read SIMULATION STATE table → find row with `status=monitoring` → `get_run_status(id)` → `watch_run(id)` → re-issue Monitor.

### Auto-compact

Manual /compact focus string (steps 7a, 12a, before step 16):
```
/compact Preserve: workflow step number, run_name, all chain_id/run_id values, is_glassy (if known), properties_requested, run_log.md absolute path, last worker RESULT block
```
After any compact: read `run_log.md` SIMULATION STATE before the next tool call.

### Recovery ownership

The orchestrator decides all recovery actions. Workers are re-spawned with adjusted prompts:

- **Chain failed (Mode A):** Monitor fires → `get_run_status` returns FAILED → read error log → adjust params → re-spawn worker
- **Session ended mid-Monitor (Mode B):** Two sub-cases:

  **B-1 — tmux alive:** `ssh lambda && pj` to re-attach; Monitor is still blocking, no action needed.

  **B-2 — Claude process died (no tmux, machine rebooted, or session killed):**
  1. `ssh lambda && pj && claude --continue` (or start fresh if conversation unavailable)
  2. Read `data/[RUN]/run_log.md` → find the row where `status = monitoring`; note the `id` column value
  3. Call `get_run_status(id)`:
     - **running** → `watch_run(id)` → re-issue `Monitor(command=monitor_command)` → update run_log.md back to `monitoring`
     - **completed** → update run_log.md to `done` → continue from the next orchestrator step
     - **failed** → `get_run_output(id)` → diagnose → re-spawn worker (counts as recovery attempt)
     - **not found** → wait 60–90 s for MCP server restart, retry; if still missing, treat as failed
  4. **`monitor_command` is deterministic:** `watch_run(id)` regenerates it from the ID alone — always safe to re-call

- Max 2 recovery attempts per stage; after that, write `UNRESOLVED` and stop

