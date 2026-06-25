---
name: project-ps4-equil-chain
description: PSTR/PCFF 9-stage glassy chain for PS4, temp=550 K, max_temp=630 K, n_atoms=6420, chain_id=ac214038; engine=kokkos, gpu_ids=1, mpi=1; velocity_seed=647974
metadata:
  type: project
  ingested_at: 2026-06-25
---

PS4 Atactic Polystyrene equilibration chain submitted 2026-06-24.

- polymer_class: PSTR
- force_field: PCFF (EMC, params_file required)
- n_atoms: 6420
- n_stages: 9 (glassy: add_300k_production=True)
- chain_id: ac214038
- engine: kokkos
- gpu_ids: 1
- mpi: 1
- temp: 550.0 K (T_workflow_K)
- max_temp: 630.0 K (T_anneal_high_K)
- press: 1.0 atm
- velocity_seed: 647974
- data_file: data/PS4/lammps/equil/cell.data
- params_file: data/PS4/lammps/equil/emc_build.params
- stages_dir: data/PS4/lammps/equil/
- npt_prod300_data: data/PS4/lammps/equil/npt_prod300/npt_prod300_out.data
- npt_prod300_log: data/PS4/lammps/equil/npt_prod300/npt_prod300.log

**Why:** Fresh replicate of PS (PS2/PS3 precedent) with new velocity seed to improve slope-gate pass rate (PS memory indicates seed/build-dependent slope-gate behavior).
**How to apply:** npt_prod300_out.data is the 300 K production cell for density, deformation, and Murnaghan; equil-checker feeds from this path.

[[ps-pcff-tg-slopegate-fail]]
