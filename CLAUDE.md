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
| `guides/MULTI_MACHINE_WORKFLOW.md` | Two-machine revision integrator protocol (`scripts/integrate.py`) — how findings/fixes from both machines land in `main` |

---

## Path Convention

All run files live under `data/<run_name>/` (repo-relative, git-excluded). Use absolute paths in all tool calls.

`<lammps_base>` = `<repo_root>/data/<run_name>/lammps/` — `<repo_root>` is your PolyJarvis checkout dir (gen_prompt.py derives it from its own location; never hard-code `/home/<user>/...`).

Equilibration paths are tool-defined — use worker RESULT dict keys (`npt_production_dir`, `npt_prod300_data`, etc.); do not construct them manually.

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
| `murnaghan-worker` | 🟠 orange | **mechanical track** — equil `.data` → submitted Murnaghan pressure series (glassy 300 K primary; rubbery T>Tg unchanged) | haiku |
| `deform-worker` | 🔵 cyan | **mechanical track** — NPT `.data` → submitted 3-direction uniaxial deformation run (Murnaghan fallback) | haiku |
| `bulk-modulus-extractor` | 🟢 green | Murnaghan/deform/fluctuation logs → bulk_modulus_GPa (Born+NVT removed) | sonnet |
| `run-summary-worker` | 🟢 green | all output JSONs → `run_summary.json` | haiku |

### Track definitions

The pipeline groups workers into **tracks** — campaigns that share a simulation type and produce related properties. Foundation runs first and feeds all tracks; mechanical reads `is_glassy` from thermal (or `glassy_hint` when thermal is skipped).

| Track | Workers | Properties |
|-------|---------|------------|
| foundation | molecule-builder, equilibration-worker, equilibration-checker | density (from equil-check) |
| thermal | tg-sweep-worker, tg-analysis-worker | Tg, CTE (α_g, α_r), ΔCp |
| mechanical | murnaghan-worker (primary), deform-worker (fallback), bulk-modulus-extractor | K (bulk modulus), G, E |

### Orchestrator workflow

