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
    → parse RESULT → extract data_path, lammps_flags

  [Equilibration]
  Agent(subagent_type="equilibration-worker", description="🟠 Equilibrate {polymer_name}",
        prompt=<gen_prompt.py --stage equil --plan PLAN_PATH --data_path ...>)
    → parse RESULT → extract chain_id, monitor_command, expected_equil_data
  Write SIMULATION STATE to run_log.md (status=monitoring)
  Monitor(command=monitor_command, timeout_ms=3600000)
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
  Read("guides/THERMAL_TRACK.md") now for the full multirate sweep + registry + is_glassy procedure.
  On session restart mid-thermal-track: re-read guides/THERMAL_TRACK.md before resuming.

  [mechanical track — if "bulk_modulus" in properties_requested]
  Read("guides/MECHANICAL_TRACK.md") now for the Murnaghan + deform-fallback + BM extraction procedure.
  On session restart mid-mechanical-track: re-read guides/MECHANICAL_TRACK.md before resuming.

PHASE C — SUMMARY (always)

  Agent(subagent_type="run-summary-worker", description="🟢 Run summary {polymer_name}",
        prompt=<gen_prompt.py --stage run-summary --plan PLAN_PATH
               --smiles ... --ff ... --tg_fit_quality ... --d05 equil_verdict
               --n_replicates <distinct replicates in the multirate registry>>)  # multirate Tg
    → parse RESULT → run_summary_path → write RESULTS to run_log.md
```

### Cross-run protocol

Validate each worker result against `run_plan.json` `planned_stages[].success_criteria`; `/recover` if not met (max 2 attempts/worker), then write UNRESOLVED to run_log.md and stop.
A probe result contradicting a plan assumption (wrong FF, D-08 mismatch) routes back to the planner (re-plan → re-critic); never let a worker improvise. For a planned `hardware_benchmark` probe: run `scripts/calibrate_hardware.py --cell <.data> --ff <fam>` politely before the affected GPU stage (idle-GPU + spare cores; never `--allow-busy`).
Session restart: read SIMULATION STATE table in run_log.md → find `status=monitoring` → `get_run_status(id)` → `watch_run(id)` → re-issue Monitor; if in Phase B re-read the active track guide first.

---

<!-- CROSS_STAGE_RULES_START -->
## Cross-Track Rules (Always Active — Memorize These)

These rules are inlined into every worker prompt by `gen_prompt.py`. They apply regardless of which worker or track is running.

0. **GPU is used for ALL simulation runs** — always pass explicit `gpu_ids` and `mpi`; never leave them unset or default
1. **Fill `run_log.md` in real time** — log each DECISION row when made, each RECOVERY block immediately after resolving an error; do not reconstruct at the end
2. **Record all seeds before submitting any job** — log EMC seed, SEED_HOT, and SEED_COLD in the run_log header. For replication studies, use fixed seeds from `guides/REVISION_PARAMS.md`. For exploratory runs, read seeds back from job output and log them immediately after submission.
<!-- CROSS_STAGE_RULES_END -->

