---
name: project_peg4_equil_chain
description: PEG4 POXI/PCFF 9-stage rubbery chain with add_melt_npt=True (npt_cool_melt + npt_melt + npt_cool), temp=300 K, max_temp=580 K, n_atoms=7020, chain_id=9199fe26; engine=kokkos, gpu_ids=0, mpi=1, velocity_seed=409966
metadata:
  type: project
  ingested_at: 2026-06-25
---

PEG4 equilibration chain submitted 2026-06-24.

- chain_id: 9199fe26
- polymer: PEG (POXI/PCFF)
- n_atoms: 7020
- n_stages: 9 (add_melt_npt=True path: npt_cool_melt → npt_melt → npt_cool → nvt_production → npt_production)
- temp: 300 K (rubbery)
- max_temp: 580 K (T_anneal_high_K)
- t_equil_K: 500 K (melt isothermal)
- engine: kokkos
- gpu_ids: "0"
- mpi: 1
- velocity_seed: 409966
- params_file: data/PEG4/lammps/equil/emc_build.params (required for EMC PCFF Coeffs)
- npt_tg_prep_data: data/PEG4/lammps/equil/npt_melt/npt_melt_out.data (Tg sweep start cell at 500 K)
- npt_prod_data: data/PEG4/lammps/equil/npt_production/npt_production_out.data (300 K density/BM source)

**Why:** add_melt_npt=True inserts a 1 ns isothermal hold at 500 K between annealing and final cool-down, giving better chain relaxation for the Tg sweep start cell.

**How to apply:** npt_tg_prep_data (npt_melt_out.data at 500 K) feeds the Tg sweep worker; npt_production_out.data (300 K) feeds equil-check and Murnaghan worker.
