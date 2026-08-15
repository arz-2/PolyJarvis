# Molecule Builder Memory Index

- [PEST routing](pest_routing.md) — PEST (PLA/PET/PCL)→EMC/PCFF, charge none, pppm; no co-occur/warning; use_pcff:true [ingested 2026-06-25]
- [PDIE routing + stereo trap](pdie_routing.md) — PDIE→EMC/TraPPE-UA (use_trappe:true); EMC ignores SMILES cis/trans → ~50:50 mixture; verify by torsion, not atom type
- [PKTN routing](pktn_routing.md) — PKTN (PEEK)→EMC/PCFF, charge none, pppm; co-occurs POXI+PPNL, ff_confidence low vs prompt's cited; coeffs live in emc_build.params
- [EMC params cutoff mismatch](feedback_emc_params_cutoff_mismatch.md) — EMC hardcodes cutoff/charge_cutoff 9.5 A in emc_build.params vs prompt cutoff_A; report, don't rebuild
- [EMC wait + scope friction](feedback_emc_wait_and_scope_friction.md) — foreground until-loop blows the 600s Bash cap on ~27k-atom builds; poll get_emc_job_status; MCP source is out of Bash scope
- [EMC wait patterns blocked](feedback_emc_wait_patterns_blocked.md) — arm a run_in_background until-loop on emc_build.data and end the turn; chained sleeps blocked, foreground loops blow the 600s cap
- [EMC seed null conflict](feedback_emc_seed_null_conflict.md) — prompt says null→seed=-1, guide forbids -1; draw an integer, EMC echoes it as resolved_seed
- [Rebuild nchain verification](feedback_rebuild_nchain_verification.md) — on finite-size rebuilds, check natoms = nchains x (dp x RU atoms + 2) before reporting; EMC number-mode fallback is silent
- [Output contract footguns](feedback_output_contract_footguns.md) — work_dir already ends in /cell (don't double-nest); RESULT template omits lammps_flags use_trappe — copy tool output verbatim
