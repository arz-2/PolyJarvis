# Equilibration Worker Memory Index

- [TraPPE-UA EMC validation false-positive](feedback_trappe_ua_validation.md) — EMC TraPPE-UA .data files have no Coeffs sections; validate_data_file will always flag 4 blocking errors — this is expected, not a real blocker [ingested 2026-06-05]
- [TraPPE-UA use_trappe flag](feedback_trappe_use_flag.md) — PHYC/PDIE/PSTR classes require use_trappe=True in generate_equilibration_workflow; lammps_flags only carries use_pcff/use_opls so must be inferred from polymer_class [ingested 2026-06-05]
- [Do not pass data_file to run_lammps_chain for EMC builds](feedback_chain_no_data_file.md) — For EMC TraPPE-UA (and likely PCFF) builds, omit data_file from run_lammps_chain to avoid preflight re-blocking on missing Coeffs
