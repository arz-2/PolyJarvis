---
name: emc-output-naming
description: EMC writes emc_build.data (not polymer.data) regardless of output_name; never hardcode the data filename
metadata:
  type: feedback
---

EMC cell jobs write their LAMMPS data file as `emc_build.data` in the job output_dir, NOT `<output_name>.data` (e.g. NOT `polymer.data` even when `output_name="polymer"`). Same prefix for siblings: `emc_build.params`, `emc_build.emc.gz`, `emc_build.pdb.gz`, `emc_build.psf.gz`, `emc_build.in/.esh`.

**Why:** EMC's emc_setup.pl uses a fixed internal job basename `emc_build` for the build script and all generated artifacts; `output_name` does not rename the produced files. A background watcher that waits on `<output_dir>/polymer.data` will never fire even on success (PSU2/PSFO, 2026-06-23: job 302087b7 completed fine but the polymer.data watch condition never matched).

**How to apply:** Never hardcode/guess the data filename. After `get_emc_job_status` reports `completed`, call `get_emc_job_output(job_id)` and take `result["data_path"]` verbatim for both the existence check and the `cp` to `{work_dir}/cell/cell.data`. If you must poll a file in a background watcher, watch for `emc_build.data` (or just poll job status), not `polymer.data`. See [[emc-seed-not-persisted]].
