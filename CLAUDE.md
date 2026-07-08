# PolyJarvis

AI agent for autonomous polymer MD simulation. Given a SMILES string, runs the full pipeline — molecular construction (RadonPy/EMC MCP servers) → equilibration → Tg sweep → property extraction (LAMMPS engine MCP server, local GPU) — and reports Tg, density, and bulk modulus validated against experiment.

## Key Directories

| Path | Contents |
|------|----------|
| `orchestration/` | Orchestrator-read docs (`FOUNDATION.md`, `THERMAL_TRACK.md`, `MECHANICAL_TRACK.md`, `SUMMARY.md`), `decision_policy.json` (planner/critic framework), and CLI helpers (`gen_prompt.py`, `select_tg_path.py`, `pick_gpu.py`) |
| `guides/` | Worker guides inlined into worker prompts by `gen_prompt.py` (never read them directly); `polymer_rules.json` (per-class Tg/density/DP/annealing) |
| `data/TEMPLATE/run_log.md` | Run log template — copied to `data/[RUN]/run_log.md` at task start |
| `data/[RUN]/` | All run files: `run_log.md`, `lammps/`, `raw/`, `graphs/` (git-excluded) |
| `.understand-anything/knowledge-graph.json` | Codebase map (core system, git-excluded). **Query it before file-walking** |

**Codebase:** before file-walking, query `.understand-anything/knowledge-graph.json` (built by `/understand`; covers orchestration/, mcp-servers/, db/, guides/, `.claude/` — NOT tools/, tests/, hardware/, manuscript/, docs/). Plain JSON (`nodes`=id/type/name/summary/tags, `edges`=source/target/type) — `jq` it, or use `/understand-chat|explain|diff`. It's a snapshot and a **map, not ground truth** (lazy imports under-captured) — verify against the file; for out-of-scope dirs use normal search.

**Paths:** all run files live under `data/<run_name>/` (repo-relative, git-excluded); use absolute paths in tool calls. `<lammps_base>` = `<repo_root>/data/<run_name>/lammps/` (`gen_prompt.py` derives `<repo_root>` from its own location — never hard-code `/home/<user>/...`). Equilibration paths are tool-defined — use worker RESULT dict keys (`npt_production_dir`, `npt_prod300_data`, ...), never construct them manually.

**Run log:** copy the template at task start; fill it in **real time**, not reconstructed at the end. The RECOVERIES section is the primary evidence of agent value — write a block immediately after resolving any failure.

## Orchestrator Pattern (Multi-Agent Mode)

Default mode is multi-agent: the orchestrator (this session) spawns stateless specialist workers via `Agent(subagent_type=...)` and holds all state + recovery logic. Workers group into **tracks** — foundation runs first and feeds all; mechanical reads `is_glassy` from thermal (or `glassy_hint` when thermal is skipped). Models are set in each agent definition.

| Worker (color) | Track | Role |
|------|------|------|
| ⚪ `literature-grounding-worker` | setup | off-table / low-medium confidence only — SMILES+class → DOI-verified `literature_grounding.json` feeding the planner |
| 🟡 `planner` | setup | goal + class → `run_plan.json` (deterministic if confidence=high; reasoned otherwise) |
| 🔴 `critic` | setup | proposed `run_plan.json` → approved \| revise \| escalate |
| 🔵 `molecule-builder` | foundation | SMILES → `.data` file (EMC or RadonPy) |
| 🟠 `equilibration-worker` | foundation | `.data` → submitted equilibration chain |
| 🟠 `equilibration-checker` | foundation | equil logs → PASS/EXTEND/FAIL verdict + density |
| 🟣 `tg-sweep-worker` | thermal | equil `.data` → submitted Tg sweep run |
| 🟢 `tg-analysis-worker` | thermal | Tg sweep log → Tg_K, CTE (α_g, α_r), ΔCp |
| 🟠 `murnaghan-worker` | mechanical (primary) | equil `.data` → Murnaghan pressure series (glassy 300 K; rubbery T>Tg) |
| 🔵 `deform-worker` | mechanical (fallback) | NPT `.data` → 3-direction uniaxial deformation run |
| 🟢 `bulk-modulus-extractor` | mechanical | Murnaghan/deform/fluctuation logs → bulk_modulus_GPa |
| 🟢 `exp-lookup-worker` | summary | polymer name/class → condition-matched exp ranges (Tg/density/K) |
| 🟢 `run-summary-worker` | summary | all output JSONs → `run_summary.json` |

