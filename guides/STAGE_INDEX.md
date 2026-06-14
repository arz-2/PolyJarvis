# PolyJarvis Cross-Stage Rules
**Version:** 2.0 | **Last updated:** June 10, 2026

Inlined into every worker prompt by `gen_prompt.py`. These rules apply regardless of stage.
Recovery thresholds and error taxonomy live in `CLAUDE.md` (Recovery Reference section) — for orchestrator use.

---

## Cross-Stage Rules (Always Active — Memorize These)

0. **RadonPy path: force field AFTER polymerization** — never before (EMC handles this automatically)
1. **GPU is used for ALL simulation stages** — always pass explicit `gpu_ids` and `mpi`; never leave them unset or default
2. **Check convergence before extracting properties**
3. **Never report Tg without verifying bilinear fit R²**
4. **Fill `run_log.md` in real time** — log each DECISION row when made, each RECOVERY block immediately after resolving an error; do not reconstruct at the end
5. **Record all seeds before submitting any job** — log EMC seed, SEED_HOT, and SEED_COLD in the run_log header. For replication studies, use fixed seeds from `guides/REVISION_PARAMS.md`. For exploratory runs, read seeds back from job output and log them immediately after submission.
6. **Always call `watch_run(chain_id)` immediately after `run_lammps_chain`** — `watch_run` is what creates the sentinel file; without it the chain may complete but Monitor hangs forever. Pattern: `run_lammps_chain` → `watch_run` → `Monitor`. Both tools return immediately.
