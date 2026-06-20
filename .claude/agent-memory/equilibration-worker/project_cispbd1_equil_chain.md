---
name: cispbd1-equil-chain
description: cis-PBD1 PDIE/TraPPE-UA 7-stage rubbery equilibration chain, temp=300 K, max_temp=480 K, n_atoms=8040, chain_id=c2e7c43e
metadata:
  type: project
---

cis-PBD1 (standard cis-1,4-PBD, `*C/C=C\C*`, PDIE, TraPPE-UA) 7-stage rubbery equilibration chain submitted 2026-06-18.

- chain_id: c2e7c43e
- n_atoms: 8040
- temp: 300 K, max_temp: 480 K, press: 1 atm, max_press: 50000 atm
- npt_prod_steps: 1500000
- SEED_HOT: 853457 (nvt_softheat velocity create 300 K)
- SEED_COLD: N/A (nvt_production inherits velocities from npt_cool, no reinit)
- gpu_ids: "2", mpi: 1
- work_dir: /home/alexzhao/PolyJarvis/data/cis-PBD1/lammps/equil
- npt_production_dir: /home/alexzhao/PolyJarvis/data/cis-PBD1/lammps/equil/npt_production
- npt_production_log: /home/alexzhao/PolyJarvis/data/cis-PBD1/lammps/equil/npt_production/npt_production.log

**Why:** Standard rubbery path (exp Tg 181 K < 300 K); 7-stage chain ending at npt_production at 300 K.
**How to apply:** Use npt_production_out.data and npt_production.log as primary density/bulk-modulus source for this run.

Note: SMILES was corrected from erroneous C6 diene `*CC/C=C\CC*` to standard cis-1,4-PBD `*C/C=C\C*` before this run (R-01).
