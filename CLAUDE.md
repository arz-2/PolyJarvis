# PolyJarvis

AI agent for autonomous polymer MD simulation. Given a SMILES string, runs the full pipeline — molecular construction (RadonPy/EMC MCP servers) → equilibration → track sweeps → property extraction.

## Key Directories

| Path | Contents |
|------|----------|
| `orchestration/` | `decision_policy.json`; `tracks/` — orchestrator-read phase docs (`FOUNDATION.md`, `THERMAL_TRACK.md`, `MECHANICAL_TRACK.md`, `SUMMARY.md`, `DETERMINISTIC_REPLICATE.md`); `scripts/` — CLI helpers (`gen_prompt.py`, `select_tg_path.py`, `pick_gpu.py`, `canon_smiles.py`, `make_deterministic_plan.py`, `apply_cached_characterization.py`) |
| `guides/` | Worker guides inlined into worker prompts by `gen_prompt.py`; `polymer_rules.json`; `system_characterization_cache.json` |
| `data/TEMPLATE/run_log.md` | Run log template — copied to `data/[RUN]/run_log.md` at task start |
| `data/[RUN]/` | All run files: `run_log.md`, `lammps/`, `raw/`, `graphs/` |

**Paths:** all run files live under `data/<run_name>/` (repo-relative, git-excluded); use absolute paths in tool calls. Equilibration paths are tool-defined — use worker RESULT dict keys, never construct them manually.

**Run log:** copy the template at task start; fill it in real time, not reconstructed at the end.

## Orchestrator Pattern

Default mode is multi-agent: the orchestrator (this session) spawns stateless specialist workers via `Agent(subagent_type=...)` and holds all state + recovery logic. Workers group into **tracks** — foundation runs first and feeds all.

| Worker (color) | Track | Role |
|------|------|------|
| ⚪ `literature-grounding-worker` | setup | for every not-yet-validated SMILES — SMILES+class → DOI-verified `literature_grounding.json` feeding the planner |
| 🟡 `planner` | setup | goal + class → `run_plan.json` (deterministic if this exact SMILES is protocol_validated for the requested properties; reasoned otherwise) |
| 🔴 `critic` | setup | proposed `run_plan.json` → approved \| revise \| escalate |
| 🔵 `molecule-builder` | foundation | SMILES → `.data` file (EMC or RadonPy) |
| 🟠 `equilibration-worker` | foundation | `.data` → submitted equilibration chain |
| 🟠 `equilibration-checker` | foundation | equil logs → PASS/EXTEND/FAIL verdict + density |
| 🟣 `tg-sweep-worker` | thermal | equil `.data` → submitted Tg sweep run |
| 🟢 `tg-analysis-worker` | thermal | Tg sweep log → Tg_K, CTE (α_g, α_r), ΔCp |
| 🟠 `murnaghan-worker` | mechanical (primary) | equil `.data` → Murnaghan pressure series (glassy 300 K; rubbery T>Tg) |
| 🔵 `deform-worker` | mechanical (fallback) | NPT `.data` → uniaxial deformation run (primary + paired slow-rate sensitivity check) |
| 🟢 `bulk-modulus-extractor` | mechanical | Murnaghan/deform/fluctuation logs → bulk_modulus_GPa |
| 🟢 `exp-lookup-worker` | summary | polymer name/class → condition-matched exp ranges (Tg/density/K) |
| 🟢 `run-summary-worker` | summary | all output JSONs → `run_summary.json` |

### Orchestrator workflow

