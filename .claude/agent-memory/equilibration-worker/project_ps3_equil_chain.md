---
name: project-ps3-equil-chain
description: PS3 atactic Polystyrene equilibration: 9-stage glassy chain, PCFF, temp=550 K, chain_id=c2a94ebb; engine=kokkos, gpu_ids=1, mpi=1
metadata:
  type: project
  ingested_at: 2026-06-23
---

PS3 atactic Polystyrene (PSTR class) equilibration submitted 2026-06-23.

**Chain:** 9-stage glassy path (temp=550 K > 300 K, add_300k_production=True). Stage 09 npt_prod300 at 300 K is the density/deformation source.

**Key params:** use_pcff=True, max_temp=630 K, n_atoms=6420, gpu_ids=1, mpi=1, engine=kokkos, velocity_seed=null (random; read back from nvt_softheat.log). params_file required for EMC PCFF Coeffs.

**chain_id:** c2a94ebb
**work_dir:** /home/arz2/PolyJarvis/data/PS3/lammps/equil/

**Why:** PSTR uses PCFF (Class II); glassy polymer (exp Tg ~370 K); 9-stage chain mandatory so stage 09 (npt_prod300) produces 300 K density and serves as deformation source. temp=550 K chosen as T_workflow_K above MD Tg.

**How to apply:** If re-running PS3 or similar PSTR chains, use temp=550 K (not 300 K), use_pcff=True, add_300k_production=True, engine=kokkos (not gpu). EMC-generated .data files for PSTR have no Coeffs sections — always pass params_file.

See also: [[project-ps2-equil-chain]] for PS2 PSTR chain (same params, chain_id=5249cae6). [[project-ps1-equil-chain]] for PS1 (mpi=4, engine=gpu).
