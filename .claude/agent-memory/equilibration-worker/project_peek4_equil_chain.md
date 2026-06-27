---
name: peek4-equil-chain
description: PEEK/PKTN PCFF 9-stage glassy chain, temp=770 K, max_temp=850 K, n_atoms=8720, chain_id=7a6f0aa0; engine=kokkos, gpu_ids=1, mpi=1; params_file required [2026-06-25]
metadata:
  type: project
---

PEEK4 (PKTN class, PCFF) — 9-stage glassy equilibration chain submitted 2026-06-25.

**Why:** PEEK has exp_Tg ~416–420 K; T_workflow_K=770 K (well above Tg), max_temp=850 K, 8 annealing cycles. Glassy path → chain auto-appends npt_cool300 + npt_prod300; stage 09 is density/deformation source.

**How to apply:** Use chain_id=7a6f0aa0 for get_run_status / watch_run. npt_prod_data_path = `data/PEEK4/lammps/equil/npt_prod300/npt_prod300_out.data`.

- chain_id: 7a6f0aa0
- n_stages: 9
- gpu_ids: "1"
- mpi: 1
- engine: kokkos
- n_atoms: 8720
- temp: 770.0 K
- max_temp: 850.0 K
- press: 1.0 atm
- params_file: data/PEEK4/lammps/equil/emc_build.params (required for EMC PCFF Coeffs)
- velocity_seed: random (read back from nvt_softheat.log)
- npt_prod_log: data/PEEK4/lammps/equil/npt_prod300/npt_prod300.log
- npt_prod_data: data/PEEK4/lammps/equil/npt_prod300/npt_prod300_out.data
- expected_equil_data: data/PEEK4/lammps/equil/nvt_production/nvt_production_out.data
