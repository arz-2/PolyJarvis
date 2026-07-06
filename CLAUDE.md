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
| `literature-grounding-worker` | ⚪ gray | **setup (off-table / low-medium confidence only)** — SMILES + class → DOI-verified `literature_grounding.json` (FF, electrostatics, DP/nchain, density & Tg targets) that feeds the planner | sonnet |
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
  Read CLAUDE.md at startup. At Phase B entry, Read guides/THERMAL_TRACK.md (if tg requested)
  and/or guides/MECHANICAL_TRACK.md (if bulk_modulus requested). Never read worker guides
  (THERMAL_SWEEP.md, BM_ANALYSIS.md, etc.) directly — gen_prompt.py inlines those into worker prompts.
  Copy data/TEMPLATE/run_log.md → data/[RUN]/run_log.md
  classify_polymer(smiles) if class unknown → CLASS_ID. Check builder_status:
    `jq -r '.classes.CLASS_ID.builder_status // "supported"' guides/polymer_rules.json`
    == "unsupported" → write UNRESOLVED to run_log.md and stop.
  properties_requested = task TARGET_PROPERTIES normalized to a lowercase set;
    "all" or field absent → {"density", "tg", "bulk_modulus"}.
    Write "Requested: {properties_requested}" to run_log.md metadata line.
  GROUND (off-table / low-medium confidence ONLY — skip for confidence=high so the deterministic,
  byte-identical plan path is untouched by web nondeterminism):
    `CONF=$(jq -r '.classes.CLASS_ID.confidence // "offtable"' guides/polymer_rules.json)`
    (class key absent or classify_polymer "unknown" ⇒ offtable)
    If CONF in {low, medium, offtable}:
      Agent(subagent_type="literature-grounding-worker", description="⚪ Ground {polymer_name}",
          prompt="polymer_name: <canonical name>\npolymer_class: <CLASS_ID or offtable>\n"
                 "smiles: <SMILES>\nproperties_requested: <comma-joined>\nconfidence: <CONF>\n"
                 "output_path: data/<RUN>/raw/literature_grounding.json")
        → RESULT.grounding_path = GROUNDING_PATH. Advisory planning evidence only (DOI-verified);
          never used as run-summary grading bounds (exp-lookup owns those in Phase C).
      Pass `grounding_path: GROUNDING_PATH` as an extra line in the planner prompt below.
    If CONF=high: skip this step; do NOT pass grounding_path.
  PLAN — Agent(subagent_type="planner", description="🟡 Plan {polymer_name}",
      prompt="run_name: <RUN>\nsmiles: <SMILES>\npolymer_class: <CLASS_ID>\nproperties_requested: <comma-joined>\nwork_dir: data/<RUN>/lammps"
             + (off-table/low-medium: "\ngrounding_path: GROUNDING_PATH"))
    → RESULT → plan_path (PLAN_PATH), plan_mode, confidence, critique_status.
    Write D-00 (plan) pointer to run_log.md header: PLAN_PATH + plan_mode + confidence.
  CRITIC loop (max 2 rounds) — Agent(subagent_type="critic", description="🔴 Critique plan",
      prompt="run_plan_path: PLAN_PATH\ncritic_round: <N>")
    → status=approved → proceed | revise → re-spawn planner with the findings, re-critique |
      escalate → write UNRESOLVED to run_log.md and stop.
    Deterministic plans (confidence=high) approve in round 1 with 0 findings — no loop.
  Thread the approved plan: EVERY gen_prompt.py call MUST include `--plan PLAN_PATH` — the plan's
  decided_params drive the worker prompts; never read polymer_rules.json manually:
    `python3 scripts/gen_prompt.py --stage <STAGE> --run_name <RUN> --polymer_class <CLASS> --plan PLAN_PATH [--data_path ...]`
  `T_workflow_K=$(jq -r '.decided_params.T_workflow_K // 600' PLAN_PATH)` → write to run_log.md
    header (alongside plan_path + confidence).
  If "tg" not in properties_requested: glassy_hint = (T_workflow_K != 300.0)
  Hardware (before any GPU stage):
    `GPU_PER_RUN=$(jq -r '.decided_params.gpu_per_run // empty' PLAN_PATH)` (empty ⇒ policy-derived, 1 GPU)
    When the plan pins a D-08_hardware override (gpu_per_run/engine/mpi_ranks in decided_params),
    let gen_prompt.py thread it into the worker prompt — do NOT also pass --gpu_ids/--mpi_ranks
    (CLI wins and would shadow the plan). Claim the matching GPU count at submit time:
    `scripts/pick_gpu.py --json claim --run <RUN> --need ${GPU_PER_RUN:-1}` → on success
    `{"claimed":[ids],...}` use that list verbatim as the worker's gpu_ids; on shortfall
    (`{"error":...,"available":[…]}`, exit 1) defer/retry, do not force. Release on completion
    (`pick_gpu.py release --run <RUN>`). Write engine/gpu_per_run/mpi to run_log.md (D-08 row).

