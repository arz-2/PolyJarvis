# PolyJarvis

AI agent for autonomous polymer MD simulation. Given a SMILES string, runs the full pipeline — molecular construction (RadonPy/EMC MCP servers) → equilibration → Tg sweep → property extraction (LAMMPS engine MCP server, local GPU) — and reports Tg, density, and bulk modulus validated against experiment.

---

## Key Directories

| Path | Contents |
|------|----------|
| `guides/` | Agent workflow guides (worker-named); cross-track rules are in this file (see below) |
| `guides/polymer_rules.json` | Per-class Tg ranges, density targets, DP defaults, annealing cycles |
| `data/TEMPLATE/run_log.md` | Run log template — copy to `data/[RUN]/run_log.md` at task start |
| `data/[RUN]/` | All run files: `run_log.md`, `lammps/`, `raw/`, `graphs/` (git-excluded) |

---

## Path Convention

All run files live under `data/<run_name>/` (repo-relative, git-excluded). Use absolute paths in all tool calls.

`<lammps_base>` = `/home/arz2/PolyJarvis/data/<run_name>/lammps/`

**Equilibration internals** — directory names are tool-defined by `generate_equilibration_workflow`. Use the return dict keys (`npt_production_dir`, `npt_prod300_data`, etc.) — do not construct these paths manually. Key file names: `nvt_production.log` (melt NVT), `npt_production_out.data` (rubbery final), `npt_prod300_out.data` (glassy 300 K final).

**Track output paths** (orchestrator-chosen, under `<lammps_base>`):
- thermal: `thermal/tg_sweep/tg_sweep.log`
- mechanical (born): `mechanical/born/nvt_born.log`, `mechanical/born/born_matrix.dat`
- mechanical (deform): `mechanical/deform/npt_deform.log`
- mechanical (murnaghan): `mechanical/bm_series/` (log files listed in murnaghan-worker RESULT)

---

## Run Log

Copy `data/TEMPLATE/run_log.md` to `data/[RUN]/run_log.md` at task start. Fill it in real time — not reconstructed at the end. The RECOVERIES section is the primary evidence of agent value — write a block immediately after resolving any failure.

---

## Orchestrator Pattern (Multi-Agent Mode)

The default mode is multi-agent. The orchestrator (this session) spawns specialist workers via `Agent(subagent_type=...)` calls. Workers are stateless — the orchestrator holds all state and recovery logic.

| Worker | Color | Role | Model |
|--------|-------|------|-------|
| `planner` | 🟡 yellow | goal + class → `run_plan.json` (deterministic if confidence=high; reasoned otherwise) | opus |
| `critic` | 🔴 red | proposed `run_plan.json` → verdict approved \| revise \| escalate | opus |
| `molecule-builder` | 🔵 blue | SMILES → `.data` file (EMC or RadonPy) | opus |
| `equilibration-worker` | 🟠 orange | `.data` → submitted equilibration chain | sonnet |
| `equilibration-checker` | 🟠 orange | equil logs → PASS/EXTEND/FAIL verdict + density | haiku |
| `tg-sweep-worker` | 🟣 purple | **thermal track** — equil `.data` → submitted Tg sweep run | haiku |
| `tg-analysis-worker` | 🟢 green | **thermal track** — Tg sweep log → Tg_K, CTE (α_g, α_r), ΔCp | haiku |
| `born-worker` | 🔵 blue | **mechanical track** — NPT `.data` → submitted NVT Born matrix run (glassy only) | sonnet |
| `deform-worker` | 🔵 cyan | **mechanical track** — NPT `.data` → submitted uniaxial deformation run (born fallback) | haiku |
| `murnaghan-worker` | 🟠 orange | **mechanical track** — equil `.data` → submitted Murnaghan pressure series (rubbery) | haiku |
| `bulk-modulus-extractor` | 🟢 green | Born/deform/Murnaghan/fluctuation logs → bulk_modulus_GPa | sonnet |
| `run-summary-worker` | 🟢 green | all output JSONs → `run_summary.json` | haiku |

### Track definitions

The pipeline groups workers into **tracks** — campaigns that share a simulation type and produce related properties. Foundation runs first and feeds all tracks; mechanical reads `is_glassy` from thermal (or `glassy_hint` when thermal is skipped).

| Track | Workers | Properties |
|-------|---------|------------|
| foundation | molecule-builder, equilibration-worker, equilibration-checker | density (from equil-check) |
| thermal | tg-sweep-worker, tg-analysis-worker | Tg, CTE (α_g, α_r), ΔCp |
| mechanical | born/deform/murnaghan-worker, bulk-modulus-extractor | K (bulk modulus), G, E |

### Orchestrator workflow

