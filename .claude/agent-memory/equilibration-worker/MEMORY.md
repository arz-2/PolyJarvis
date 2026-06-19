# Equilibration Worker Memory Index

- [PE density re-run corrected protocol](project_pe1_melt_npt_protocol.md) — PE1 replicate 1: add_melt_npt=True, t_equil_K=550 K, melt_npt_steps=1M, npt_prod_steps=5M; 9-stage chain with melt branch confirmed
- [PSU1 Polysulfone equil chain](project_psu1_equil_chain.md) — PSFO/PCFF 9-stage glassy chain, temp=700 K, max_temp=780 K, n_atoms=8656, chain_id=a3dd19a9; only one velocity seed (723979) in nvt_softheat
- [cis-PBD1 equil chain](project_cispbd1_equil_chain.md) — PDIE/TraPPE-UA 7-stage rubbery chain, temp=300 K, max_temp=480 K, n_atoms=8040, chain_id=c2e7c43e; SEED_HOT=853457; SEED_COLD=N/A (nvt_production inherits)