### Orchestrator workflow

```
SETUP  (all Agent() calls below use gen_prompt.py-generated prompts unless a field list is given)
  Read CLAUDE.md at startup. Copy data/TEMPLATE/run_log.md → data/[RUN]/run_log.md.
  classify_polymer(smiles) if class unknown → CLASS_ID. builder_status unsupported
    (`jq -r '.classes.CLASS_ID.builder_status // "supported"' guides/polymer_rules.json`)
    → write UNRESOLVED to run_log.md and stop.
  properties_requested = task TARGET_PROPERTIES lowercased set; "all"/absent → {density,tg,bulk_modulus}.
    Write "Requested: {properties_requested}" to run_log.md.

  GROUND (off-table / low-medium confidence ONLY — skip for confidence=high so the deterministic,
    byte-identical plan path stays untouched by web nondeterminism):
    CONF=`jq -r '.classes.CLASS_ID.confidence // "offtable"' guides/polymer_rules.json`
      (class key absent or classify "unknown" ⇒ offtable)
    If CONF in {low, medium, offtable}:
      ⚪ literature-grounding-worker ← polymer_name, polymer_class(or offtable), smiles,
        properties_requested, confidence=CONF, output_path=data/<RUN>/raw/literature_grounding.json
        → RESULT.grounding_path = GROUNDING_PATH  (advisory planning evidence only, DOI-verified;
          NEVER used as run-summary grading bounds — exp-lookup owns those in Phase C).
      Pass grounding_path: GROUNDING_PATH as an extra planner input.
    If CONF=high: skip; do NOT pass grounding_path.

  PLAN  🟡 planner ← run_name, smiles, polymer_class, properties_requested,
    work_dir=data/<RUN>/lammps [, grounding_path]
    → plan_path (PLAN_PATH), plan_mode, confidence, critique_status.
    Write D-00 pointer to run_log.md header: PLAN_PATH + plan_mode + confidence.

  CRITIC loop (max 2 rounds)  🔴 critic ← run_plan_path=PLAN_PATH, critic_round=N
    → approved → proceed | revise → re-spawn planner with the findings, re-critique |
      escalate → write UNRESOLVED to run_log.md and stop.
    Deterministic plans (confidence=high) approve in round 1 with 0 findings — no loop.

  Thread the approved plan: EVERY gen_prompt.py call MUST include --plan PLAN_PATH (its
    decided_params drive the worker prompts; never read polymer_rules.json manually):
    `python3 orchestration/gen_prompt.py --stage <STAGE> --run_name <RUN> --polymer_class <CLASS> --plan PLAN_PATH [--data_path ...]`
  T_workflow_K=`jq -r '.decided_params.T_workflow_K // 600' PLAN_PATH` → write to run_log.md header.
  If "tg" not in properties_requested: glassy_hint = (T_workflow_K != 300.0)

  Hardware (before any GPU stage):
    GPU_PER_RUN=`jq -r '.decided_params.gpu_per_run // empty' PLAN_PATH` (empty ⇒ policy-derived, 1 GPU).
    When the plan pins a D-08 override (gpu_per_run/engine/mpi_ranks in decided_params), let
      gen_prompt.py thread it into the worker prompt — do NOT also pass --gpu_ids/--mpi_ranks
      (CLI wins and would shadow the plan).
    Claim at submit: `orchestration/pick_gpu.py --json claim --run <RUN> --need ${GPU_PER_RUN:-1}`
      → success `{"claimed":[ids],...}`: use that list verbatim as the worker's gpu_ids;
        shortfall (`{"error":...}`, exit 1): defer/retry, do not force.
      Release on completion (`pick_gpu.py release --run <RUN>`). Write engine/gpu_per_run/mpi to D-08 row.

BACKGROUND-WAIT  (canonical wait pattern — FOUNDATION/THERMAL/MECHANICAL guides and /recover
  reference it by name; never block in-conversation). After a worker returns a monitor_command:
  write SIMULATION STATE to run_log.md (status=monitoring + bg task id), then
  `Bash(command=monitor_command, run_in_background=true)` (detached waiter; no & needed) and END
  YOUR TURN — launch, STOP, get woken ONCE on exit. A PreToolUse hook also reminds you at launch:
  do NOT get_run_status / spawn the next stage / release a GPU this turn. On the exit wakeup, route
  on the exit code:
    RUN_COMPLETE (0)             → get_run_status(chain_id) → check success/failure → proceed
    PROCESS_DEAD_NO_SENTINEL (3) → FAILED → /recover (max 2/worker)
    killed / no terminal line    → relaunch the SAME waiter (lossless; SEEN dedups progress)

PHASE A — FOUNDATION (always)
  Read orchestration/FOUNDATION.md — build → equilibration (BACKGROUND-WAIT) → equil-check gate
  (density, D-05) + EXTEND branch. Re-read after any mid-phase session restart.

PHASE B — TRACKS (property-conditional)
  thermal (if "tg"): Read orchestration/THERMAL_TRACK.md — owns the multirate sweep loop, the
    slope-gate hard stop + per-class structural fallback, and is_glassy. Gating consequence: if
    tg_multirate_result.json slope_gate_pass==False (glassy only; rubbery exempt), do NOT proceed
    to mechanical/run-summary — follow the guide's recovery ladder, UNLESS the plan marks it
    structural (decided_params.tg_slope_gate_fallback), then use the single-rate fallback.
  mechanical (if "bulk_modulus"): Read orchestration/MECHANICAL_TRACK.md — owns Murnaghan-primary
    + deform-fallback + BM extraction.
  Re-read the active track guide before resuming after any mid-track restart.

PHASE C — SUMMARY (always)
  Read orchestration/SUMMARY.md — owns exp-lookup (BEFORE run-summary) → tg_path via
  select_tg_path.py → run-summary → memory capture.
```

