# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

@AGENTS.md

## Architecture

PolyJarvis is a deterministic polymer-simulation platform: scientific intent -> planning agent -> validated `run_plan.json` -> deterministic stage scripts (build, equilibration, thermal, mechanical, summary) -> recovery agent, invoked only on structured issues and capped at two calls. Code — not agent prompts — owns simulation files, parameter resolution, job submission, validation, recovery limits, and provenance. `orchestration/README.md` lists what each script in `orchestration/scripts/` owns; `docs/AGENT_CONTRACT.md` has the full JSON schemas. Entry points: `orchestration/scripts/agent_api.py` (contract), `orchestration/scripts/scientific_control.py` (plan -> execute -> conditional recovery), `orchestration/scripts/run_campaign.py` (resumable single-stage or full execution).

This is a from-scratch rewrite (branch `refactor/deterministic-control-plane`). The prior multi-agent worker-prompt implementation and the manuscript archive exist only in Git history on `main` and in the sibling worktree — do not assume `.claude/agents/`, stage-worker markdown files, or agent-owned run state from that era apply here.

## Setup gotchas

- `.mcp.json` is gitignored; copy `.mcp.json.example` and fill in host paths (`LAMBDA_*`, `CONDA_ENV`, `EMC_ROOT`, `RADONPY_PATH`, etc.).
- `mcp-radonpy-server` is referenced in `.mcp.json.example` but has no directory under `mcp-servers/` in this checkout — only `mcp-lammps-engine`, `mcp-emc-server`, and `mcp-mol-builder-server` exist here.
- `db/experimental_db.sqlite` (real lab measurements: DSC, dilatometry, mechanical testing — renamed from `polymer_db.sqlite`) is gitignored (curated from copyrighted sources) and does not exist until built/copied locally — `db/query_best_match.py` lookups need it first.
- `db/polydatabase_md.sqlite` (LLM-mined MD-simulation-literature records from polydatabase.com / its public Zenodo dataset, CC BY 4.0) is a separate gitignored local index, built via `db/ingest_scripts/import_polydatabase.py`. The `literature-grounding-worker` agent (the MD-protocol critic) queries it via `db/query_polydatabase.py` as its primary source before falling back to WebSearch; it never bypasses DOI verification and silently degrades to WebSearch-only if not yet built. Note the index applies no `system_type`/`material_morphology` filter and returns DOIs in URL form — callers must handle both.
- Resumable run state lives in `data/<run>/raw/control_state.json` (control layer), `data/<run>/workflow_state.json` (per-stage status/attempts), and each attempt's own `data/<run>/attempts/<stage>/<attempt_id>/executor_state.json` (that attempt's resolved parameters + computed outputs); completed stages are skipped on resume.
- GPU claims go through `orchestration/scripts/hardware_runtime.py` (atomic claim/release ledger) — don't assume a GPU is free without checking it.

Subdirectory `CLAUDE.md` files can be added for module-specific instructions (e.g. `orchestration/`, `mcp-servers/<server>/`) — they load automatically when Claude works in those directories. Ask if you want one.
