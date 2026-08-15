---
name: project_pla1_equil_chain
description: PLA1 (PEST/PCFF) glassy melt-phase equilibration chain, nchain=10, temp=620K
metadata:
  type: project
---

PLA1 — PEST class (PLA), EMC/PCFF build, glassy (T_workflow=620K > 300K, max_temp=700K),
n_atoms=4520, nchain=10. inspect_data_file with target_density_gcm3=1.248 gave SIZE_PASS
(L_over_2Rg=1.224, L_over_2cutoff=1.912) — no rebuild needed. add_melt_npt=false (melt-mixing
gate uses the standard glassy 9-stage split, not add_melt_npt).

Submitted melt-phase prefix only (phase=melt): 7 stages
[minimize, nvt_softheat, npt_compress, npt_pppm, npt_cool, nvt_production, npt_production],
chain_id=ec91e13e. Cooldown tail [npt_cool300, npt_prod300] saved to
/home/arz2/PolyJarvis/data/PLA1/lammps/equil/_pending_cooldown_stages.json for the
`phase=cooldown` resubmit after the melt-mixing gate passes.

engine=kokkos, gpu_ids=2, mpi=1, velocity_seed=353960. params_file
(emc_build.params) copied alongside cell.data into equil/ dir — required to suppress
Coeffs-missing errors on EMC PCFF builds, see [[feedback_cis_lock_nocoeff_ff_detect]].
