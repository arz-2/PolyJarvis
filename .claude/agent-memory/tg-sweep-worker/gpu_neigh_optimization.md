---
name: tg_sweep_gpu_neigh_optimization
description: GPU neighbor list optimization for small PCFF Tg-sweep cells — ~+30% speedup
metadata:
  type: feedback
  ingested_at: 2026-06-22
---

After generate_script writes tg_sweep.in, the default `package gpu 1 neigh no` line must be manually edited to `package gpu 1 neigh yes` for small PCFF cells (<5k atoms).

**Why:** Neighbor lists built on GPU GPU add ~30% speedup for small systems and are identical in physics (NPT-stable after expand/contract probe).

**How to apply:** In tg-sweep-worker:
1. Generate script with generate_script(template="npt_tg_step", ...).
2. Use Edit tool to replace `package gpu 1 neigh no` → `package gpu 1 neigh yes` in the generated .in file.
3. Verify the edit and script structure (20-point staircase loop, single velocity init) before run_lammps_script submission.
4. Always use mpi≥4 for PCFF (mpi=1 starves PPPM/bonded on CPU, ~75× slower).

Related: [[mpi1_pcff_gpu_starvation]]
