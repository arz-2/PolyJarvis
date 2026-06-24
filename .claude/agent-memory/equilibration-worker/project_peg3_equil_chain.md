---
name: peg3-equil-chain
description: PEG3 Polyethylene glycol (POXI/PCFF) 7-stage rubbery equil chain, temp=300 K, max_temp=580 K, n_atoms=7020, chain_id=6807e1cc (engine=kokkos, mpi=1, velocity_seed=182001)
metadata:
  type: project
  ingested_at: 2026-06-23
---

PEG3 (PEO/PEG, POXI class, PCFF force field) 7-stage rubbery equilibration chain submitted 2026-06-23.

- chain_id: 6807e1cc (current; prior chain 0bb5f028 used engine=gpu, mpi=2 — superseded)
- n_atoms: 7020 (matched expected)
- n_stages: 7 (Path B rubbery — temp=300 K, no 300K prod appendix)
- temp: 300.0 K, max_temp: 580.0 K
- npt_prod_steps: 2,000,000
- gpu_ids: "0", mpi: 1
- engine: kokkos
- velocity_seed: 182001 (pinned SEED_HOT for reproducibility)
- params_file: /home/arz2/PolyJarvis/data/PEG3/lammps/cell/emc_build.params

Key paths:
- data_file: /home/arz2/PolyJarvis/data/PEG3/lammps/cell/cell.data
- npt_production_log: /home/arz2/PolyJarvis/data/PEG3/lammps/equil/npt_production/npt_production.log
- npt_production_out: /home/arz2/PolyJarvis/data/PEG3/lammps/equil/npt_production/npt_production_out.data
- expected_equil_data: /home/arz2/PolyJarvis/data/PEG3/lammps/equil/nvt_production/nvt_production_out.data

**Why:** POXI/PCFF EMC build — Coeffs live in params file, not .data; passed params_file to both inspect_data_file and run_lammps_chain to suppress false Coeffs errors. Same as PEG1 and PEG2. engine=kokkos is host default for single-GPU runs (GPU-package was CPU-bound at 0% util).

**How to apply:** For any POXI/PCFF (or other EMC PCFF class) run, always locate and pass the emc_build.params alongside the .data file. Use engine=kokkos, mpi=1 as the host default.

Related: [[peg1-equil-chain]] [[peg2-equil-chain]]
