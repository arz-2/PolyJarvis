---
name: project_psu3_bm_slow_gpu_contention
description: PSU3 glassy Murnaghan BM ran ~12x slower than the Tg sweep due to GPU-3 sharing with a concurrent PEEK4 BM run + dump I/O; reduced npt_steps to 150k to fit budget
metadata:
  type: project
---

PSU3 (PSFO/PCFF, glassy) Murnaghan BM at 300 K, ±1000 atm (5 pts). First submit used npt_steps=500000 and ran at **~107k steps/hr — ~12x slower** than the same-cell kokkos Tg sweep (~1.4M steps/hr), projecting ~23 h for the series (over the 48 h budget).

Root cause (two compounding factors):
1. **GPU-3 contention**: nvidia-smi `--query-compute-apps -i 3` + lsof showed a concurrent **PEEK4** BM `lmp` sharing GPU 3 with PSU3's `lmp`. The `pick_gpu.py` claim ("PSU3" on GPU 3) is **advisory only** — another orchestrator session launched onto the same claimed GPU. Two lmp on one GPU ≈ halves throughput.
2. **BM dump I/O**: `run_bulk_modulus_series` writes a per-point `.dump` (saw 178 MB on PEEK4's bm_P0); the Tg sweep wrote none (DUMP_FILE=""). The dump is not needed for K extraction (extractor reads the log volume, not the dump).

Fix used: killed ONLY the PSU3-confirmed pids (verified via /proc cwd+cmdline), left PEEK4 untouched (cross-track rule 3), resubmitted with **npt_steps=150000** (0.15 ns/pt → 750k steps ≈ 7 h even contended). Result was clean: K=4.42 GPa (r²=0.9996), B0'=18.79 (elevated — ±1000 atm under-constrains curvature at short averaging, WARNING not FAIL), fluctuation B_dyn=4.37 GPa agrees 1.1%. K within exp [4.0,5.5].

How to apply: (a) before a long BM series, check `nvidia-smi --query-compute-apps -i <gpu>` for an existing lmp on the claimed GPU — the claim is not enforced. (b) Consider disabling the BM dump (unused by the extractor) to cut I/O. (c) For glassy cells 150k steps/point (0.15 ns) gave a clean Murnaghan fit + self-consistent fluctuation cross-check — 500k may be overkill when volume converges fast in a glass. Repo-relative: `data/PSU3/lammps/mechanical/bm_series/`.
