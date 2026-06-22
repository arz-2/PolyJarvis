---
name: peg1-equil-chain
description: PEG1 Polyethylene glycol (POXI/PCFF) 7-stage rubbery equil chain, temp=300 K, max_temp=580 K, n_atoms=7020, chain_id=ae9b7b4b
metadata:
  type: project
  ingested_at: 2026-06-22
---

PEG1 (PEO/PEG, POXI class, PCFF force field) 7-stage rubbery equilibration chain submitted 2026-06-20.

- chain_id: ae9b7b4b
- n_atoms: 7020 (matched expected)
- n_stages: 7 (Path B rubbery — no 300K prod appendix)
- temp: 300.0 K, max_temp: 580.0 K
- npt_prod_steps: 2,000,000
- gpu_ids: "0", mpi: 4
- SEED_HOT: 548980 (nvt_softheat velocity create seed)
- SEED_COLD: N/A (nvt_production inherits velocities from data file)
- params_file: /home/arz2/PolyJarvis/data/PEG1/lammps/cell/emc_build.params

**Why:** POXI/PCFF EMC build — Coeffs live in params file, not .data; passed params_file to both inspect_data_file and run_lammps_chain to suppress false Coeffs errors.

**How to apply:** For any POXI/PCFF (or other EMC PCFF class) run, always locate and pass the emc_build.params alongside the .data file. Coeffs-missing errors from inspect_data_file are expected and suppressed by params_file argument.

Related: [[psu1-equil-chain]]
