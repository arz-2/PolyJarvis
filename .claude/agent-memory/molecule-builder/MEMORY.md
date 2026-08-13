# Molecule Builder Memory Index

- [PEST routing](pest_routing.md) — PEST (PLA/PET/PCL)→EMC/PCFF, charge none, pppm; no co-occur/warning; use_pcff:true [ingested 2026-06-25]
- [PDIE routing + stereo trap](pdie_routing.md) — PDIE→EMC/TraPPE-UA (use_trappe:true); EMC ignores SMILES cis/trans → ~50:50 mixture; verify by torsion, not atom type
- [PKTN routing](pktn_routing.md) — PKTN (PEEK)→EMC/PCFF, charge none, pppm; co-occurs POXI+PPNL, ff_confidence low vs prompt's cited; coeffs live in emc_build.params
- [EMC params cutoff mismatch](feedback_emc_params_cutoff_mismatch.md) — EMC hardcodes cutoff/charge_cutoff 9.5 A in emc_build.params vs prompt cutoff_A; report, don't rebuild
- [Output contract footguns](feedback_output_contract_footguns.md) — work_dir already ends in /cell (don't double-nest); RESULT template omits lammps_flags use_trappe — copy tool output verbatim
