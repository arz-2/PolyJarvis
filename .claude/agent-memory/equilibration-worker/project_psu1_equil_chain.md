---
name: project-psu1-equil-chain
description: PSU1 Polysulfone equilibration: 9-stage glassy chain, PCFF, temp=700 K, chain_id=a3dd19a9
metadata:
  type: project
  ingested_at: 2026-06-22
---

PSU1 Polysulfone (PSFO class) equilibration submitted 2026-06-18.

**Chain:** 9-stage glassy path (temp=700 K > 300 K, add_300k_production=True). Stage 09 npt_prod300 at 300 K is the density/deformation source.

**Key params:** use_pcff=True, max_temp=780 K, n_atoms=8656, gpu_ids=0,1,2,3, mpi=4, SEED_HOT=723979 (nvt_softheat velocity init only; no SEED_COLD — subsequent stages read from data/restart files).

**chain_id:** a3dd19a9
**work_dir:** /home/arz2/PolyJarvis/data/PSU1/lammps/

**Why:** PSFO uses PCFF (Class II); glassy polymer (exp Tg ~190 C); 9-stage chain mandatory so stage 09 produces 300 K density for mechanical track.

**How to apply:** If re-running PSU1 or similar PSFO chains, use temp=700 K (not 300 K), use_pcff=True, add_300k_production=True. Only one velocity seed is emitted (in nvt_softheat); this is normal for PCFF LAMMPS chains.
