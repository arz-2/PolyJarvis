# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

@AGENTS.md

## Architecture

PolyJarvis is a deterministic polymer-simulation platform: scientific intent -> planning agent -> validated `run_plan.json` -> deterministic stage scripts (build, equilibration, thermal, mechanical, summary) -> recovery agent, invoked only on structured issues and capped at two calls. Code — not agent prompts — owns simulation files, parameter resolution, job submission, validation, recovery limits, and provenance. `orchestration/README.md` lists what each script in `orchestration/scripts/` owns. Entry points: `orchestration/scripts/agent_api.py` (contract), `orchestration/scripts/scientific_control.py` (plan -> execute -> conditional recovery), `orchestration/scripts/run_campaign.py` (resumable single-stage or full execution).

This is a from-scratch rewrite (branch `refactor/deterministic-control-plane`). The prior multi-agent worker-prompt implementation and the manuscript archive exist only in Git history on `main` and in the sibling worktree — do not assume `.claude/agents/`, stage-worker markdown files, or agent-owned run state from that era apply here.

## Running without a session

`orchestration/langgraph/run_graph.py` runs a whole campaign headlessly — no live Claude Code
session, no approval gate:

```bash
mcp-servers/.venv/bin/python orchestration/langgraph/run_graph.py \
    --run-name PS1 --smiles '*CC(*)c1ccccc1' --properties density,tg \
    --goal 'density and Tg for polystyrene' --max-gpu-hours 40 --deadline-hours 24
```

It classifies (`classify_cli.py`), plans (`make_deterministic_plan.py run-plan`), critiques and
adjudicates via two headless `claude -p` calls that reuse `.claude/agents/literature-grounding-worker.md`
and `SKILL.md` step 5 verbatim, materializes, and executes through `agent_api.py` with the
usual inner recovery. Add `--no-llm` for the deterministic arm, `--dry-run` to stop before
execution, `--resume` to pick up (also automatic). Exit codes are in
`orchestration/langgraph/state.py`; `escalation_required` (2) and `failed` (3) are terminal
and need a human, `deadline_exceeded` (4) is resumable.

Three things worth knowing before changing it: the graph is a DAG and must stay one (both
recovery-agent calls are already spent when `escalation_required` comes back, so re-entering
only re-burns GPU time); every path into execution — resume and cache-hit included — must pass
the cost guard, and `cost_estimate.total_gpu_hours` is a documented *lower* bound; and a cache
hit skips `materialize` for correctness, not speed, because `materialize_plan` would re-solve
the cell and overwrite the frozen protocol it just replayed.

`polymer_class` is a **backbone taxonomy**, and that is a real limitation, not a quibble:
`polyinfo_classifier` matches on the extracted mainchain, so PMMA reports `PEST: false` —
its ester is pendant. 404 of PI1070's 1077 repeat units carry a polar group that never
informed their class label, yet the class supplies `electrostatics`, `charge_method`,
`cutoff_A`, `dt_fs` and the experimental bands. So `classify` also returns a `chemistry`
block from `guides/functional_groups.json` (40 real functional groups, matched on the 2-mer,
each tagged backbone or pendant, plus composition and descriptors), and
`chemistry_policy.consistency()` checks it against the class constants.

Those findings are **advisory** — written to `data/<run>/raw/classification.json`, streamed
as graph events, and put in front of the adjudicating critic, which is the only thing that
may act on them and only through `overrides`. They never rewrite a class constant: the class
table is curated against real validation runs, this is a rule over SMARTS.

Two measurements make it worth trusting. Implied vs class-declared electrostatics agrees
**43/43** across every curated `member_smiles`, so the proxy is exact and a break is signal.
And on the 735 PI1070 units carrying no N-carbonyl group (baseline EMC failure 14.6%),
aliphatic **`alkene` fails 59.6% of trial builds — 4.1× baseline**, a risk factor absent from
`guides/ff_moiety_rules.json`'s three rules; it is recorded as an advisory recommending
`--with-ff-probe` rather than promoted to a blocking rule, because that file demands
per-field `tried`/`failed` measurement and this is correlation on one population.

`polymer_class` itself comes from RadonPy's `poly.polyinfo_classifier` through `classify_cli.py`,
which is *called*, never reimplemented. It disagrees with `guides/polymer_rules.json`'s own
curated `member_smiles` on exactly three molecules (PVC, PVME, PPO/PPE); those are recorded in
`guides/class_overrides.json` with a reason each, and `tests/test_class_agreement.py` fails if
that set changes. Against PoLyInfo's curated labels across all 1077 rows of RadonPy's PI1070 it
agrees 91.1% — a characterization, not a bar, since PoLyInfo answers "what is this called" and
this repo answers "which protocol does it get".

## Setup gotchas

- `.mcp.json` is gitignored; copy `.mcp.json.example` and fill in host paths (`LAMBDA_*`, `CONDA_ENV`, `EMC_ROOT`, `RADONPY_PATH`, etc.).
- `mcp-radonpy-server` is referenced in `.mcp.json.example` but has no directory under `mcp-servers/` in this checkout — only `mcp-lammps-engine`, `mcp-emc-server`, and `mcp-mol-builder-server` exist here.
- `db/experimental_db.sqlite` (real lab measurements: DSC, dilatometry, mechanical testing — renamed from `polymer_db.sqlite`) is gitignored (curated from copyrighted sources) and does not exist until built/copied locally — `db/query_best_match.py` lookups need it first.
- `db/polydatabase_md.sqlite` (LLM-mined MD-simulation-literature records from polydatabase.com / its public Zenodo dataset, CC BY 4.0) is a separate gitignored local index, built via `db/ingest_scripts/import_polydatabase.py`. The `literature-grounding-worker` agent (the MD-protocol critic) queries it via `db/query_polydatabase.py` as its primary source before falling back to WebSearch; it never bypasses DOI verification and silently degrades to WebSearch-only if not yet built. Note the index applies no `system_type`/`material_morphology` filter and returns DOIs in URL form — callers must handle both.
- Resumable run state lives in `data/<run>/workflow_state.json` (per-stage status/attempts) and each attempt's own `data/<run>/attempts/<stage>/<attempt_id>/executor_state.json` (the plan-level `decided_params` in force for that attempt, plus its computed outputs — NOT the resolver's per-stage arguments, which are computed transiently and never persisted); completed stages are skipped on resume. `data/<run>/raw/control_state.json` is NOT run state: it is a thin session record (who is on this run, and is it over), written by both the control plane and the resume path.
- GPU claims go through `orchestration/scripts/hardware_runtime.py` (atomic claim/release ledger) — don't assume a GPU is free without checking it.

Subdirectory `CLAUDE.md` files can be added for module-specific instructions (e.g. `orchestration/`, `mcp-servers/<server>/`) — they load automatically when Claude works in those directories. Ask if you want one.
