---
name: emc-seed-not-persisted
description: EMC seed must be logged from the prompt/resolved_seed; get_emc_job_output echoes resolved_seed — never report -1
metadata:
  type: feedback
---

The EMC seed passed to `submit_emc_cell_job(seed=...)` is echoed back as `result["resolved_seed"]` in `get_emc_job_output`. Use that to confirm the seed actually used, and report it in the RESULT block.

**Why:** Reproducibility depends on the exact seed. For revision baselines the seed is FIXED in the prompt (from guides/REVISION_PARAMS.md) — e.g. PSU2/PSFO used emc_seed=820419, confirmed by resolved_seed=820419 in job output. Never report `-1` (that's the "pick random" sentinel, not a usable seed); if seed=-1 was passed, read resolved_seed back and log that integer.

**How to apply:** Record the seed in run_log.md BEFORE submitting (cross-track rule 2). After completion, cross-check `result["resolved_seed"]` matches what you passed and put that integer in the RESULT `emc_seed` field. See [[emc-output-naming]].
