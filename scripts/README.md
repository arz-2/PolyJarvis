# scripts/ — CLI & Orchestration Helpers

Flat by design: these paths are hard-wired into `CLAUDE.md`, the agent definitions in
`.claude/agents/`, and the guides — do not move or rename without a repo-wide reference sweep.

## Pipeline core

| Script | Purpose | Primary consumers |
|---|---|---|
| `gen_prompt.py` | Builds every worker prompt: inlines the stage guide from `guides/`, threads the approved `run_plan.json` decided_params, and emits the final prompt text. The hub of the orchestrator→worker contract. | Orchestrator (`CLAUDE.md`), all worker stages |
| `make_deterministic_plan.py` | Emits a byte-identical `run_plan.json` for confidence=high polymer classes (the planner shells out to it; low/medium classes get a reasoned plan instead). | `planner` agent, `decision_policy.json`, tests |
| `select_tg_path.py` | Phase C helper: picks which per-rate `tg_summary` feeds run-summary (slowest rate if the multirate slope gate passed, highest if it failed). | Orchestrator (`CLAUDE.md` Phase C) |
| `integrate.py` | Two-machine revision integrator: lands findings/fixes from both workstations into `main` (see `guides/MULTI_MACHINE_WORKFLOW.md`). | Orchestrator, multi-machine protocol |

## Hardware cluster (shared lib: `hw_common.py`)

| Script | Purpose | Primary consumers |
|---|---|---|
| `hw_common.py` | Shared access to `hardware_policy` / `polymer_rules.json` engine defaults. | The four scripts below + `gen_prompt.py` |
| `pick_gpu.py` | GPU claim/release ledger (`claim --run <LABEL> --need N` / `release`). One GPU-run per GPU across concurrent orchestrator sessions. | Orchestrator, all GPU stages |
| `calibrate_hardware.py` | One-command host-match of per-FF engine defaults (`/calibrate-hardware` skill). | New-machine setup, `README.md` |
| `benchmark_hardware.py` | MPI/GPU throughput benchmark backing calibration decisions. | `calibrate_hardware.py`, `guides/HARDWARE*.md` |
| `bench_accuracy_diff.py` | Physics-parity check between engine arms (e.g. KOKKOS vs GPU package) before flipping a default. | `calibrate_hardware.py` |

## Analysis / one-offs

| Script | Purpose | Primary consumers |
|---|---|---|
| `estimate_tg_group_contribution.py` | Motif-based group-contribution Tg estimate used as planning evidence for off-table polymers. | `planner` agent |
| `collect_reviewer_data.sh` | Regenerates the curated reviewer-data subset under `data/` (git-adds the provenance files listed in `data/REVIEWER_DATA_README.md`). Paper-revision tooling, not part of the simulation pipeline. | Manual (revision workflow) |
