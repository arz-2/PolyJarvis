# Hardware Lookup — mpi/gpu per run

Rationale, numbers, caveats: [HARDWARE_STUDY.md](HARDWARE_STUDY.md).
Box: 4× NVIDIA A800 40GB (ids 0–3) + AMD Ryzen Threadripper PRO 5975WX (32 physical cores / 64 threads).
> ⚠ The per-run `mpi`/`gpu` values in the tables below were measured on the prior box (4× RTX 6000 24GB / 18-core i9-10980XE) and are carried over **unverified** on this A800 box. Only the Σmpi budget was updated for 32 cores. Re-run `scripts/benchmark_hardware.py` per cost class on the A800s to retune.

## Limits
- Σ mpi over concurrent runs ≤ 32.
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
- Budget check: `python3 scripts/pick_gpu.py budget --mpi <N>` (exit 0 fits / 1 oversubscribed)
- Claim/release GPU: `python3 scripts/pick_gpu.py claim --run <RUN>` / `release --run <RUN>`
- Benchmark a cell: `python3 scripts/benchmark_hardware.py --data <cell>.data --ff <pcff|opls|trappe> [--pppm] --label <NAME>`

Prepend `--json` to any `pick_gpu.py` subcommand for one structured JSON object on stdout
(`status`/`claim`/`budget`/`release`) instead of human text — prefer it when parsing the result
programmatically (e.g. the orchestrator reads `claim`'s `{"claimed":[ids]}`). Defaults are
unchanged: `claim` still prints bare comma-joined ids, `budget` keeps its 0/1 exit code.

Defaults auto-derived by `gen_prompt.py` from `polymer_rules.json:hardware_policy` when `--mpi_ranks`/`--gpu_ids` omitted. `mpi` = concurrent-safe; `mpi solo` = box dedicated to one run (provisional, not yet benchmarked).
