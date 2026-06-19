---
name: emc-output-naming
description: EMC cell job writes emc_build.data/.params regardless of output_name arg
metadata:
  type: project
---

The `output_name` argument to `submit_emc_cell_job` does NOT rename the output
`.data` / `.params` files. The EMC server always writes `emc_build.data` and
`emc_build.params` into the job's output_dir
(`/home/arz2/polyjarvis_emc_jobs/<job_id>/`).

**Why:** The EMC ESH template hardcodes the `emc_build` prefix; output_name only
affects internal job tracking.

**How to apply:** When copying outputs to `{work_dir}/cell/`, source
`emc_build.data` (not `<output_name>.data`). A background wait-for-file loop
should watch for `emc_build.data`, not `<output_name>.data`. See
[[trappe-result-block]].
