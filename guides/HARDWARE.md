# Hardware Lookup — mpi/gpu per run

Rationale, numbers, caveats: [HARDWARE_STUDY.md](HARDWARE_STUDY.md).
Box: 4× Quadro RTX 6000 (ids 0–3) + i9-10980XE (18 physical cores).

## Limits
- Σ mpi over concurrent runs ≤ 18.
- ≤ 1 GPU-heavy run per GPU.
- PPPM (GPU-package fallback / GAFF2): mpi ≥ 4, never mpi=1. KOKKOS PCFF/OPLS run mpi=1 (kspace on GPU, not CPU-serial).
- <10k-atom cell: 1 GPU, never >1.

## Standard MD (equil, tg sweep, production)

| FF family | Classes | engine | gpu_ids | gpus | mpi | mpi solo |
|-----------|---------|--------|---------|------|-----|----------|
| PCFF | PACR PEST PVNL PSFO PKTN PCBN PAMD PIMD POXI PSUL PURT PANH PPHS PIMN PPNL | **kokkos** | one id | 1 | **1** | 1 |
| OPLS-AA | PHAL PSIL | **kokkos** | one id | 1 | **1** | 1 |
| TraPPE-UA | PHYC PDIE | gpu (neigh yes) | one id | 1 | 1 | 1 |
| GAFF2 | PURA / off-table | gpu | one id | 1 | 4 | 8 |

## Special templates (mechanical track)

| Template | engine | gpus | mpi | mpi solo |
|----------|--------|------|-----|----------|
| nvt_born | cpu | 0 | 4 | 8 |
| npt_deform | gpu | 1 | 4 | 8 |
| npt_tg_step | gpu | 1 | 4 | 8 |

## Commands
- Atom-count estimate (D-08 sizing): the bare `python3` lacks rdkit — call a conda-env python by absolute path, e.g. `"$(conda env list | awk '/mol-builder/{print $NF}')"/bin/python -c "from rdkit import Chem; ..."` (mol-builder or radonpy env). Derive the env path from `conda env list`; never hard-code `/home/<user>/...`.
- Budget check: `python3 scripts/pick_gpu.py budget --mpi <N>` (exit 0 fits / 1 oversubscribed)
- Claim/release GPU: `python3 scripts/pick_gpu.py claim --run <RUN>` / `release --run <RUN>`
- Benchmark a cell: `python3 scripts/benchmark_hardware.py --data <cell>.data --ff <pcff|opls|trappe> [--pppm] --label <NAME>`

Prepend `--json` to any `pick_gpu.py` subcommand for one structured JSON object on stdout
(`status`/`claim`/`budget`/`release`) instead of human text — prefer it when parsing the result
programmatically (e.g. the orchestrator reads `claim`'s `{"claimed":[ids]}`). Defaults are
unchanged: `claim` still prints bare comma-joined ids, `budget` keeps its 0/1 exit code.

Defaults auto-derived by `gen_prompt.py` from `polymer_rules.json:hardware_policy` when `--mpi_ranks`/`--gpu_ids` omitted. `mpi` = concurrent-safe; `mpi solo` = box dedicated to one run (provisional, not yet benchmarked).