```
SETUP
  Read CLAUDE.md at startup. At Phase B entry, Read guides/THERMAL_TRACK.md if tg requested and/or Read guides/MECHANICAL_TRACK.md if bulk_modulus requested. Never read worker guides (THERMAL_SWEEP.md, BM_ANALYSIS.md, etc.) directly — gen_prompt.py inlines those into worker prompts.
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
  plan is the source of truth. Example:
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
    → parse RESULT → extract data_path, lammps_flags, emc_seed (integer or null)
    → immediately write emc_seed to run_log.md header Seeds line (never log -1; log null if RadonPy path)

  [Equilibration]
  Agent(subagent_type="equilibration-worker", description="🟠 Equilibrate {polymer_name}",
        prompt=<gen_prompt.py --stage equil --plan PLAN_PATH --data_path ...>)
    → parse RESULT → extract chain_id, monitor_command, expected_equil_data, npt_tg_prep_data
      npt_tg_prep_data is non-null for rubbery polymers (npt_melt at T_equil_K); null for glassy.
  Write SIMULATION STATE to run_log.md (status=monitoring, + bg task id)
  *** BACKGROUND-WAIT — canonical pattern (referenced by THERMAL_TRACK.md, MECHANICAL_TRACK.md,
      /recover; this is the ONE definition — do not re-paste it, reference it). Replaces blocking Monitor. ***
  Bash(command=monitor_command, run_in_background=true)   # detached waiter; no & needed
  # WHY this works: monitor_command is ALREADY a complete blocking waiter (sentinel-wait + PID-liveness
  # loop, RUN_COMPLETE→exit 0, PROCESS_DEAD_NO_SENTINEL→exit 3). The ONLY reason the old Monitor tool
  # re-armed ~hourly was its fixed 1 h timeout_ms cap — a harness limit, not a property of the command.
  # Backgrounded, it runs to completion untouched and the harness re-invokes you EXACTLY ONCE on exit.
  # >>> NOW END YOUR TURN. <<< Do NOT call get_run_status, spawn the next stage, release a GPU, or
  # "just check on it" in this same turn. Treat it exactly like a backgrounded Agent spawn: launch the
  # waiter, STOP, and wait to be woken. (This wait is a behavioral contract you must keep — unlike the
  # old Monitor, nothing forces you to block, so acting early would consume an incomplete result.)
  # On the completion wakeup (a later turn), branch on the waiter's exit/output — SAME routing as the
  # old Monitor output:
  #   RUN_COMPLETE (exit 0)             → get_run_status(chain_id) → check success/failure → proceed
  #   PROCESS_DEAD_NO_SENTINEL (exit 3) → treat as FAILED → /recover (max 2/worker)
  #   killed / no terminal line         → relaunch the SAME waiter (lossless; SEEN dedups progress)
  # Optional safety net (long runs only, default OFF — re-introduces periodic wakeups): if you do not
  # trust the wakeup on a multi-hour run, arm one long-fallback ScheduleWakeup(1800s+) as a heartbeat.
  get_run_status(chain_id) → check success/failure   # ONLY after the RUN_COMPLETE wakeup, not before

  [Equil-check gate]
  Agent(subagent_type="equilibration-checker", description="🟠 Equil check {polymer_name}",
        prompt=<gen_prompt.py --stage equil-check --plan PLAN_PATH --data_path npt_prod_data_path>)
    → parse RESULT → extract equil_verdict, density_gcm3,
        ct_decay_fraction, ct_tau_relax_ps,
        end_to_end_r_mean_A, end_to_end_r_std_A, end_to_end_n_chains
      → write D-05 to run_log.md (populate Chain Structure Summary rows from these fields)
  If equil_verdict=EXTEND: re-spawn equilibration-worker in extend mode (prompt: mode=extend,
    extend_from_data=<npt_prod_data_path>, extend_ns=1–2, press/engine same, temp=npt_prod_temp_K
    (300 K — the production temperature of the cell, NOT the melt T_equil/T_workflow; passing the
    melt T would re-melt a cooled glassy cell)). It generates a single deterministic npt_extend stage
    via generate_equilibration_workflow(extend_only=True) and submits it. Do NOT hand-write a
    continuation .in. Re-run BACKGROUND-WAIT (launch the waiter, end your turn, resume on the
    RUN_COMPLETE wakeup), then re-run equil-check on npt_extend_out.data (max 2 extensions).
  If equil_verdict=FAIL: write UNRESOLVED and stop

PHASE B — TRACKS (property-conditional)

  [thermal track — if "tg" in properties_requested]
  Read("guides/THERMAL_TRACK.md") now for the full multirate sweep + registry + is_glassy procedure.
  On session restart mid-thermal-track: re-read guides/THERMAL_TRACK.md before resuming.

  Slope-gate hard stop (after multirate analysis — read slope_gate_pass from tg_multirate_result.json):
    Registry rows for this sweep are STAGED (not yet committed) until this gate — see
    guides/THERMAL_TRACK.md "Multirate Tg registry" (deferred write). Rubbery sweeps run with
    --regime rubbery, so slope_gate_pass is True by exemption (rubbery_regime_exemption=True) and
    this hard stop does NOT fire for them — commit the staged rows and proceed.
    if slope_gate_pass == False:   # glassy contamination only
      DO NOT proceed to mechanical track or run-summary.
      Discard the staged registry rows for this sweep (nothing was committed → no churn).
      Spawn recovery: re-run all 3 Tg sweeps from the same equil cell with a new velocity seed.
      Max 2 recovery attempts total; if both fail → write UNRESOLVED to run_log.md and stop.

  [mechanical track — if "bulk_modulus" in properties_requested]
  Read("guides/MECHANICAL_TRACK.md") now for the Murnaghan + deform-fallback + BM extraction procedure.
  On session restart mid-mechanical-track: re-read guides/MECHANICAL_TRACK.md before resuming.

PHASE C — SUMMARY (always)

  [Experimental lookup — run BEFORE run-summary so grading uses condition-matched DB ranges]
  Agent(subagent_type="exp-lookup-worker", description="🟢 Exp lookup {polymer_name}",
        prompt="polymer_name: <canonical name>\npolymer_class: <CLASS>\nT_sim_K: <300 or T_workflow>\n"
               "is_glassy: <from thermal track>\nproperties: <comma-joined>\n"
               "output_path: data/<RUN>/raw/exp_lookup.json")
    → parse RESULT → exp_lookup_path, match_confidence, exp_{tg,density,K}_{min,max}.
  # Thread these ranges into run-summary via the CLI overrides below. Do NOT hand-enter a tight
  # single floor (a too-tight 1.35 density floor caused a 0.07% false FAIL, PVC2). When
  # match_confidence=none or a field is null, OMIT that override — gen_prompt then falls back to
  # its DB lookup / polymer_rules median ±5% band, which is correctly wide.

  # Before spawning run-summary-worker: verify the lammps-engine MCP server is live.
  # In long sessions (>12 h) the MCP connection can drop silently. Do a minimal call
  # (e.g. list_templates) — if it returns, proceed; if it hangs or errors, restart the
  # MCP server before the Agent call.
  # Determine tg_path and slope_gate_pass before spawning run-summary-worker:
  #   SLOPE_GATE=$(jq -r '.slope_gate_pass' data/RUN/raw/tg_multirate_result.json)
  #   RATES_ARR=$(jq -r '.decided_params.tg_rates_K_per_ns' PLAN_PATH)   # e.g. [25,50,100]
  #   if [ "$SLOPE_GATE" = "false" ]; then
  #     TG_PATH="data/RUN/raw/tg_r$(jq '.[length-1]' <<<$RATES_ARR)/tg_summary.json"  # highest rate (fallback)
  #   else
  #     TG_PATH="data/RUN/raw/tg_r$(jq '.[0]' <<<$RATES_ARR)/tg_summary.json"         # slowest rate (convention)
  #   fi
  # Exp ranges: prefer the exp-lookup-worker RESULT (condition-matched). Thread each non-null field
  # as a CLI override; omit nulls so gen_prompt falls back to its DB/polymer_rules ±5% band.
  #   --exp_tg_min/--exp_tg_max        (from exp_tg_min_K / exp_tg_max_K)
  #   --exp_density_min/--exp_density_max  (from exp_density_min_gcm3 / exp_density_max_gcm3)
  #   --exp_K_min/--exp_K_max          (from exp_K_min_GPa / exp_K_max_GPa; else polymer_rules exp_K_GPa)
  # NEVER hand-enter a single tight floor — that is what caused the PVC2 density false FAIL.
  Agent(subagent_type="run-summary-worker", description="🟢 Run summary {polymer_name}",
        prompt=<gen_prompt.py --stage run-summary --plan PLAN_PATH
               --smiles ... --ff ... --tg_fit_quality ... --d05 equil_verdict
               --n_replicates <distinct replicates in the multirate registry>
               --tg_path <TG_PATH (see above — slowest rate if slope_gate=True, highest rate if False)>
               --slope_gate_pass <true|false from tg_multirate_result.json>
               [--exp_tg_min ... --exp_tg_max ...] [--exp_density_min ... --exp_density_max ...]
               --exp_K_min <exp-lookup or polymer_rules exp_K_GPa.min> --exp_K_max <exp_K_GPa.max>>)
    → parse RESULT → run_summary_path → write RESULTS to run_log.md
    → if run_summary tg.primary_fit_invalid==True, flag the headline Tg as unreliable in run_log.md
      (the fit violated a hard physics constraint and no valid alternative existed).

  [Capture errors + improvements — to MEMORY ONLY, last action of the run]
  Before declaring the run done, promote pipeline-level lessons to memory as `feedback` entries
  (per the # Memory rules) so /ingest-memory can act on them later:
    1. Errors encountered during the run (symptom → root cause → fix/workaround).
    2. Room-for-improvement / codebase friction (confusing/wrong guide, MCP-tool quirk,
       missing/incorrect polymer_rules param, awkward worker contract).
  Write these to the orchestrator's own auto-memory (`~/.claude/projects/<project-slug>/memory/` — the dir named in the # Memory system reminder)
  and/or the relevant worker's canonical repo-root `.claude/agent-memory/<worker>/` dir (the absolute
  path named in that worker's agent definition — NEVER resolved relative to a worker's cwd, NEVER a
  `.claude/` created under a work_dir or data/<run>/ subdir) — these are the inputs
  /ingest-memory consumes. Do NOT put any of this in run_log.md: the run log is for users to
  interpret the simulation, not to fix the workflow. (RECOVERIES stays as-is — it documents what
  happened to the simulation, per cross-track rule 1 — but no new improvement/error-capture content
  is added to the run log.)
```