```
SETUP
  Read CLAUDE.md only (never read worker guides directly)
  Copy data/TEMPLATE/run_log.md → data/[RUN]/run_log.md
  classify_polymer(smiles) if class unknown → CLASS_ID. Check builder_status:
    `jq -r '.classes.CLASS_ID.builder_status // "supported"' guides/polymer_rules.json`
    If result == "unsupported": write UNRESOLVED to run_log.md and stop.
  Parse properties_requested from task TARGET_PROPERTIES field:
    properties_requested = {"density", "tg", "bulk_modulus"}  # default: all three
    If task says "all" or field absent → use full set. Otherwise normalize to lowercase set.
    Write "Requested: {properties_requested}" to run_log.md metadata line.
  PLAN — Agent(subagent_type="planner", description="🟡 Plan {polymer_name}",
      prompt="run_name: <RUN>\nsmiles: <SMILES>\npolymer_class: <CLASS_ID>\nproperties_requested: <comma-joined>\nwork_dir: data/<RUN>/lammps")
    → parse RESULT block → extract plan_path (PLAN_PATH), plan_mode, confidence, critique_status.
    Write D-00 (plan) pointer to run_log.md header: PLAN_PATH + plan_mode + confidence.
  CRITIC loop (max 2 rounds) — Agent(subagent_type="critic", description="🔴 Critique plan",
      prompt="run_plan_path: PLAN_PATH\ncritic_round: <N>")
    → parse RESULT block:
      status=approved  → proceed.
      status=revise    → re-spawn planner with the critique findings; increment round; re-critique.
      status=escalate  → write UNRESOLVED to run_log.md and stop.
    Deterministic plans (confidence=high) return approved in round 1 with 0 findings — no loop.
  Thread the approved plan. EVERY `gen_prompt.py` call MUST include `--plan PLAN_PATH` so the
  plan's decided_params drive the worker prompts. Do NOT read polymer_rules.json manually — the
  plan is the source of truth. The Validator (see below) checks each worker result against the
  plan's success_criteria; a deviation routes back to the planner, not the worker. Example:
    `python3 scripts/gen_prompt.py --stage <STAGE> --run_name <RUN> --polymer_class <CLASS> --plan PLAN_PATH [--data_path ...]`
  Read temperature regime from approved plan (before spawning any worker):
    `T_workflow_K=$(jq -r '.decided_params.T_workflow_K // 600' PLAN_PATH)`
    Write T_workflow_K to run_log.md header (alongside plan_path + confidence).
  If "tg" not in properties_requested: glassy_hint = (T_workflow_K != 300.0)
  Read hardware regime from approved plan (before any GPU stage):
    `GPU_PER_RUN=$(jq -r '.decided_params.gpu_per_run // empty' PLAN_PATH)`  (empty ⇒ policy-derived, 1 GPU)
    When the plan pins a D-08_hardware override (gpu_per_run/engine/mpi_ranks in decided_params),
    let `gen_prompt.py` thread it into the worker prompt — do NOT also pass `--gpu_ids`/`--mpi_ranks`
    (CLI wins and would shadow the plan). Claim the matching GPU count at submit time:
    `scripts/pick_gpu.py --json claim --run <RUN> --need ${GPU_PER_RUN:-1}` → parse the JSON:
    on success `{"claimed":[ids],...}` (use that list verbatim as the worker's gpu_ids); on
    shortfall `{"error":...,"available":[…]}` with exit 1 (defer/retry, do not force). Release on
    completion (`pick_gpu.py release --run <RUN>`). Write the chosen engine/gpu_per_run/mpi to
    run_log.md (D-08 row).

PHASE A — FOUNDATION (always)

  [Build]
  Agent(subagent_type="molecule-builder", description="🔵 Build {polymer_name} cell",
        prompt=<gen_prompt.py --stage build --plan PLAN_PATH>)
    → parse RESULT → extract data_path, lammps_flags

  [Equilibration]
  Agent(subagent_type="equilibration-worker", description="🟠 Equilibrate {polymer_name}",
        prompt=<gen_prompt.py --stage equil --plan PLAN_PATH --data_path ...>)
    → parse RESULT → extract chain_id, monitor_command, expected_equil_data
  Write SIMULATION STATE to run_log.md (status=monitoring)
  Monitor(command=monitor_command, timeout_ms=3600000)   # see Monitor semantics below
  /compact Preserve: current phase (A), run_name, all chain_id/run_id values, is_glassy (if known), properties_requested, run_log.md absolute path, last worker RESULT block  # run if context > 40%
  get_run_status(chain_id) → check success/failure

  [Equil-check gate]
  Agent(subagent_type="equilibration-checker", description="🟠 Equil check {polymer_name}",
        prompt=<gen_prompt.py --stage equil-check --plan PLAN_PATH --data_path npt_prod_data_path>)
    → parse RESULT → extract equil_verdict, density_gcm3,
        ct_decay_fraction, ct_tau_relax_ps,
        end_to_end_r_mean_A, end_to_end_r_std_A, end_to_end_n_chains
      → write D-05 to run_log.md (populate Chain Structure Summary rows from these fields)
  If equil_verdict=EXTEND: extend chain by 1–2 ns and re-Monitor (max 2 extensions)
  If equil_verdict=FAIL: write UNRESOLVED and stop

PHASE B — TRACKS (property-conditional)

  [thermal track — if "tg" in properties_requested]
  Agent(subagent_type="tg-sweep-worker", description="🟣 Tg sweep {polymer_name}",
        prompt=<gen_prompt.py --stage tg --plan PLAN_PATH --data_path equil_data_path>)
    → parse RESULT → extract run_id, monitor_command
  Write SIMULATION STATE (status=monitoring)
  Monitor(command=monitor_command, timeout_ms=3600000)   # see Monitor semantics below
  /compact Preserve: current phase (B/thermal), run_name, all chain_id/run_id values, is_glassy (if known), properties_requested, run_log.md absolute path, last worker RESULT block
  Agent(subagent_type="tg-analysis-worker", description="🟢 Extract Tg {polymer_name}",
        prompt=<gen_prompt.py --stage analyze-tg --plan PLAN_PATH --data_path tg_log_path>)
    → parse RESULT → extract Tg_K, Tg_fit_quality → write D-06 to run_log.md

  [is_glassy determination]
  if "tg" in properties_requested:
    is_glassy = (Tg_K > 300)    # safe default: True if Tg_K is None or fit ABORT
  else:
    is_glassy = glassy_hint      # from plan; write D-06 = "N/A — tg not requested"
    Tg_K = None; Tg_fit_quality = "N/A (not requested)"

  [mechanical track — if "bulk_modulus" in properties_requested]
  if is_glassy:
    Agent(subagent_type="born-worker", description="🔵 NVT-Born {polymer_name}",
          prompt=<gen_prompt.py --stage born --plan PLAN_PATH --data_path npt_prod_data_path>)
      → parse RESULT → extract run_id_born, born_log_path, born_matrix_file, n_atoms, monitor_command_born
    Write SIMULATION STATE (status=monitoring)
    Monitor(command=monitor_command_born, timeout_ms=3600000)
    /compact Preserve: current phase (B/mechanical), run_name, all chain_id/run_id values, is_glassy, properties_requested, run_log.md absolute path, last worker RESULT block
    Recovery if born-worker fails: spawn deform-worker as fallback —
      Agent(subagent_type="deform-worker", description="🔵 Deform fallback {polymer_name}",
            prompt=<gen_prompt.py --stage deform --plan PLAN_PATH --data_path npt_prod_data_path>)
        → parse RESULT → extract run_id_deform, deform_log_path, monitor_command_deform
      Write SIMULATION STATE (status=monitoring)
      Monitor(command=monitor_command_deform, timeout_ms=3600000)
      /compact (same preserve list + deform_log_path)
  elif bm_pressures_atm is non-null in plan.decided_params:   # rubbery + pressures
    Agent(subagent_type="murnaghan-worker", description="🟠 Murnaghan BM {polymer_name}",
          prompt=<gen_prompt.py --stage murnaghan --plan PLAN_PATH --data_path equil_data_path>)
      → parse RESULT → extract chain_id_murnaghan, log_files (murnaghan_log_files), monitor_command_murnaghan
    Write SIMULATION STATE (status=monitoring)
    Monitor(command=monitor_command_murnaghan, timeout_ms=3600000)
    /compact Preserve: current phase (B/mechanical), run_name, all chain_id/run_id values, is_glassy, murnaghan_log_files, properties_requested, run_log.md absolute path, last worker RESULT block
  # else (rubbery + no pressures): skip — fluctuation path, equil log already present

  Agent(subagent_type="bulk-modulus-extractor", description="🟢 Extract BM {polymer_name}",
        prompt=<gen_prompt.py --stage analyze-bm --plan PLAN_PATH
               [--born_log born_log_path --born_matrix born_matrix_file --born_n_atoms n_atoms]  # born path
               [--deform_log deform_log_path]                                                     # deform fallback
               [--murnaghan_logs '<JSON list of log_files>']                                      # Murnaghan path
               --npt_prod_log npt_prod_log_path>)                                                 # fluctuation (always passed)
    → parse RESULT → extract bulk_modulus_GPa, bulk_modulus_method → write D-07 to run_log.md

PHASE C — SUMMARY (always)

  Agent(subagent_type="run-summary-worker", description="🟢 Run summary {polymer_name}",
        prompt=<gen_prompt.py --stage run-summary --plan PLAN_PATH
               --smiles ... --ff ... --tg_fit_quality ... --d05 equil_verdict>)
    → parse RESULT → run_summary_path → write RESULTS to run_log.md
```

