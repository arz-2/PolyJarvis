---
name: emc-output-name-ignored
description: submit_emc_cell_job ignores output_name — always writes emc_build.data/.params, not <output_name>.data
metadata:
  type: feedback
---

`submit_emc_cell_job(output_name="polymer", ...)` does NOT produce `polymer.data`. The EMC server always writes `emc_build.data` and `emc_build.params` regardless of `output_name`.

**Why:** The MOLECULE_BUILDER guide's Path-A example uses `output_name="polymer"`, which misleads you into thinking the file is named `polymer.data`. A background `until [ -f .../polymer.data ]` wait will hang forever (until its timeout) because that file is never created.

**How to apply:** Never poll for `<output_name>.data` to detect completion. Instead poll `get_emc_job_status(job_id)` until `status=="completed"`, then read the actual path from `get_emc_job_output(job_id)["result"]["data_path"]` (which correctly points at `emc_build.data`). The documented copy step works only because it reads `data_path` from the result dict, not because the filename matches `output_name`.
