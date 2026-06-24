---
name: project-pvc3-equil-chain
description: PVC3 PVNL/PCFF 9-stage glassy chain, temp=530 K, max_temp=610 K, n_atoms=3620, chain_id=dfa923bf; revision of PVC2 with longer melt equilibration (t_equil=8 ns, anneal_cycles=7) to fix degenerate Tg
metadata:
  type: project
---

PVC3 (PVNL/PCFF) 9-stage glassy equilibration chain submitted 2026-06-23.

- chain_id: dfa923bf
- n_atoms: 3620 (atom types: c, c1, cl, hc; H type_id=4)
- temp: 530.0 K, max_temp: 610.0 K, press: 1.0 atm
- engine: kokkos, gpu_ids: 3, mpi: 1
- params_file required (EMC PCFF Coeffs in emc_build.params)
- velocity_seed: null (random; read SEED_HOT back from nvt_softheat.log)
- stages: minimize, nvt_softheat, npt_compress, npt_pppm, npt_cool, nvt_production, npt_production, npt_cool300, npt_prod300
- npt_prod300 is density/deformation source (stage 09, 300 K)
- equil dir: /home/alexzhao/PolyJarvis/data/PVC3/lammps/equil/
- revision motivation: PVC2 had degenerate Tg fits at DP60; PVC3 uses longer melt equil (8 ns, 7 annealing cycles)

**Why:** Glassy polymer (exp_Tg ~355 K); temp>300 forces 9-stage path with 300 K cool-down. PVC2 had degenerate Tg fits so PVC3 extends melt equilibration time per [[project-pvc2-equil-chain]].
**How to apply:** For any PVNL/PCFF run, params_file is required and kokkos engine confirmed working on GPU 3. If Tg fits degenerate again, increase anneal_cycles beyond 7 or try longer t_equil.
