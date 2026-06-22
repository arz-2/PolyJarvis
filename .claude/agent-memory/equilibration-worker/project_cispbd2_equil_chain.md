---
name: cispbd2-equil-chain
description: cis-PBD2 PDIE/TraPPE-UA 7-stage rubbery equilibration chain, temp=300 K, max_temp=480 K, n_atoms=8040, chain_id=49d5c679
metadata:
  type: project
  ingested_at: "2026-06-22"
---

cis-PBD2 (second replicate cis-1,4-PBD, `*C/C=C\C*`, PDIE, TraPPE-UA) 7-stage rubbery equilibration chain submitted 2026-06-22.

- chain_id: 49d5c679
- n_atoms: 8040
- temp: 300 K, max_temp: 480 K, press: 1 atm, max_press: 50000 atm
- npt_prod_steps: 1500000
- SEED_HOT: 355754 (nvt_softheat velocity create 300 K)
- SEED_COLD: N/A (nvt_production inherits velocities from npt_cool, no reinit)
- gpu_ids: "0", mpi: 1, engine: gpu
- work_dir: /home/arz2/PolyJarvis/data/cis-PBD-2/lammps/equil
- npt_production_dir: /home/arz2/PolyJarvis/data/cis-PBD-2/lammps/equil/npt_production
- npt_production_log: /home/arz2/PolyJarvis/data/cis-PBD-2/lammps/equil/npt_production/npt_production.log

**Why:** Standard rubbery path (exp Tg 181 K < 300 K); 7-stage chain ending at npt_production at 300 K.
**How to apply:** Use npt_production_out.data and npt_production.log as primary density/bulk-modulus source for this run.

**Key detail:** params_file must be passed to both inspect_data_file AND generate_equilibration_workflow for EMC TraPPE-UA cells. Worker guide says to omit it but the tools require it to suppress "Coeffs section missing" blocking errors. [[pe2-equil-chain]] confirms same pattern for PHYC.

Related: [[cispbd1-equil-chain]]
