---
name: missing-query-best-match-script
description: query_best_match.py script does not exist; workflow cannot proceed to exp-lookup stage
metadata:
  type: feedback
---

**Missing script:** `db/query_best_match.py` (repo-relative, resolved against `<repo_root>`) is referenced in exp-lookup-worker stage guide but does not exist in the codebase.

**Why:** Stage guide (inlined in exp-lookup-worker prompt) defines the full lookup workflow and expects this Python script to query polymer_db.sqlite for experimental ranges (Tg, density, bulk modulus). Without it, the worker cannot execute.

**How to apply:** Before exp-lookup-worker can run, either (1) implement query_best_match.py per the stage guide spec, or (2) have the orchestrator skip exp-lookup and fall back to polymer_rules.json ranges for all properties. Current workaround: orchestrator omits exp_tg_min/max, exp_density_min/max, exp_K_min/max overrides from gen_prompt.py calls and lets defaults handle it.
