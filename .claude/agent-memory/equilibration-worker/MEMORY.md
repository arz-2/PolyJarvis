# Equilibration Worker Memory Index

- [TraPPE-UA EMC validation false-positive](feedback_trappe_ua_validation.md) — EMC TraPPE-UA .data files have no Coeffs sections; validate_data_file will always flag 4 blocking errors — this is expected, not a real blocker [ingested 2026-06-05]
- [TraPPE-UA use_trappe flag](feedback_trappe_use_flag.md) — PHYC/PDIE/PSTR classes require use_trappe=True in generate_equilibration_workflow; lammps_flags only carries use_pcff/use_opls so must be inferred from polymer_class [ingested 2026-06-05]
- [PCFF EMC builds: pass params_file to both generate and run calls](feedback_chain_no_data_file.md) — Pass params_file to generate_equilibration_workflow AND run_lammps_chain; data_file can be included when params_file is also present (suppresses Coeffs false-positive). Confirmed PAMD/Nylon1 2026-06-06. [ingested 2026-06-10]
- [PSIL/OPLS-AA equilibration settings](feedback_psil_opls_equil.md) — PSIL is rubbery (exp_Tg=148 K): use temp=300.0 not T_equil_K=350; use_opls=True MUST be passed; dihedral_style=multi/harmonic (NOT fourier); params_file required to suppress Coeffs false-positive [ingested 2026-06-10]
