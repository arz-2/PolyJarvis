---
name: project_pegore1_equil_chain
description: PEGORE1 (PEO force-field comparison, EMC field pcff_ore) 9-stage rubbery add_melt_npt chain, temp=300K, max_temp=580K, t_equil_K=500K, n_atoms=7020, chain_id=766a58e6
metadata:
  type: project
---

PEGORE1 is a force-field-comparison run for the POXI (PEO) class, built by EMC with field
`pcff_ore/pcff_ore` (a pcff variant with a larger parameter file), NOT plain `pcff`. Despite
`use_pcff=true` in lammps_flags, the actual field name is `pcff_ore` — do not silently
"correct" this to plain pcff or re-derive the field from polymer_rules; it's intentional for
the comparison study.

data/PEGORE1/lammps/cell/emc_build.data (n_atoms=7020) has no Coeffs sections (EMC convention);
coefficients live in data/PEGORE1/lammps/cell/emc_build.params, copied to
equil/emc_build.params and passed as `params_file` to both inspect_data_file and
generate_equilibration_workflow/run_lammps_chain.

Chain: rubbery (T_workflow_K=300 ≤ 300), add_melt_npt=true (explicit in prompt, t_equil_K=500),
9-stage: minimize, nvt_softheat, npt_compress, npt_pppm, npt_cool_melt, npt_melt (Tg-sweep
starting cell, npt_tg_prep_data), npt_cool, nvt_production, npt_production (density/BM source).
engine=kokkos, gpu_ids=2, mpi=1, velocity_seed=20260812 (pinned, explicit in prompt).
chain_id=766a58e6.

Note: the deployed `inspect_data_file` tool in this session did NOT accept `target_density_gcm3`
or `nchain` kwargs (schema lacks them) despite the EQUILIBRATION.md guide instructing to pass
them for the finite-size forecast gate — passing them anyway did not error but also had no
visible effect on the returned validation dict. Proceeded on `validation.errors == []` alone.
See [[project_finite_size_gate_and_verdicts]] (root memory) for the gate's intended design.
