---
name: peek2-equil-chain
description: PEEK2 PKTN/PCFF 9-stage glassy equil chain, temp=770 K, max_temp=850 K, n_atoms=10900, chain_id=2a790dda
metadata:
  type: project
---

PEEK2 (Poly(ether ether ketone)) replicate 1 — glassy path (temp=770 K > 300 K).

- Class: PKTN / PCFF / PPPM
- n_atoms: 10900 (DP=32, 10 chains)
- temp: 770.0 K, max_temp: 850.0 K
- engine: kokkos, gpu_ids: 2, mpi: 1
- chain_id: 2a790dda
- n_stages: 9 (add_300k_production=True → npt_cool300 + npt_prod300 appended)
- SEED_HOT: 55628 (velocity in nvt_softheat)
- SEED_COLD: N/A (nvt_production inherits)
- params_file: /home/arz2/PolyJarvis/data/PEEK2/lammps/cell/emc_build.params
- npt_prod300_data: /home/arz2/PolyJarvis/data/PEEK2/lammps/npt_prod300/npt_prod300_out.data (density + deform source)
- submitted: 2026-06-22

**Why:** PEEK is a high-performance aromatic ether/ketone thermoplastic (Tg ~415 K exp). Glassy path required — 300 K chains are frozen.
**How to apply:** Stage 09 npt_prod300 is the density and deformation source for mechanical track.
