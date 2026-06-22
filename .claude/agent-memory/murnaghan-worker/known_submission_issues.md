---
name: murnaghan_submission_issues
description: Known blocker bugs in run_bulk_modulus_series generator (chain log-path concatenation, missing kokkos engine support)
metadata:
  type: feedback
---

## Issue 1: Log-path concatenation in chain script generator (BLOCKER)

**Symptom:** Chain exits status=failed before stage 1 completes (no progress file written).

**Root cause:** In the generated chain script (e.g. `chain_886eab7d.sh`), the log redirect on each stage concatenates `stage_dir` (e.g. `.../bm_P0/`) with an already-absolute `log_path` (e.g. `/home/arz2/.../bm_P0/bm_P0.log`):
```bash
mpirun ... >> /home/arz2/.../bm_P0//home/arz2/.../bm_P0/bm_P0.log
```
This tries to write to a nested `home/...` dir that doesn't exist (only `bm_P0/` was created). Bash `>>` does not create parent dirs → redirect fails → immediate `log_fail` + `sentinel_fail` + chain exits 1 on stage 1.

**Why:** The chain generator does not check whether `log_path` is already absolute before concatenating with stage_dir; it always prefixes.

**How to apply:** After calling `run_bulk_modulus_series`, immediately check sentinel JSON (path: `/tmp/polyjarvis/sentinels/done_<chain_id>.json`). If `status: failed` and progress JSONL is empty/missing, this is the log-path bug. Return error RESULT to orchestrator without calling Monitor.

**Status:** Confirmed PSU1 2026-06-21 chain 886eab7d; likely affects all glassy Murnaghan submissions until server.py is patched.

---

## Issue 2: Missing kokkos engine support in run_bulk_modulus_series (CAPABILITY GAP)

**Symptom:** Tool generates scripts with `-sf gpu -pk gpu` (old CUDA/GPU package) instead of kokkos flags (`-k on g 1 -sf kk -pk kokkos`).

**Root cause:** `run_bulk_modulus_series` signature has no `engine` parameter (only `use_gpu=True`, `use_pcff`, `use_opls`, `use_trappe` for FF selection). It cannot emit kokkos binary or kokkos-specific flags.

**Why:** Murnaghan was originally designed for rubbery polymers (glassy path is new via CLAUDE.md guides/MURNAGHAN.md Rule B); kokkos requirement was not backported to the tool.

**How to apply:** At tool-call time, check if the task demands kokkos. If so, either:
1. Add `engine="kokkos"` to the prompt and verify it's accepted by the tool (it isn't, as of 2026-06-21).
2. Flag in RESULT that engine selection is not supported and return error.

**Status:** Confirmed PSU1 2026-06-21; affects all runs claiming kokkos requirement.

---

## Memory Links

- [[murnaghan_workflow_rules]] — glassy/rubbery routing logic, pressure defaults
