---
name: peg2-equil-chain
description: PEG2 Polyethylene glycol (POXI/PCFF) 7-stage rubbery equil chain, temp=300 K, max_temp=580 K, n_atoms=7020, chain_id=ed32756d; engine=kokkos, gpu_ids=0, mpi=1
metadata:
  type: project
  ingested_at: 2026-06-22
---

PEG2 (PEO/PEG, POXI class, PCFF force field) 7-stage rubbery equilibration chain submitted 2026-06-22.

- chain_id: ed32756d
- n_atoms: 7020 (matched expected)
- n_stages: 7 (Path B rubbery — no 300K prod appendix)
- temp: 300.0 K, max_temp: 580.0 K
- npt_prod_steps: 2,000,000
- gpu_ids: "0", mpi: 1, engine: kokkos
- SEED_HOT: random (velocity_seed=null; read from nvt_softheat output after completion)
- SEED_COLD: N/A (nvt_production inherits velocities from data file)
- params_file: /home/alexzhao/PolyJarvis/data/PEG2/lammps/equil/emc_build.params

**Why:** POXI/PCFF EMC build — Coeffs live in params file, not .data; passed params_file to inspect_data_file and run_lammps_chain to suppress false Coeffs errors. engine=kokkos per plan hardware override.

**How to apply:** For any POXI/PCFF run with kokkos engine, pass params_file to both inspect_data_file and run_lammps_chain; engine="kokkos" must match workflow generation and chain submission.

Related: [[peg1-equil-chain]]
