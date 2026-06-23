---
name: project_pla2_equil_chain
description: PLA2 equilibration chain submission — glassy PEST, PCFF, kokkos engine, GPU 3, 9-stage chain
metadata:
  type: project
---

PLA2 equilibration chain submitted 2026-06-22. 9-stage glassy path (temp=620 K > 300 K → npt_cool300 + npt_prod300 auto-appended). chain_id: e220ec0e. GPU 3, mpi=1, engine=kokkos.

**Why:** PEST/PLA is glassy (exp_Tg ~330 K); T_equil_K=620 K (well above MD Tg); must equilibrate above Tg then cool to 300 K for density/BM source.

**How to apply:** npt_prod300_out.data is the density and Murnaghan deformation source. equil-check should use npt_prod300.log. Stages dir: /home/arz2/PolyJarvis/data/PLA2/lammps/equil/.
