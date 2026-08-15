---
name: project_psu1_equil_chain
description: PSU1 PSFO/PCFF glassy melt-phase chain, rebuild nchain=32 accepted after nchain=20 SIZE_CHAIN_SELF_IMAGE failure
metadata:
  type: project
---

PSU1 (PSFO, PCFF) rebuilt at nchain=32 (43,264 atoms, L=98.25 A) after nchain=20 pack failed the
pre-submit finite-size gate at L/2Rg=0.946 (see [[project_psu1_size_gate_fail]]). Rebuild
inspect_data_file forecast: L_predicted_A=77.98, packed_Rg_A=34.7, L_over_2Rg=1.124,
L_over_2cutoff=4.104 — passes both the tool's own SIZE_PASS verdict and the run's stricter
custom acceptance bar of L/2Rg >= 1.08. Submitted as phase=melt (glassy, T_workflow=700K,
max_temp=780K): 7-stage melt prefix (minimize..npt_production) chain_id=5fd36896, cooldown tail
(npt_cool300+npt_prod300) saved to
/home/arz2/PolyJarvis/data/PSU1/lammps/equil/_pending_cooldown_stages.json. engine=kokkos,
gpu_ids=0, mpi=1, velocity_seed=37413. params_file (emc_build.params) required for EMC PCFF
Coeffs.

**Why:** custom acceptance bars stricter than the tool's SIZE_PASS threshold can be specified by
the orchestrator per-run (here 1.08 vs tool's ~1.0) when a prior rebuild already undershot once —
always check the prompt for an explicit bar before trusting SIZE_PASS alone.

**How to apply:** when a prompt states a custom L/2Rg acceptance bar, compare
finite_size_forecast.L_over_2Rg against that bar, not just validation.errors/verdict.
