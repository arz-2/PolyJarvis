# Molecule Builder Memory Index

- [EMC output naming](emc_output_naming.md) — EMC always writes emc_build.data (not polymer.data); take data_path from get_emc_job_output verbatim
- [EMC seed not persisted](emc_seed_not_persisted.md) — read resolved_seed from job output; never report -1; record seed before submit
- [PSFO routing](psfo_routing.md) — PSFO→EMC/PCFF, charge none, pppm; co-occurs POXI+PPNL (expected); use_pcff:true
