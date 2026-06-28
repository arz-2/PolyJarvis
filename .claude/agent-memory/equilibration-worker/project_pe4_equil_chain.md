---
name: project-pe4-equil-chain
description: PE4 Polyethylene PHYC/TraPPE-UA 9-stage rubbery add_melt_npt chain, chain_id=efeec2a8, GPU 0, engine=gpu
metadata:
  type: project
---

PE4 Polyethylene (PHYC/TraPPE-UA) 9-stage rubbery chain with add_melt_npt submitted 2026-06-25.

- chain_id: efeec2a8
- engine: gpu (not kokkos — TraPPE-UA, no PCFF Class II)
- gpu_ids: 0, mpi: 1
- n_atoms: 4840
- temp: 300 K, max_temp: 620 K, t_equil_K: 550 K
- npt_prod_steps: 2500000, melt_npt_steps: 500000
- velocity_seed: random (null → read back from nvt_softheat.log)
- params_file: data/PE4/lammps/equil/emc_build.params (required for EMC TraPPE-UA Coeffs)
- npt_tg_prep_data: data/PE4/lammps/equil/npt_melt/npt_melt_out.data (Tg sweep starting cell at 550 K)
- npt_production_log: data/PE4/lammps/equil/npt_production/npt_production.log
- npt_production_dir: data/PE4/lammps/equil/npt_production

**Why:** PE is rubbery (exp_Tg_K << 300 K); add_melt_npt provides an isothermal npt_melt at 550 K for Tg sweep starting cell and density extraction at the melt.
**How to apply:** Stage 09 npt_production at 300 K is the primary density/bulk-modulus source. npt_tg_prep_data feeds the Tg sweep worker. Read velocity_seed back from nvt_softheat.log after chain starts.
