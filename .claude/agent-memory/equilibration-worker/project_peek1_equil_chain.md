---
name: peek1_equil_chain
description: PEEK1 PKTN/PCFF glassy melt-phase chain (rebuild nchain=17), temp=770K, max_temp=850K, n_atoms=18530, chain_id=a6fd9db8
metadata:
  type: project
---

PEEK1 (PKTN/PCFF) equilibration, phase=melt submission. This is a REBUILD at nchain=17 (was 8;
prior attempt archived at data/PEEK1/attempt1_nchain8/, failed SIZE_CHAIN_SELF_IMAGE gate).

- data_file: /home/arz2/PolyJarvis/data/PEEK1/lammps/equil/cell.data (18530 atoms, box 73.35 A cubic)
- params_file: /home/arz2/PolyJarvis/data/PEEK1/lammps/equil/emc_build.params
- inspect_data_file: valid=true, errors=[], warnings=[], net_charge=0, density=0.66 g/cm3 (uncompressed cell)
- Note: this MCP server's inspect_data_file tool signature does NOT accept nchain/target_density_gcm3
  params (checked against actual tool schema) — the finite-size forecast feature described in the
  worker guide is not available through this tool version; only the standard validation ran.
- generate_equilibration_workflow: temp=770 (glassy, >300K) -> 9-stage chain (run_order: minimize,
  nvt_softheat, npt_compress, npt_pppm, npt_cool, nvt_production, npt_production, npt_cool300,
  npt_prod300). max_temp=850, engine=kokkos, gpu_ids=1, mpi=1, velocity_seed=null (random).
- phase=melt: submitted only the first 7 stages (through npt_production) as chain_id=a6fd9db8.
  Remaining 2 stages (npt_cool300, npt_prod300) written to
  /home/arz2/PolyJarvis/data/PEEK1/lammps/equil/_pending_cooldown_stages.json for the cooldown-phase
  resubmission.

See [[project_psu3_equil_chain]] for another PCFF glassy 700K-class chain with similar sizing.