PHASE A — FOUNDATION (always)

  [Build]
  Agent(subagent_type="molecule-builder", description="🔵 Build {polymer_name} cell",
        prompt=<gen_prompt.py --stage build --plan PLAN_PATH>)
    → RESULT → data_path, lammps_flags, emc_seed (integer or null)
    → immediately write emc_seed to run_log.md header Seeds line (never log -1; log null if RadonPy path)

  [Equilibration]
  Agent(subagent_type="equilibration-worker", description="🟠 Equilibrate {polymer_name}",
        prompt=<gen_prompt.py --stage equil --plan PLAN_PATH --data_path ...>)
    → RESULT → chain_id, monitor_command, expected_equil_data, npt_tg_prep_data
      (npt_tg_prep_data non-null for rubbery polymers — npt_melt at T_equil_K; null for glassy)
  Write SIMULATION STATE to run_log.md (status=monitoring, + bg task id)
  *** BACKGROUND-WAIT — canonical wait pattern. Defined ONCE here; THERMAL_TRACK.md,
      MECHANICAL_TRACK.md, /recover reference it by name. Never block in-conversation. ***
  Bash(command=monitor_command, run_in_background=true)   # detached waiter; no & needed
  THEN END YOUR TURN — launch, STOP, get woken ONCE on exit, like a backgrounded Agent spawn.
  # Behavioral contract (a PreToolUse hook also reminds you at launch): do NOT get_run_status /
  # spawn the next stage / release a GPU this turn. On the exit wakeup, route on the exit code:
  #   RUN_COMPLETE (exit 0)               → get_run_status(chain_id) → check success/failure → proceed
  #   PROCESS_DEAD_NO_SENTINEL (exit 3)   → FAILED → /recover (max 2/worker)
  #   killed / no terminal line (restart) → relaunch the SAME waiter (lossless; SEEN dedups progress)

  [Equil-check gate]
  Agent(subagent_type="equilibration-checker", description="🟠 Equil check {polymer_name}",
        prompt=<gen_prompt.py --stage equil-check --plan PLAN_PATH --data_path npt_prod_data_path>)
    → RESULT → equil_verdict, density_gcm3, ct_decay_fraction, ct_tau_relax_ps,
        end_to_end_r_mean_A, end_to_end_r_std_A, end_to_end_n_chains
      → write D-05 to run_log.md (populate Chain Structure Summary rows from these fields)
  If equil_verdict=EXTEND: re-spawn equilibration-worker in extend mode (prompt: mode=extend,
    extend_from_data=<npt_prod_data_path>, extend_ns=1–2, press/engine same, temp=npt_prod_temp_K
    — the 300 K production temperature of the cell, NOT the melt T_equil/T_workflow; the melt T
    would re-melt a cooled glassy cell). The worker generates a single deterministic npt_extend
    stage via generate_equilibration_workflow(extend_only=True) and submits it — do NOT hand-write
    a continuation .in. Re-run BACKGROUND-WAIT, then re-run equil-check on npt_extend_out.data
    (max 2 extensions).
  If equil_verdict=FAIL: write UNRESOLVED and stop

PHASE B — TRACKS (property-conditional)

  [thermal track — if "tg" in properties_requested]
  Read("guides/THERMAL_TRACK.md") now — it owns the multirate sweep loop, the Tg registry
  (deferred write), the slope-gate hard stop, and the is_glassy determination. Re-read it before
  resuming after any mid-track session restart.
  Slope-gate hard stop (glassy only; rubbery sweeps are exempt): if tg_multirate_result.json has
  slope_gate_pass==False, do NOT proceed to the mechanical track or run-summary — follow the
  track guide's recovery ladder (discard staged registry rows, reroll seed, max 2 attempts,
  else UNRESOLVED).

  [mechanical track — if "bulk_modulus" in properties_requested]
  Read("guides/MECHANICAL_TRACK.md") now — it owns the Murnaghan-primary + deform-fallback + BM
  extraction procedure. Re-read it before resuming after any mid-track session restart.

