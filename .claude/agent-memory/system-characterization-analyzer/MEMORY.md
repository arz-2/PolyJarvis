# system-probe-analyzer Memory Index

The pre-equilibration probe (`system-probe-worker`, `task=analyze_probe`) was removed 2026-08-06 —
`refine_from_equil` against the real equilibration chain's own hold is the sole task now.

## Feedback
- [Bash denied on guides/*.json](feedback_bash_denied_guides_json.md) — Bash sandboxed to data/**; use Read (paged) for polymer_rules.json/MURNAGHAN.md, never grep/jq/cat via Bash
- [Cache write goes through the merge script](feedback_cache_write_blind_no_read.md) — never `Write` system_characterization_cache.json; use write_characterization_cache.py, which merges one SMILES key and enforces the reliability gate

## Project
