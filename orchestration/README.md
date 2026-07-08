# orchestration/ — CLI & Orchestration Helpers + Orchestrator-Read Docs

Flat by design: these paths are hard-wired into `CLAUDE.md`, the agent definitions in
`.claude/agents/`, and the guides — do not move or rename without a repo-wide reference sweep.

## Orchestrator-read docs

The orchestrator `Read`s these on phase entry (they are NOT inlined into worker prompts — worker
guides live in `guides/`).

| Doc | Read at | Owns |
|---|---|---|
| `FOUNDATION.md` | Phase A | build → equilibration (BACKGROUND-WAIT) → equil-check gate + EXTEND branch |
| `THERMAL_TRACK.md` | Phase B (tg) | multirate Tg sweep, slope gate + per-class fallback, is_glassy |
| `MECHANICAL_TRACK.md` | Phase B (bulk_modulus) | Murnaghan primary + deform fallback + BM extraction routing |
| `SUMMARY.md` | Phase C | exp-lookup → tg_path (`select_tg_path.py`) → run-summary → memory capture |
| `decision_policy.json` | planner/critic (at plan/critique time) | evaluation framework the planner/critic reason against |

## Pipeline core

| Script | Purpose | Primary consumers |
|---|---|---|
| `gen_prompt.py` | Builds every worker prompt: inlines the stage guide from `guides/`, threads the approved `run_plan.json` decided_params, and emits the final prompt text. The hub of the orchestrator→worker contract. | Orchestrator (`CLAUDE.md`), all worker stages |
| `make_deterministic_plan.py` | Emits a byte-identical `run_plan.json` for confidence=high polymer classes (the planner shells out to it; low/medium classes get a reasoned plan instead). Reads `guides/polymer_rules.json`. | `planner` agent, tests |
| `select_tg_path.py` | Phase C helper: picks which per-rate `tg_summary` feeds run-summary (slowest rate if the multirate slope gate passed, else the plan's `tg_slope_gate_fallback` rate, default highest). | Orchestrator (`CLAUDE.md` Phase C) |

## Hardware runtime (shared lib: `hw_common.py`)

| Script | Purpose | Primary consumers |
|---|---|---|
| `hw_common.py` | Shared access to `hardware_policy` / `polymer_rules.json` engine defaults. | `pick_gpu.py`, `gen_prompt.py`, `make_deterministic_plan.py`, the `hardware/` calibration toolchain |
| `pick_gpu.py` | GPU claim/release ledger (`claim --run <LABEL> --need N` / `release`). One GPU-run per GPU across concurrent orchestrator sessions. | Orchestrator, all GPU stages |

The calibration toolchain (`calibrate_hardware.py`, `benchmark_hardware.py`,
`bench_accuracy_diff.py`) lives with the policy docs and calibration cells in `hardware/`.

## Analysis / one-offs

| Script | Purpose | Primary consumers |
|---|---|---|
| `estimate_tg_group_contribution.py` | Motif-based group-contribution Tg estimate used as planning evidence for off-table polymers. | `planner` agent |

The benchmark data-release rebuilder lives with the manuscript material: `manuscript/collect_data.sh`.
