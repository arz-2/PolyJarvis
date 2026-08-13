---
name: project_pegcmp1_equil_chain
description: PEGCMP1 POXI/COMPASS(use_pcff=true) 9-stage rubbery add_melt_npt chain, temp=300 K, max_temp=580 K, n_atoms=7020, chain_id=b9b7bf5d; engine=kokkos, gpu_ids=0, mpi=1, velocity_seed=20260812
metadata:
  type: project
  ingested_at: 2026-08-12
---

PEGCMP1 equilibration chain submitted 2026-08-12 — reviewer force-field-comparison arm.

- chain_id: b9b7bf5d
- polymer: PEG (POXI), field under test = **compass** (EMC Class II) — `use_pcff=True` selects
  the correct class2 style block for COMPASS; do not confuse with the PEG1-4 PCFF baseline
- baseline for comparison: PEG1-4 (PCFF), archived — see [[project_peg4_equil_chain]]
- n_atoms: 7020 (parity with PEG1)
- n_stages: 9 (add_melt_npt=True path)
- temp: 300 K (rubbery, decided_params.T_workflow_K) — run_log's own "T_workflow_K: 500" line was
  a hand-transcription slip, actually T_equil_K
- max_temp: 580 K, t_equil_K: 500 K, melt_npt_steps: 1000000 (1 ns @ dt=1.0 fs)
- lj_cutoff: 9.5 Å (decided_params.cutoff_A, not the 12.0 Å default)
- engine: kokkos, gpu_ids: "0", mpi: 1, velocity_seed: 20260812
- params_file: EMC `.data` has zero inline Coeffs sections (COMPASS/EMC convention same as PCFF);
  copied `emc_build.params` from `lammps/cell/` into `lammps/equil/` and passed to
  `inspect_data_file`, `generate_equilibration_workflow`, and `run_lammps_chain` — omitting it on
  any one call fires spurious "Coeffs missing" blocking errors
- verified emitted .in: `pair_style lj/class2/coul/long 9.5 9.5`, `bond_style class2`, and
  `include` line is an absolute path resolving correctly from every stage's own work_dir

**Why:** reviewer para 7 asks whether PEG's PCFF thermomechanical error (−5.43% density, +50% K)
is FF-specific; COMPASS is the alternative Class II field EMC supports, protocol held identical.

**How to apply:** downstream density/K comparison should cite this chain's npt_production (300 K)
against [[project_peg4_equil_chain]]'s npt_production, not against PEG1-3.
