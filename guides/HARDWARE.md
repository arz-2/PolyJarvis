# Hardware Lookup — mpi/gpu per run

Rationale, numbers, caveats: [HARDWARE_STUDY.md](HARDWARE_STUDY.md).
Box: 4× Quadro RTX 6000 (ids 0–3) + i9-10980XE (18 physical cores).

## Limits
- Σ mpi over concurrent runs ≤ 18.
- ≤ 1 GPU-heavy run per GPU.
- PPPM (PCFF/OPLS): mpi ≥ 4, never mpi=1.
- <10k-atom cell: 1 GPU, never >1.

## Standard MD (equil, tg sweep, production)

| FF family | Classes | engine | gpu_ids | gpus | mpi | mpi solo |
|-----------|---------|--------|---------|------|-----|----------|
| PCFF | PACR PEST PVNL PSFO PKTN PCBN PAMD PIMD POXI PSUL PURT PANH PPHS PIMN PPNL | gpu | one id | 1 | 4 | 8 |
| OPLS-AA | PHAL PSIL | gpu | one id | 1 | 4 | 8 |
| TraPPE-UA | PHYC PDIE | cpu | "" | 0 | 4 | 8 |
| GAFF2 | PURA / off-table | gpu | one id | 1 | 4 | 8 |

## Special templates (mechanical track)

| Template | engine | gpus | mpi | mpi solo |
|----------|--------|------|-----|----------|
| nvt_born | cpu | 0 | 4 | 8 |
| npt_deform | gpu | 1 | 4 | 8 |
| npt_tg_step | gpu | 1 | 4 | 8 |

## Commands
- Budget check: `python3 scripts/pick_gpu.py budget --mpi <N>`
- Claim/release GPU: `python3 scripts/pick_gpu.py claim --run <RUN>` / `release --run <RUN>`
- Benchmark a cell: `python3 scripts/benchmark_hardware.py --data <cell>.data --ff <pcff|opls|trappe> [--pppm] --label <NAME>`

Defaults auto-derived by `gen_prompt.py` from `polymer_rules.json:hardware_policy` when `--mpi_ranks`/`--gpu_ids` omitted. `mpi` = concurrent-safe; `mpi solo` = box dedicated to one run (provisional, not yet benchmarked).