### Validator gate

The Planner proposes; the Executor **never improvises**. After each worker's `Monitor` + status check, validate the result against that worker's `success_criteria` in the approved `run_plan.json` (`planned_stages[].success_criteria`):

- **Met** → proceed.
- **Not met** → invoke `/recover` (max 2 attempts/worker). The equil-check gate is `check_equilibration_comprehensive.overall_pass=True`; the tg-analysis gate is the bilinear-fit R² floor. These are already enforced — the plan records them as explicit criteria rather than implicit rules.
- **Probe contradicts a plan assumption** → if a planned `reduction_probe` comes back inconsistent with a plan assumption (e.g. the chosen FF is wrong), return control to the **planner** to revise downstream stages (re-spawn `planner` with the finding, then re-`critic`). Do not let a worker silently improvise a different parameter.
- **`hardware_benchmark` probe** → when the plan schedules it (off-table FF, unusual cell size, or a host where `hardware_policy.values_are_benchmarked=false`), run it **politely before** the affected GPU stage: `scripts/calibrate_hardware.py --cell <built .data> --ff <fam>` (idle-GPU + spare-core gated, niced — never `--allow-busy` on a shared box). If the measured winner contradicts the plan's D-08 choice, route back to the **planner** (re-plan → re-`critic`) exactly like any other contradicting probe — do not let the worker pick a different engine/mpi on its own.

