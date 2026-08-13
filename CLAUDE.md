# PolyJarvis

AI agent for autonomous polymer MD simulation. Given a SMILES string, runs the full pipeline — molecular construction (RadonPy/EMC MCP servers) → equilibration → track sweeps → property extraction.

## Key Directories

| Path | Contents |
|------|----------|
| `orchestration/` | `decision_policy.json`; `tracks/` — orchestrator-read phase docs (`FOUNDATION.md`, `THERMAL_TRACK.md`, `MECHANICAL_TRACK.md`, `SUMMARY.md`, `DETERMINISTIC_REPLICATE.md`); `scripts/` — CLI helpers (`gen_prompt.py`, `select_tg_path.py`, `pick_gpu.py`, `canon_smiles.py`, `make_deterministic_plan.py`, `apply_cached_characterization.py`) |
| `guides/` | Worker guides inlined into worker prompts by `gen_prompt.py`; `polymer_rules.json`; `system_characterization_cache.json` |
| `data/TEMPLATE/run_log.md` | Run log template — copied to `data/[RUN]/run_log.md` at task start |
| `data/[RUN]/` | All run files: `run_log.md`, `lammps/`, `raw/`, `graphs/` |

**Paths:** all run files live under `data/<run_name>/` (repo-relative, git-excluded)

## Running a campaign

To run a simulation campaign for a SMILES, invoke the `run-campaign` skill
(`.claude/commands/run-campaign.md`)

## Conventions

Applies to all code, architecture, and doc changes/additions:

- Minimal additions — don't add a file, section, or comment unless it's load-bearing.
- Worker-facing docs (agent `.md`, `guides/*.md`) state rules and steps only, not the design
  reasoning behind them.
- Keep comments and doc notes to a minimum — state the current rule, not a running commentary.
- No timestamps, changelog phrasing, or references to prior/dead code — describe only the current
  state.
- State hard rules and instructions only — don't explain rationale or walk through alternatives;
  let agents infer at runtime.

This file covers repo layout and development conventions only.
