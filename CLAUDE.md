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

## Running a campaign

To run a simulation campaign for a SMILES, invoke the `run-campaign` skill
(`.claude/commands/run-campaign.md`) — it reads `orchestration/ORCHESTRATOR.md`, which owns the
worker roster and the full SETUP/GATE & PLAN/THREAD/HARDWARE/BACKGROUND-WAIT/RECOVERY workflow.
This file covers repo layout and development conventions only.
