# Molecule Builder Memory Index

- [PEST routing](pest_routing.md) — PEST (PLA/PET/PCL)→EMC/PCFF, charge none, pppm; no co-occur/warning; use_pcff:true [ingested 2026-06-25]
- [EMC binary annual expiry](feedback_emc_binary_annual_expiry.md) — "Validity has run out" exit 255 on ALL EMC jobs; swap bin/ only from fresh SourceForge tgz, never field/
- [EMC output has no params_path key](feedback_emc_output_no_params_path_key.md) — build params path from output_dir; .data has no Pair Coeffs, emc_build.params is load-bearing
- [work_dir already ends in /cell](feedback_workdir_double_cell_path.md) — gen_prompt appends /cell; don't nest cell/cell/; phal_patch flag has no consumer