PHASE C — SUMMARY (always)

  [Experimental lookup — run BEFORE run-summary so grading uses condition-matched DB ranges]
  Agent(subagent_type="exp-lookup-worker", description="🟢 Exp lookup {polymer_name}",
        prompt="polymer_name: <canonical name>\npolymer_class: <CLASS>\nT_sim_K: <300 or T_workflow>\n"
               "is_glassy: <from thermal track>\nproperties: <comma-joined>\n"
               "output_path: data/<RUN>/raw/exp_lookup.json")
    → RESULT → exp_lookup_path, match_confidence, exp_{tg,density,K}_{min,max}.
  # Thread these ranges into run-summary via the CLI overrides below. NEVER hand-enter a tight
  # single floor (a too-tight 1.35 density floor caused a 0.07% false FAIL, PVC2). When
  # match_confidence=none or a field is null, OMIT that override — gen_prompt then falls back to
  # its DB lookup / polymer_rules median ±5% band, which is correctly wide.

  # Before spawning run-summary-worker:
  # 1. Verify the lammps-engine MCP server is live (long sessions >12 h drop the connection
  #    silently): a minimal call (e.g. list_templates) must return; if it hangs/errors, restart
  #    the MCP server first.
  # 2. Determine tg_path + slope_gate_pass with the helper — do NOT hand-derive the path (the
  #    PLA3 footgun); the helper encodes the slowest/highest-rate convention:
  #    eval "$(python3 scripts/select_tg_path.py --plan PLAN_PATH --multirate data/RUN/raw/tg_multirate_result.json)"
  #    # → sets TG_PATH (slowest rate if gate passed, highest if failed) and SLOPE_GATE (true|false)
  # 3. Exp ranges: thread each non-null exp-lookup field as a CLI override; omit nulls so
  #    gen_prompt falls back to its DB/polymer_rules ±5% band:
  #    --exp_tg_min/--exp_tg_max, --exp_density_min/--exp_density_max,
  #    --exp_K_min/--exp_K_max (else polymer_rules exp_K_GPa).
  Agent(subagent_type="run-summary-worker", description="🟢 Run summary {polymer_name}",
        prompt=<gen_prompt.py --stage run-summary --plan PLAN_PATH
               --smiles ... --ff ... --tg_fit_quality ... --d05 equil_verdict
               --n_replicates <distinct replicates in the multirate registry>
               --tg_path <TG_PATH> --slope_gate_pass <SLOPE_GATE>
               [--exp_tg_min ... --exp_tg_max ...] [--exp_density_min ... --exp_density_max ...]
               --exp_K_min ... --exp_K_max ...>)
    → RESULT → run_summary_path → write RESULTS to run_log.md
    → if run_summary tg.primary_fit_invalid==True, flag the headline Tg as unreliable in run_log.md
      (the fit violated a hard physics constraint and no valid alternative existed).

  [Capture errors + improvements — to MEMORY ONLY, last action of the run]
  Before declaring the run done, promote pipeline-level lessons to memory as `feedback` entries
  (per the # Memory rules) so /ingest-memory can act on them later: (1) errors encountered
  (symptom → root cause → fix/workaround); (2) codebase friction (confusing/wrong guide, MCP-tool
  quirk, missing/incorrect polymer_rules param, awkward worker contract).
  Write them to the orchestrator's own auto-memory dir and/or the relevant worker's canonical
  repo-root `.claude/agent-memory/<worker>/` dir (the absolute path named in that worker's agent
  definition — never a `.claude/` created under a work_dir or data/<run>/ subdir); these are the
  inputs /ingest-memory consumes. Do NOT put any of this in run_log.md — the run log is for users
  to interpret the simulation, not to fix the workflow (RECOVERIES stays, per cross-track rule 1).
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
3. **Check for existing writers before killing any process** — before killing and relaunching any LAMMPS run, run `lsof | grep <log_filename>` to check for existing writers. If another writer is present (concurrent orchestrator session), do NOT launch — coordinate via user first. A double-launch corrupts the shared log and requires a full restart from step 0. As a backstop, `run_lammps_script`/`run_lammps_chain`/`run_bulk_modulus_series` now refuse to launch when a live LAMMPS/MPI process already holds the target log open, returning `status=error` with `conflicting_writers` (kill the stale writer, then resubmit; pass `allow_concurrent_writer=True` only after confirming the writer is stale). This is a safety net, not a substitute for the manual check.
4. **Log the exact GPU claim label** — after any GPU claim (`pick_gpu.py claim --run <LABEL>`), copy the `run` field from the JSON response into the SIMULATION STATE table. Use that exact string verbatim at release (`pick_gpu.py release --run <LABEL>`). A label mismatch at release silently leaves the GPU stuck as claimed.
5. **Log repo-relative run paths in memory** — when recording run artifacts or paths in any `.claude/agent-memory/**` file, write them repo-relative (`data/<run>/...`), never machine-absolute (`/home/<user>/...`). Keeps captures portable across the revision machines so integration needs no path sanitization. The memory file ITSELF must live only in the repo-root `.claude/agent-memory/<worker>/` dir (the absolute path in your agent definition) — never a `.claude/` created under a work_dir or data/<run>/ subdir.
<!-- CROSS_STAGE_RULES_END -->