```
SETUP
  Read this file. Copy data/TEMPLATE/run_log.md → data/[RUN]/run_log.md. classify_polymer(smiles)
  if class unknown; write UNRESOLVED and stop if builder_status is unsupported. Note
  properties_requested in the run log header.

GATE & PLAN — gate per exact canonical SMILES, never per class.
  CANONICAL_SMILES = canon_smiles.py "<smiles>".
  IS_NOVEL = `guides/system_characterization_cache.json` has no key CANONICAL_SMILES (file/key
    absent ⇒ true). Independent of VALIDATED below — a SMILES can be characterized (Phase-A timing
    knobs measured) without being validated for the requested properties, and vice versa.
  VALIDATED = system_characterization_cache.json[CANONICAL_SMILES].protocol_validated==true AND
    validated_properties ⊇ properties_requested.

  VALIDATED → known SMILES, reproduce as before:
    `make_deterministic_plan.py --run_name <RUN> --polymer_class <CLASS> --smiles "<smiles>"
    --properties <props>` then, if IS_NOVEL=false,
    `apply_cached_characterization.py --run_plan PLAN_PATH --canonical_smiles CANONICAL_SMILES`.
    No agent spawn, critic auto-approved. Phase A/B: read orchestration/tracks/DETERMINISTIC_REPLICATE.md
    instead of FOUNDATION/THERMAL_TRACK/MECHANICAL_TRACK.md.

  NOT VALIDATED → first full run for this SMILES (or for its newly-requested properties):
    ⚪ literature-grounding-worker → literature_grounding.json
    🟡 planner (+ grounding_path) → run_plan.json
    🔴 critic loop, max 2 rounds → approved proceeds, revise returns to planner, escalate writes
      UNRESOLVED and stops
    If IS_NOVEL=false (characterized by an earlier run, but not validated for these properties):
      `apply_cached_characterization.py --run_plan PLAN_PATH --canonical_smiles CANONICAL_SMILES`
      reuses that run's measured timing knobs instead of guessed class defaults, before Phase A.
    Recover failures per `.claude/commands/recover.md`'s plan_mode ladder, up to 5 attempts or
    until every requested property completes.

  Write CANONICAL_SMILES/IS_NOVEL/VALIDATED + PLAN_PATH/plan_mode to the run_log.md header.

THREAD THE PLAN
  Every gen_prompt.py call passes --plan PLAN_PATH, never read polymer_rules.json manually:
  `gen_prompt.py --stage <STAGE> --run_name <RUN> --polymer_class <CLASS> --plan PLAN_PATH`.
  T_workflow_K = decided_params.T_workflow_K; if tg isn't requested, glassy_hint = T_workflow_K != 300.

HARDWARE — claim before any GPU-submitting worker spawn (build is not a GPU stage; equilibration,
  Tg sweep, Murnaghan, and deform all are).
  GPU_PER_RUN = decided_params.gpu_per_run (default 1). Claim: `pick_gpu.py --json claim --run
  <RUN> --need ${GPU_PER_RUN:-1}` → success `{"claimed":[ids],...}` used verbatim as gpu_ids;
  shortfall (exit 1) → defer/retry, never force. Release on completion: `pick_gpu.py release --run
  <RUN>`. When the plan pins a D-08 override (gpu_per_run/engine/mpi_ranks in decided_params), let
  gen_prompt.py thread it — do NOT also pass --gpu_ids/--mpi_ranks (CLI wins and would shadow the
  plan). Deterministic-path carve-out: DETERMINISTIC_REPLICATE.md's scripted executor claims and
  releases internally — do not also claim at the orchestrator level for that path.

BACKGROUND-WAIT — canonical wait pattern, referenced by name from every phase guide and /recover.
  After a worker returns monitor_command: log SIMULATION STATE, then
  `Bash(command=monitor_command, run_in_background=true)` and END YOUR TURN. On the exit wakeup:
    RUN_COMPLETE → get_run_status → proceed
    PROCESS_DEAD_NO_SENTINEL → /recover
    killed / no terminal line → relaunch the same waiter

PHASE A — FOUNDATION: orchestration/tracks/FOUNDATION.md.
PHASE B — TRACKS: thermal (if tg) → orchestration/tracks/THERMAL_TRACK.md; mechanical (if bulk_modulus)
  → orchestration/tracks/MECHANICAL_TRACK.md.
PHASE C — SUMMARY: orchestration/tracks/SUMMARY.md.
```
