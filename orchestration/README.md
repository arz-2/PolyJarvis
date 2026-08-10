# orchestration/ — CLI & Orchestration Helpers + Orchestrator-Read Docs

Two subdirectories: `tracks/` — orchestrator-read phase/track guides, `Read` directly on phase
entry — and `scripts/` — every CLI helper, all siblings in one directory because five of them
bare-import each other (`hw_common.py`, `select_hardware.py`) via a same-directory `sys.path`
insert; splitting them across further subdirectories would break those imports. `decision_policy.json`
and this file stay at the `orchestration/` top level.

These paths are hard-wired into `CLAUDE.md`, the agent definitions in `.claude/agents/`, and the
guides — do not move or rename without a repo-wide reference sweep.

## tracks/ — orchestrator-read docs

The orchestrator `Read`s these on phase entry (they are NOT inlined into worker prompts — worker
guides live in `guides/`).

| Doc | Read at | Owns |
|---|---|---|
| `FOUNDATION.md` | Phase A | build → equilibration (BACKGROUND-WAIT) → equil-check gate (non-PASS → RECOVERY) |
| `THERMAL_TRACK.md` | Phase B (tg) | single-rate Tg sweep + analysis, per-class rate fallback, is_glassy |
| `MECHANICAL_TRACK.md` | Phase B (bulk_modulus) | Murnaghan primary + deform fallback + BM extraction routing |
| `SUMMARY.md` | Phase C | exp-lookup → tg_path (`select_tg_path.py`) → run-summary → memory capture |
| `DETERMINISTIC_REPLICATE.md` | Phase A/B, `plan_mode=="deterministic"` | scripted replay path — read instead of the other four |

## scripts/ — pipeline core

| Script | Purpose | Primary consumers |
|---|---|---|
| `gen_prompt.py` | Builds every worker prompt: inlines the stage guide from `guides/`, threads the approved `run_plan.json` decided_params, and emits the final prompt text. The hub of the orchestrator→worker contract. | Orchestrator (`CLAUDE.md`), all worker stages |
| `make_deterministic_plan.py` | Emits a byte-identical `run_plan.json`, used as-is when this exact canonical SMILES is already `protocol_validated` in `guides/system_characterization_cache.json` (the planner shells out to it), or as the starting-hypothesis scaffold every reasoned plan for a novel SMILES revises. Reads `guides/polymer_rules.json`. | `planner` agent, tests |
| `select_hardware.py` | Mechanically implements `decision_policy.json:policies.hardware`'s D-08 require/prefer clauses (FF-alias resolution, RDKit cell-atom estimate, benchmark-window comparison) so the numbers live in one place. | `planner` agent (reasoned path), `validate_run_plan.py` |
| `validate_run_plan.py` | Mechanical structural checks for a `run_plan.json` against `decision_policy.json` (criteria coverage, evidence presence, stage schema, hardware arithmetic) — the parts of the Critic's review that don't need judgment. | `planner` (self-check), `critic` agent |
| `select_tg_path.py` | Phase C helper: picks which per-rate `tg_summary` feeds run-summary (slowest rate if the multirate slope gate passed, else the plan's `tg_slope_gate_fallback` rate, default highest). | Orchestrator (`CLAUDE.md` Phase C) |
| `canon_smiles.py` | Canonicalizes a SMILES string — the gate key for `system_characterization_cache.json` and `polymer_rules.json` validation lookups. | Orchestrator (GATE & PLAN), `planner`, `critic`, `protocol-locker` |
| `apply_cached_characterization.py` | Reuses an earlier run's measured timing knobs (`derived_*` fields) for a SMILES that's characterized but not yet validated for the requested properties, instead of guessed class defaults. | Orchestrator (GATE & PLAN, `IS_NOVEL=false` branch) |
| `enforce_gate.py` | Mechanized PASS/EXTEND/STRUCTURAL_FAIL/FAIL verdict enforcement for the equil-check gate, against `decision_policy.json`'s binding/advisory clauses. `--live` mode is called directly by the `enforce_equilibration_gate` MCP tool at tool-call time — a live production dependency, not just a CLI. | `equilibration-checker` (via the MCP tool), retrospective audits |
| `run_deterministic_replicate.py` | Scripted end-to-end executor for the `deterministic` path — replaces the agent-spawn chain with direct MCP calls for replicate-2+ runs of an already-validated SMILES. | Orchestrator (`DETERMINISTIC_REPLICATE.md`) |
| `aggregate_replicates.py` | Mean±SD rollup across a class's named replicate run set. | Orchestrator (Phase C campaign hooks) |

## scripts/ — hardware runtime (shared lib: `hw_common.py`)

| Script | Purpose | Primary consumers |
|---|---|---|
| `hw_common.py` | Shared access to `hardware_policy` / `polymer_rules.json` engine defaults. | `pick_gpu.py`, `gen_prompt.py`, `make_deterministic_plan.py`, `select_hardware.py`, `run_deterministic_replicate.py`, the `hardware/` calibration toolchain |
| `pick_gpu.py` | GPU claim/release ledger (`claim --run <LABEL> --need N` / `release`). One GPU-run per GPU across concurrent orchestrator sessions. | Orchestrator, all GPU stages |

The calibration toolchain (`calibrate_hardware.py`, `benchmark_hardware.py`,
`bench_accuracy_diff.py`) lives with the policy docs and calibration cells in `hardware/` — both
import `hw_common.py` from `orchestration/scripts/` via an explicit `sys.path` insert.

## scripts/ — analysis / one-offs

| Script | Purpose | Primary consumers |
|---|---|---|
| `estimate_tg_group_contribution.py` | Motif-based group-contribution Tg estimate used as planning evidence for off-table polymers. | `planner` agent |

The benchmark data-release rebuilder lives with the manuscript material: `manuscript/collect_data.sh`.

## Top level

| File | Purpose |
|---|---|
| `decision_policy.json` | Evaluation framework the planner/critic reason against; also read directly by `enforce_gate.py` and `validate_run_plan.py` (both anchor its path at `orchestration/`, not `orchestration/scripts/` — why it stays here rather than moving with the scripts). |
| `README.md` | This file. |