### Cross-run protocol

Validate each worker result against `run_plan.json` `planned_stages[].success_criteria`; `/recover` if not met (max 2 attempts/worker), then write UNRESOLVED to run_log.md and stop.
A probe result contradicting a plan assumption (wrong FF, D-08 mismatch) routes back to the planner (re-plan → re-critic); never let a worker improvise. For a planned `hardware_benchmark` probe: run `scripts/calibrate_hardware.py --cell <.data> --ff <fam>` politely before the affected GPU stage (idle-GPU + spare cores; never `--allow-busy`).
Session restart: read SIMULATION STATE table in run_log.md → find `status=monitoring` → `get_run_status(id)` → if still running, `watch_run(id)` → relaunch the waiter via BACKGROUND-WAIT (`Bash(command=monitor_command, run_in_background=true)`) and end your turn; if already completed, proceed. If in Phase B re-read the active track guide first.

---

<!-- CROSS_STAGE_RULES_START -->
## Cross-Track Rules (Always Active — Memorize These)

These rules are inlined into every worker prompt by `gen_prompt.py`. They apply regardless of which worker or track is running.

0. **GPU is used for ALL simulation runs** — always pass explicit `gpu_ids` and `mpi`; never leave them unset or default
1. **Fill `run_log.md` in real time** — log each DECISION row when made, each RECOVERY block immediately after resolving an error; do not reconstruct at the end
2. **Record all seeds before submitting any job** — log EMC seed, SEED_HOT, and SEED_COLD in the run_log header. For replication studies, use fixed seeds from `guides/REVISION_PARAMS.md`. For exploratory runs, read seeds back from job output and log them immediately after submission.
3. **Check for existing writers before killing any process** — before killing and relaunching any LAMMPS run, run `lsof | grep <log_filename>` to check for existing writers. If another writer is present (concurrent orchestrator session), do NOT launch — coordinate via user first. A double-launch corrupts the shared log and requires a full restart from step 0.
4. **Log the exact GPU claim label** — after any GPU claim (`pick_gpu.py claim --run <LABEL>`), copy the `run` field from the JSON response into the SIMULATION STATE table. Use that exact string verbatim at release (`pick_gpu.py release --run <LABEL>`). A label mismatch at release silently leaves the GPU stuck as claimed.
5. **Log repo-relative run paths in memory** — when recording run artifacts or paths in any `.claude/agent-memory/**` file, write them repo-relative (`data/<run>/...`), never machine-absolute (`/home/<user>/...`). Keeps captures portable across the revision machines so integration needs no path sanitization. The memory file ITSELF must live only in the repo-root `.claude/agent-memory/<worker>/` dir (the absolute path in your agent definition) — never a `.claude/` created under a work_dir or data/<run>/ subdir.
<!-- CROSS_STAGE_RULES_END -->

