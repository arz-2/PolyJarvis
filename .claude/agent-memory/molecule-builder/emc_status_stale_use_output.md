---
name: emc-status-stale-use-output
description: get_emc_job_status can report "running" indefinitely after an EMC cell job has actually completed — poll get_emc_job_output to get ground truth, and watch for output.*/emc_build.data not cell.data
metadata:
  type: feedback
ingested_at: 2026-06-10
---

`get_emc_job_status(job_id)` can keep returning `status: "running"` (has_result=false, has_error=false) even after the EMC build has already finished successfully. `get_emc_job_output(job_id)` returned the completed result with data_path while status still said running (BPAPC1/PCBN job 37ba7e71, completed 11898 atoms).

**Why:** the EMC server's status thread does not reliably flip to "completed"; the result object is populated independently. Relying on status alone causes you to wait forever on a finished job.

**How to apply:**
- After submitting an EMC cell job, poll BOTH: if status is still "running" but the job has been going a few minutes, call `get_emc_job_output(job_id)` — it returns the full result dict the moment the build finishes.
- EMC writes the data file as `<output_name's esh base>.data` → in practice `emc_build.data` (NOT `cell.data`). The output dir also has `emc_build.params`, `emc_build.emc.gz`, `.pdb.gz`, `.psf.gz`. A background watcher globbing for `cell.data` will never fire — glob `*.data` or just trust get_emc_job_output.
- `ps` showing no `emc` process does NOT mean failure — the binary is fast (BPA-PC dp=40, ~12k atoms finished in ~4.5 min) and may already have exited cleanly by the time you check.

See [[psil_now_buildable]] for the other recent EMC note.
