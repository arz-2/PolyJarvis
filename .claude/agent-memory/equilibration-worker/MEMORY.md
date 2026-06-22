# Equilibration Worker Memory Index

- [PE density re-run corrected protocol](project_pe1_melt_npt_protocol.md) — PE1 replicate 1: add_melt_npt=True, t_equil_K=550 K, melt_npt_steps=1M, npt_prod_steps=5M; 9-stage chain with melt branch confirmed [ingested 2026-06-20]
- [PSU1 Polysulfone equil chain](project_psu1_equil_chain.md) — PSFO/PCFF 9-stage glassy chain, temp=700 K, max_temp=780 K, n_atoms=8656, chain_id=a3dd19a9; only one velocity seed (723979) in nvt_softheat
- [cis-PBD1 equil chain](project_cispbd1_equil_chain.md) — PDIE/TraPPE-UA 7-stage rubbery chain, temp=300 K, max_temp=480 K, n_atoms=8040, chain_id=c2e7c43e; SEED_HOT=853457; SEED_COLD=N/A (nvt_production inherits)
- [cis-PBD2 equil chain](project_cispbd2_equil_chain.md) — PDIE/TraPPE-UA 7-stage rubbery chain, temp=300 K, max_temp=480 K, n_atoms=8040, chain_id=49d5c679; SEED_HOT=355754; gpu_ids=0, mpi=1; params_file required despite worker guide saying omit
- [PEG1 equil chain](project_peg1_equil_chain.md) — POXI/PCFF 7-stage rubbery chain, temp=300 K, max_temp=580 K, n_atoms=7020, chain_id=ae9b7b4b; SEED_HOT=548980; params_file required for EMC PCFF Coeffs
- [PS1 atactic Polystyrene equil chain](project_ps1_equil_chain.md) — PSTR/PCFF 9-stage glassy chain, temp=550 K, max_temp=630 K, n_atoms=6420; prior chain 76ded65d failed (mpirun), retry chain_id=6f8a5143; SEED_HOT=179213; gpu_ids=1, mpi=4
- [PEEK2 PEEK equil chain](project_peek2_equil_chain.md) — PKTN/PCFF 9-stage glassy chain, temp=770 K, max_temp=850 K, n_atoms=10900, chain_id=2a790dda; SEED_HOT=55628; engine=kokkos, gpu_ids=2, mpi=1
- [PE2 Polyethylene equil chain](project_pe2_equil_chain.md) — PHYC/TraPPE-UA 7-stage rubbery chain, temp=300 K, max_temp=620 K, n_atoms=4840, chain_id=b0ad167b; SEED_HOT=1005; params_file required (emc_build.params); GPU1, mpi=1
