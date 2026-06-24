---
name: pvc3_r100_submission
description: PVC3 (PVNL/PCFF) Tg sweep r100 (100 K/ns), glassy path, per-T dump enabled, velocity seed 730559 captured
metadata:
  type: project
---

PVC3 r100 (fastest rate, rate index 2) submitted cleanly 2026-06-24.

**Parameters:**
- T: 550 → 150 K, step 20 K (21 stages)
- Starting cell: npt_prod300_out.data (300 K, glassy regime)
- Engine: KOKKOS (per-plan D-08 hardware override)
- Per-T dump: enabled (PER_T_DUMP_FILE=per_t_structs.dump)
- Velocity seed: 730559 (random draw from template, captured for reproducibility — cross-track rule 2)

**Run ID:** 65168f97
**Working dir:** /home/arz2/PolyJarvis/data/PVC3/lammps/thermal/tg_sweep_r100
**Log path:** /home/arz2/PolyJarvis/data/PVC3/lammps/thermal/tg_sweep_r100/tg_sweep.log

**FF verified:** pair_style lj/class2/coul/long + dihedral_style class2 + kspace_style pppm (correct PCFF Class II for KOKKOS engine).

**No issues — clean submission. Same workflow as r25, r50 prior to this run.**