### Monitor semantics

Always call `Monitor(command=monitor_command, timeout_ms=3600000)` — 3600000 ms (1 h) is the tool's max, and a LAMMPS run can exceed it. Interpret the outcome by what Monitor prints, not by the fact that it exited:

- prints `PROGRESS [##-------] 2/9 done: <stage>` (chains only) → live per-stage progress as each equilibration/series stage finishes; informational, no action — relay to the user.
- prints `RUN_COMPLETE` → run finished; `cat`'d sentinel JSON carries `status: completed | failed`. `completed` → proceed; `failed` → `/recover`.
- prints `PROCESS_DEAD_NO_SENTINEL` → the job process died without writing a sentinel (OOM/reboot) → `/recover`.
- exits with **neither** line → this is a Monitor **timeout, not completion**. The run is still going. Call `watch_run(id)` again and re-issue Monitor (re-arm). Do NOT treat a bare timeout as done or failed.

### Checkpoint protocol

Before every `Monitor` call, write SIMULATION STATE to `run_log.md` (see `data/TEMPLATE/run_log.md` for format). Update status to `done` or `failed` after Monitor returns.

On session restart: read SIMULATION STATE table → find row with `status=monitoring` → `get_run_status(id)` → `watch_run(id)` → re-issue Monitor (with `timeout_ms=3600000`).

### Auto-compact

Manual /compact focus string (after each Monitor, before bulk-modulus-extractor, before run-summary-worker):
```
/compact Preserve: current phase (A/B/C) + last worker completed, run_name, all chain_id/run_id values, is_glassy (if known), murnaghan_log_files (if set), properties_requested, run_log.md absolute path, last worker RESULT block
```
After any compact: read `run_log.md` SIMULATION STATE before the next tool call.

### Recovery

Use `/recover` to diagnose any worker failure, plan the fix, and re-spawn the worker. Max 2 recovery attempts per worker — after that write `UNRESOLVED` to run_log.md and stop. For session restart after a killed Claude process, read the SIMULATION STATE table in run_log.md and call `get_run_status` on the monitoring row — `/recover` handles this too.

---

<!-- CROSS_STAGE_RULES_START -->
## Cross-Track Rules (Always Active — Memorize These)

These rules are inlined into every worker prompt by `gen_prompt.py`. They apply regardless of which worker or track is running.

0. **GPU is used for ALL simulation runs** — always pass explicit `gpu_ids` and `mpi`; never leave them unset or default
1. **Fill `run_log.md` in real time** — log each DECISION row when made, each RECOVERY block immediately after resolving an error; do not reconstruct at the end
2. **Record all seeds before submitting any job** — log EMC seed, SEED_HOT, and SEED_COLD in the run_log header. For replication studies, use fixed seeds from `guides/REVISION_PARAMS.md`. For exploratory runs, read seeds back from job output and log them immediately after submission.
<!-- CROSS_STAGE_RULES_END -->

