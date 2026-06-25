---
name: pmma3-equil-chain
description: PMMA3/PACR PCFF 9-stage glassy chain, temp=550 K, max_temp=630 K, n_atoms=7520, chain_id=bd435bce (re-submit, EMC seed 555781); engine=kokkos, gpu_ids=3, mpi=1; params_file required; velocity_seed=random (read back from log)
metadata:
  type: project
  ingested_at: 2026-06-25
---

PMMA3 equilibration chain re-submitted 2026-06-24 (rebuilt cell after PPPM overlap failure with seed 555780).

- polymer: PMMA (PACR class)
- FF: PCFF (use_pcff=true)
- engine: kokkos, gpu_ids=3, mpi=1
- n_atoms: 7520
- temp: 550.0 K (glassy, T_workflow>300 → 9-stage chain)
- max_temp: 630.0 K
- press: 1.0 atm / max_press: 50000.0 atm
- chain_id: bd435bce (previous failed chain: 4b5494b0, nvt_softheat PPPM range error, EMC seed 555780)
- n_stages: 9 (includes npt_cool300 + npt_prod300)
- params_file: data/PMMA3/lammps/equil/emc_build.params (required for EMC PCFF Coeffs)
- velocity_seed: random (read back from nvt_softheat.log)
- npt_prod300_data: data/PMMA3/lammps/equil/npt_prod300/npt_prod300_out.data
- npt_prod300_log: data/PMMA3/lammps/equil/npt_prod300/npt_prod300.log

**Why:** Glassy PACR polymer at 550 K equilibration temperature; 9-run chain auto-appends 300 K production stages for density/BM extraction. Prior chain failed at nvt_softheat with "Out of range atoms - cannot compute PPPM" due to localized pack overlap in EMC cell; fix was rebuilding with a new EMC seed (555781).
**How to apply:** Use npt_prod300_out.data for equil-check and Murnaghan BM series.
