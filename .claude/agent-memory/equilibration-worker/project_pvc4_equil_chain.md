---
name: pvc4-equil-chain
description: PVNL/PCFF PVC 9-stage glassy equil chain at 530 K, kokkos, GPU 2, chain_id=0e4c8878 [ingested 2026-06-24]
metadata:
  type: project
  ingested_at: 2026-06-25
---

PVNL/PCFF (PVC4) glassy equilibration chain submitted 2026-06-24.

- n_atoms: 3620
- temp: 530 K (T_workflow_K), max_temp: 610 K
- press: 1.0 atm
- engine: kokkos, gpu_ids: 2, mpi: 1
- chain_id: 0e4c8878
- n_stages: 9 (minimize → nvt_softheat → npt_compress → npt_pppm → npt_cool → nvt_production → npt_production → npt_cool300 → npt_prod300)
- params_file: data/PVC4/lammps/equil/emc_build.params (required for EMC PCFF Coeffs)
- velocity_seed: random (read back from nvt_softheat.log SEED_HOT before logging)
- npt_prod300 is the density/deformation source (stage 09, 300 K production)
- add_melt_npt: false, add_300k_production: true

**Why:** PVC Tg ~354 K → glassy at MD timescales; must equilibrate at 530 K (above MD Tg); 9-stage chain cools to 300 K for density extraction.
**How to apply:** Use data/PVC4/lammps/equil/npt_prod300/npt_prod300_out.data for equil-check and downstream deformation. See [[pvc-pcff-tg-degenerate-underpredict]] for known PVNL slope-gate issues (use rates 25/50/100 K/ns, 8 ns/7 cyc).

## Extension run (attempt 1) — 2026-06-24
- Trigger: npt_prod300 had 5.55% energy drift (> 1% threshold); density 1.350 g/cm3 converged.
- chain_id: ac74390d
- extend_from_data: data/PVC4/lammps/equil/npt_prod300/npt_prod300_out.data
- extend_out_data: data/PVC4/lammps/equil/npt_extend/npt_extend_out.data
- extend_steps: 2,000,000 (2 ns at dt=1 fs), temp=300 K, press=1 atm, engine=kokkos, gpu_ids=2, mpi=1
- n_stages: 1 (npt_extend only — extend_only=True verified before submit)
