---
name: pe2-equil-chain
description: PE2 PHYC/TraPPE-UA 7-stage rubbery equilibration chain, chain_id=b0ad167b, n_atoms=4840, GPU1, velocity_seed=1005
metadata:
  type: project
  ingested_at: "2026-06-22"
---

PE2 (Polyethylene, PHYC/TraPPE-UA) 7-stage rubbery chain: chain_id=b0ad167b, n_atoms=4840, temp=300 K, max_temp=620 K, npt_prod_steps=5M, engine=gpu, gpu_ids=1, mpi=1, velocity_seed=1005 (SEED_HOT).

**Key detail:** EMC TraPPE-UA cell ships coefficients in a separate `.params` file (`emc_build.params`) — must pass `params_file=` to both `inspect_data_file` and `generate_equilibration_workflow` to suppress "Coeffs section missing" blocking errors.

**Why:** `inspect_data_file` returned validation.valid=False with 4 Coeffs-missing errors on first call; adding params_file suppressed them and returned valid=True.

**How to apply:** All PHYC/PDIE/TraPPE-UA EMC cells require params_file threading through inspect + workflow + chain calls. Check `data/<run>/lammps/cell/` for `emc_build.params` before calling inspect.

Related: [[cispbd1-equil-chain]] (same params_file pattern confirmed for PDIE)
