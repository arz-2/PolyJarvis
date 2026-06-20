# Hardware Benchmark Study — mpi/gpu for PolyJarvis MD

Companion/rationale for the lookup table in [HARDWARE.md](HARDWARE.md). This is the *why*;
HARDWARE.md is the *what*.

## Goal & context
The revision screening runs were slow and wasting GPU. Investigation (2026-06-19) found the
mpi/gpu rules existed in agent memory but were never enforced at launch, so bad configs (e.g.
`mpi=1` on PCFF ≈ 2.4 ns/day; UA on GPU `mpi=1`) launched and got fixed reactively via
`/recover`. The fix: make config plan-driven per FF (`polymer_rules.json:hardware_policy` →
`gen_prompt.py`), plus a benchmark harness (`scripts/benchmark_hardware.py`) and an allocation
helper (`scripts/pick_gpu.py`).

## Hardware
- 4× NVIDIA A800 40GB (ids 0–3)
- 1× AMD Ryzen Threadripper PRO 5975WX — 32 physical cores / 64 threads
- LAMMPS `/home/alexzhao/lammps-install/bin/lmp` (GPU sm_80 + EXTRA-COMPUTE built)

Each MPI rank ≈ 1 CPU core (GPU runs included — the rank still drives kspace/bonded/neighbor
on the CPU). **Ranks, not GPUs, are the scarce resource.** Throughput governor for concurrent
runs: **Σ mpi ≤ 32 physical cores**, ≤ 1 GPU-heavy run per GPU.

> ⚠ **Benchmark provenance:** every `ns/day` number in the Results/Conclusions below was
> measured on the **prior box (4× RTX 6000 24GB / i9-10980XE 18-core)**, NOT these A800s.
> They are retained for rationale only. The hardware descriptors and the Σmpi budget above
> have been updated to the A800/32-core box, but the per-config timings and the per-run
> `mpi`/`gpu` defaults they justify are **pending an A800 re-run** of
> `scripts/benchmark_hardware.py` (`hardware_policy.values_are_benchmarked` is still `false`).

## Method
`scripts/benchmark_hardware.py` runs a short (~2.5–3k step) LAMMPS run per config and parses
`ns/day` + the MPI-task timing breakdown (Pair/Kspace/Neigh/Comm). GPU is driven purely from
the command line (`-sf gpu -pk gpu N neigh no`) so the multi-GPU count `N` is honored (an
in-file `package gpu 1` would silently override it). It is polite by default (idle GPU + spare
cores only); the runs below used `--allow-busy` on a near-idle GPU.

### ⚠ Contention caveat (read before trusting absolutes)
All runs below were taken with **~29 background ranks already on 18 cores**, which starves the
CPU configs. So **CPU-vs-GPU absolute comparisons are confounded** — the CPU side is penalized.
What IS robust: GPU rank-scaling curves, and GPU-vs-GPU comparisons (mpi=1 penalty, multi-GPU),
because those configs are equally contended. Absolute ns/day are depressed vs a drained box.

## Results

### PCFF — class2 + pppm (PSU1 cell, 8656 atoms)
| config | GPUs | ns/day |
|--------|------|--------|
| gpu1_mpi4 | 1 | 4.96 |
| gpu4_mpi4 | 4 | 4.48 |
| gpu2_mpi2 | 2 | 2.20 |
| gpu1_mpi2 | 1 | 2.17 |
| gpu1_mpi1 | 1 | 1.13 |
| cpu_mpi4 | 0 | 2.99 |

- **Never `mpi=1`:** 1.13 vs 4.96 at mpi=4 — ~4.4× penalty (kspace is CPU-serial per rank).
- **Near-linear rank scaling on 1 GPU** (1.13→2.17→4.96) ⇒ CPU-bound on Bond/Kspace/Neigh ⇒ `mpi=8` solo gains further.
- **Multi-GPU does NOT help:** gpu1_mpi4 (1 GPU) **>** gpu4_mpi4 (4 GPUs); gpu1_mpi2 ≈ gpu2_mpi2. Extra GPUs add comm overhead, no benefit < 10k atoms ⇒ **gpu_per_run=1**. Live PSU1 on mpi=4/4-GPU was wasting 3 GPUs.
- GPU vs CPU at mpi=4: 4.96 vs 2.99 (Pair offloads 44%→7%) — directional only (CPU contended).
- Reproducible: gpu1_mpi4 = 4.96 here vs 4.95 on a different GPU.

### TraPPE-UA — lj/cut, no kspace (PE1 cell, 4840 atoms)
| config | ns/day |
|--------|--------|
| gpu1_mpi4 | 80.0 |
| gpu1_mpi2 | 40.7 |
| gpu1_mpi1 | 25.6 |
| cpu_mpi8 | 22.7 |
| cpu_mpi4 | 21.6 |

- GPU scales near-linearly (25.6→40.7→80.0). Reliable.
- CPU `mpi8` ≈ `mpi4` (22.7 ≈ 21.6) — **cores starved**, not real CPU scaling.
- **The apparent "GPU ≫ CPU for UA" is a CPU-saturation artifact** and does NOT overturn the
  isolation finding that UA is faster on CPU `mpi=8`. UA engine kept **CPU** pending a drained-box
  CPU run (where `cpu_mpi8` should ~2×). Operational note: when the box is CPU-saturated, GPU
  offload can still be the better practical choice even for UA.

### Special templates
- **born (`nvt_born`, `compute born/matrix numdiff`) — CPU-ONLY.** Loads
  `lj/class2/coul/long/gpu` but **crashes at the first matrix eval** under `-sf gpu`. CPU `mpi4`
  ran (1.57 ns/day, Modify ~60% = numdiff cost). Existing `use_gpu=False` default is correct.
- **deform (`npt_deform`, `fix deform`/SLLOD) — GPU FUNCTIONAL.** Ran under `-sf gpu` (54.4 vs
  14.1 cpu, contended). Contradicts the old "GPU+SLLOD untested" default comment.
- **tg_step (`npt_tg_step`)** — cost structure = PCFF NPT+pppm; the PCFF result applies.

## Conclusions (→ encoded in HARDWARE.md + hardware_policy)
- PCFF/OPLS std MD: **GPU, 1 GPU, mpi=4 concurrent / 8 solo; never mpi=1; never >1 GPU.**
- TraPPE-UA std MD: **CPU, mpi=4 concurrent / 8 solo** (isolation optimum; revisit only if running CPU-saturated).
- born: **CPU-only.** deform: **GPU ok.** tg_step: **as PCFF.**
- `mpi` defaults are **concurrent-safe** (4 runs × mpi=4 = 16 ≤ 32 cores), not single-run-optimal.

## Still pending (drained-box sweep)
Contention-free CPU-vs-GPU verdict for UA and PCFF (CPU `mpi=8/16` need free cores), clean
absolute numbers, and whether to flip `TEMPLATE_DEFAULTS` `use_gpu` for deform/tg_step. Run one
`benchmark_hardware.py` per cost class (no `--allow-busy`) once the screening runs finish, then
set `hardware_policy.values_are_benchmarked: true` and update the numbers.

Raw per-config JSON: `/tmp/polyjarvis/bench/*.json` (transient). Live measured ratios mirrored
in `polymer_rules.json:hardware_policy.directional_probe`.