### Cross-run protocol

Validate each worker result against `run_plan.json` `planned_stages[].success_criteria`; `/recover` if not met (max 2 attempts/worker), then write UNRESOLVED to run_log.md and stop. A probe result contradicting a plan assumption (wrong FF, D-08 mismatch) routes back to the planner (re-plan → re-critic) — never let a worker improvise; for a planned `hardware_benchmark` probe run `hardware/calibrate_hardware.py --cell <.data> --ff <fam>` politely (idle GPU + spare cores; never `--allow-busy`).
Session restart: read the SIMULATION STATE table → find `status=monitoring` → `get_run_status(id)` → if still running, `watch_run(id)` and relaunch the waiter via BACKGROUND-WAIT, then end your turn; if completed, proceed. In Phase A/B/C re-read the active phase guide first.

<!-- CROSS_STAGE_RULES_START -->
## Cross-Track Rules (Always Active — Memorize These)

Inlined into every worker prompt by `gen_prompt.py`; apply regardless of worker or track.

0. **GPU is used for ALL simulation runs** — always pass explicit `gpu_ids` and `mpi`; never leave them unset or default.
1. **Fill `run_log.md` in real time** — each DECISION row when made, each RECOVERY block immediately after resolving an error; never reconstruct at the end.
2. **Record all seeds before submitting any job** — log EMC seed, SEED_HOT, SEED_COLD in the run_log header. Replication studies: fixed seeds from `guides/REVISION_PARAMS.md`. Exploratory runs: read seeds back from job output and log them immediately after submission.
3. **Check for existing writers before killing any process** — run `lsof | grep <log_filename>`; if another writer is present (concurrent session), do NOT launch, coordinate via the user (a double-launch corrupts the shared log). Backstop: `run_lammps_script`/`run_lammps_chain`/`run_bulk_modulus_series` refuse to launch when a live process holds the target log open (`status=error`, `conflicting_writers`) — kill the stale writer then resubmit; pass `allow_concurrent_writer=True` only after confirming it's stale. The backstop is a safety net, not a substitute for the manual check.
4. **Log the exact GPU claim label** — copy the `run` field from `pick_gpu.py claim`'s JSON into the SIMULATION STATE table and use it verbatim at release. A label mismatch silently leaves the GPU stuck as claimed.
5. **Log repo-relative run paths in memory** — in any `.claude/agent-memory/**` file write `data/<run>/...`, never `/home/<user>/...` (keeps captures portable). The memory file itself lives ONLY in the repo-root `.claude/agent-memory/<worker>/` dir (the absolute path in the worker's agent definition) — never a `.claude/` under a work_dir or `data/<run>/` subdir.
<!-- CROSS_STAGE_RULES_END -->
