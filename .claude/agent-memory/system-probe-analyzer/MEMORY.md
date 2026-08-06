# system-probe-analyzer Memory Index

The pre-equilibration probe (`system-probe-worker`, `task=analyze_probe`) was removed 2026-08-06 —
`refine_from_equil` against the real equilibration chain's own hold is the sole task now.

## Feedback
- [D-09 Edit anchor slip](feedback_d09_edit_anchor_slip.md) — anchoring on bare `"planned_stages": [` inserts D-09 outside decisions[]; anchor on prior decision's closing content, verify with `jq '.decisions[].id'`

## Project
- [Cache writes zero-value entries on probe failure — RESOLVED](project_cache_writes_zero_value_entries_on_probe_failure.md) — cache write still gates on ≥1 reliability flag true; a fully-unreliable characterization writes nothing (mechanism proven probe-era, now the only path via refine_from_equil)
