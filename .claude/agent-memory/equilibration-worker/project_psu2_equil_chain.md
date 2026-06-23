---
name: project_psu2_equil_chain
description: PSU2 glassy PSFO, PCFF, kokkos, GPU 0, 9-stage chain e1eb596f, 2026-06-23
metadata:
  type: project
---

PSU2 equilibration chain submitted 2026-06-23.

- polymer_class: PSFO (Polysulfone/Udel)
- force_field: PCFF
- engine: kokkos, gpu_ids="0", mpi=1
- n_atoms: 10820
- data_file: /home/arz2/PolyJarvis/data/PSU2/lammps/equil/cell.data
- chain_id: e1eb596f
- n_stages: 9 (glassy: temp=700.0 K > 300 K → npt_cool300 + npt_prod300 appended)
- temp: 700.0 K, max_temp: 780.0 K, press: 1 atm
- velocity_seed: 611213
- npt_prod300_data: /home/arz2/PolyJarvis/data/PSU2/lammps/equil/npt_prod300/npt_prod300_out.data
- npt_prod300_log: /home/arz2/PolyJarvis/data/PSU2/lammps/equil/npt_prod300/npt_prod300.log

**Why:** PSU (BPA-sulfone) is a high-Tg glassy polymer (~460 K exp); equilibrated above Tg at 700 K, then cooled to 300 K for density + BM extraction (glassy path A).
**How to apply:** Use npt_prod300_out.data as source for Murnaghan BM series and Tg sweep starting cell.
