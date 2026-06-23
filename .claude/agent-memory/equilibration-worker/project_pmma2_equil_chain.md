---
name: project_pmma2_equil_chain
description: PMMA2 equilibration chain submission — glassy PACR, PCFF, kokkos engine, GPU 1, 9-stage chain
metadata:
  type: project
---

PMMA2 equilibration chain submitted 2026-06-22. 9-stage glassy path (temp=550 K > 300 K → npt_cool300 + npt_prod300 auto-appended). chain_id: ced82a82. GPU 1, mpi=1, engine=kokkos. 7520 atoms, max_temp=630 K.

**Why:** PACR/PMMA is glassy (exp_Tg ~388 K); T_equil_K=550 K (well above MD Tg); must equilibrate above Tg then cool to 300 K for density/BM source.

**How to apply:** npt_prod300_out.data is the density and Murnaghan deformation source. equil-check should use npt_prod300.log. Stages dir: /home/arz2/PolyJarvis/data/PMMA2/lammps/equil/.
