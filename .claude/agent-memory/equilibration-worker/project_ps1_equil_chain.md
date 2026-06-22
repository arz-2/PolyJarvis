---
name: project-ps1-equil-chain
description: PS1 atactic Polystyrene equilibration: 9-stage glassy chain, PCFF, temp=550 K; prior chain 76ded65d failed (mpirun not found), retry chain_id=6f8a5143
metadata:
  type: project
  ingested_at: 2026-06-22
---

PS1 atactic Polystyrene (PSTR class) equilibration submitted 2026-06-20.

**Chain:** 9-stage glassy path (temp=550 K > 300 K, add_300k_production=True). Stage 09 npt_prod300 at 300 K is the density/deformation source.

**Key params:** use_pcff=True, max_temp=630 K, n_atoms=6420, gpu_ids=1, mpi=4, SEED_HOT=179213 (nvt_softheat velocity init only; no SEED_COLD — subsequent stages read from data/restart files). params_file required for EMC PCFF Coeffs.

**Prior chain:** 76ded65d — FAILED due to mpirun not on PATH; params unchanged.
**Active chain_id:** 6f8a5143 (retry, mpirun shim fixed at orchestrator level)
**work_dir:** /home/arz2/PolyJarvis/data/PS1/lammps/equil/

**Why:** PSTR uses PCFF (Class II); glassy polymer (exp Tg ~370 K); 9-stage chain mandatory so stage 09 (npt_prod300) produces 300 K density and serves as deformation source. temp=550 K chosen as T_workflow_K above MD Tg.

**How to apply:** If re-running PS1 or similar PSTR chains, use temp=550 K (not 300 K), use_pcff=True, add_300k_production=True. EMC-generated .data files for PSTR have no Coeffs sections — always pass params_file.

**Recovery note:** mpirun-not-found error does NOT require changing simulation params — fix is a PATH shim at the OS level. The generate_equilibration_workflow call produces a new SEED_HOT each time; log the new seed from the regenerated nvt_softheat.in rather than reusing the prior seed.

See also: [[project-psu1-equil-chain]] for another PCFF 9-stage glassy chain example.
