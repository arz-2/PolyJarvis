# system-probe-analyzer Memory Index

The pre-equilibration probe (`system-probe-worker`, `task=analyze_probe`) was removed 2026-08-06 —
`refine_from_equil` against the real equilibration chain's own hold is the sole task now.

## Feedback
- [Cache write goes through the merge script](feedback_cache_write_blind_no_read.md) — never `Write` system_characterization_cache.json; use write_characterization_cache.py, which merges one SMILES key and enforces the reliability gate
- [write_characterization_cache.py wants flat derived_* keys](feedback_write_cache_script_flat_field_contract.md) — build a separate flat --fields scratch JSON, don't hand it system_characterization.json's nested "derived" object verbatim

## Project
