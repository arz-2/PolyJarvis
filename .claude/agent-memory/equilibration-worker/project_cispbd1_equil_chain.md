---
name: cispbd1-equil-chain
description: cis-PBD1 (PDIE, TraPPE-UA) rubbery 9-stage add_melt_npt equilibration chain parameters and submission details
metadata:
  type: project
---

cis-PBD1 equilibration submitted 2026-08-11 from a cis-microstructure-locked cell
(`data/cis-PBD1/lammps/cis_lock/cis_locked.data`, 100% cis C=C torsions — NOT the raw
47.9/52.1 EMC build). See [[feedback_cis_lock_nocoeff_ff_detect]] for the header-patch fix
required before `generate_equilibration_workflow` would accept `use_trappe=True` on this file.

Params: polymer_class=PDIE, temp=300 K (rubbery, ≤300), max_temp=480 K, t_equil_K=400 K
(add_melt_npt=True → 9-stage chain with npt_cool_melt/npt_melt/npt_cool split), press=1 atm,
max_press=50000 atm, n_atoms=8040, npt_prod_steps=1500000, melt_npt_steps=500000, use_trappe=True,
params_file=data/cis-PBD1/cell/emc_build.params (EMC nocoeff build, required).

engine=gpu, gpu_ids=2, mpi=1, chain_id=d699cddf.

npt_tg_prep_data (Tg-sweep starting cell, NOT npt_production_out.data) =
`data/cis-PBD1/lammps/equil/npt_melt/npt_melt_out.data`.
