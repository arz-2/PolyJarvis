# Error-Recovery Benchmark

Quantifies the agent's failure-recovery behavior:
inject each cataloged fault, verify the injection fires a genuine runtime error, check the
classifier labels it correctly, and (for pre-scripted faults) apply the documented fix and
verify it resolves. Inferred faults (generalization probes) have no scripted recovery and are
recorded as "left for AGENT" — the agent resolves those at the full launch (see the
`RECOV_F5_AGENT/`, `RECOV_F6_AGENT/` run dirs alongside this file).

## Run

```bash
# Cheap surfaces only (no LAMMPS/EMC):
python manuscript/recovery/run_recovery_benchmark.py --faults all --smoke

# REAL path: launch the actual tool, capture the genuine error, recover, verify
# (tiny runtime-generated cells; add --gpu N to run LAMMPS decks on a GPU):
python manuscript/recovery/run_recovery_benchmark.py --faults all --execute
```

Exit is non-zero if any injection fails to fire or the classifier mislabels.

## Modules

| File | Role |
|---|---|
| `run_recovery_benchmark.py` | Entry point; orchestrates inject → classify → recover → report |
| `fault_catalog.py` | The six faults F1–F6 (4 pre-scripted, 2 inferred) with injection + scripted recovery |
| `fault_executors.py` | `--execute` path: real tool launches that trigger each fault at runtime |
| `error_classifier.py` | Maps error text → error class + pre-scripted/inferred label |
| `metrics.py` | `RunMetrics`/`RecoveryEvent` accounting and success rates |
| `REAL_FAULT_CAPTURE.md` | Design notes for the `--execute` real-fault path |
| `results/` | Report JSONs (`recovery_benchmark_{smoke,execute}.json`, agent-run captures) |
| `tests/` | Unit tests for the classifier, catalog, and seed handling |

