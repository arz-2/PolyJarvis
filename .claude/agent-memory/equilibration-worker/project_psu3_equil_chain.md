---
name: project-psu3-equil-chain
description: PSFO/PCFF 9-stage glassy equil chain for PSU3 (Polysulfone), temp=700 K, max_temp=780 K, n_atoms=10816, chain_id=b617e91c
metadata:
  type: project
  ingested_at: 2026-06-25
---

PSFO/PCFF 9-stage glassy equilibration chain for PSU3 (Polysulfone).

- data_file: data/PSU3/lammps/equil/cell.data
- params_file: data/PSU3/lammps/equil/emc_build.params
- temp: 700 K (T_workflow_K; glassy, temp>300 → 9-stage with npt_cool300 + npt_prod300)
- max_temp: 780 K (T_anneal_high_K)
- press: 1.0 atm
- max_press: 50000 atm
- n_atoms: 10816
- chain_id: b617e91c
- engine: kokkos
- gpu_ids: 3
- mpi: 1
- velocity_seed: random (read back from nvt_softheat.log)
- n_stages: 9
- npt_prod_data_path: data/PSU3/lammps/equil/npt_prod300/npt_prod300_out.data
- npt_prod300_log: data/PSU3/lammps/equil/npt_prod300/npt_prod300.log
- submitted: 2026-06-24

**Why:** PSFO is a high-Tg glassy polysulfone; equilibration at 700 K (above Tg ~456-513 K exp) + cool to 300 K for density/deformation source.

**How to apply:** density and deformation source is npt_prod300_out.data (stage 09), NOT npt_production_out.data (stage 07). npt_tg_prep_data=null (glassy path, no melt NPT stage).

## Extension (2026-06-25)

equil-check returned EXTEND: density 1.1825 g/cm³ (SEM 0.029%, drift 0.115%) well-converged but Rg CV 36.5% and density-homogeneity CV 25.1% exceeded Poisson-limited 25.0% threshold — marginal finite-size gates.

- extend_from_data: data/PSU3/lammps/equil/npt_prod300/npt_prod300_out.data
- extend_ns: 2.0 (2,000,000 steps at dt=1 fs)
- extend_temp: 300 K (npt_prod_temp_K — NOT 700 K melt)
- extend_chain_id: db36267e
- npt_extend_out_data: data/PSU3/lammps/equil/npt_extend/npt_extend_out.data
- engine: kokkos, gpu_ids: 3, mpi: 1
