# system-probe-analyzer Memory Index

The pre-equilibration probe (`system-probe-worker`, `task=analyze_probe`) was removed 2026-08-06 —
`refine_from_equil` against the real equilibration chain's own hold is the sole task now.

## Feedback
- [Bash denied on guides/*.json](feedback_bash_denied_guides_json.md) — Bash sandboxed to data/**; use Read (paged) for polymer_rules.json/MURNAGHAN.md, never grep/jq/cat via Bash
- [Cache write goes through the merge script](feedback_cache_write_blind_no_read.md) — never `Write` system_characterization_cache.json; use write_characterization_cache.py, which merges one SMILES key and enforces the reliability gate
- [Glassy hold can never pass the C(t) gate](feedback_glassy_hold_ct_gate_never_satisfiable.md) — npt_prod300 kinetic-trap physics is expected → decay_fraction≈0 → probe_tau_relax_reliable structurally false for glassy classes; not a per-run anomaly, don't re-probe melt stage
- [write_characterization_cache.py wants flat derived_* keys](feedback_write_cache_script_flat_field_contract.md) — build a separate flat --fields scratch JSON, don't hand it system_characterization.json's nested "derived" object verbatim

## Project
- [check_equilibration_comprehensive --bond_length_A break (2026-08-14)](feedback_bond_length_a_arg_tool_break.md) — loaded MCP server stale vs on-disk script after a concurrent edit; trust orchestrator-supplied precomputed result instead of retrying
