---
name: project-pvc2-equil-chain
description: PVC2 PVNL/PCFF 9-stage glassy chain, temp=530 K, max_temp=610 K, n_atoms=3620, chain_id=b98f0f31
metadata:
  type: project
---

PVC2 (PVNL/PCFF) 9-stage glassy equilibration chain submitted 2026-06-22.

- chain_id: b98f0f31
- n_atoms: 3620 (atom types: c, c1, cl, hc; H type_id=4)
- temp: 530.0 K, max_temp: 610.0 K, press: 1.0 atm
- engine: kokkos, gpu_ids: 2, mpi: 1
- params_file required (EMC PCFF Coeffs in emc_build.params)
- velocity_seed: null (random; read SEED_HOT back from nvt_softheat.log)
- stages: minimize, nvt_softheat, npt_compress, npt_pppm, npt_cool, nvt_production, npt_production, npt_cool300, npt_prod300
- npt_prod300 is density/deformation source (stage 09, 300 K)
- equil dir: /home/alexzhao/PolyJarvis/data/PVC2/lammps/equil/

**Why:** Glassy polymer (exp_Tg ~355 K); temp>300 forces 9-stage path with 300 K cool-down.
**How to apply:** For any PVNL/PCFF run, params_file is required and kokkos engine is confirmed working on GPU 2.
