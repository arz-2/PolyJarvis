---
name: dont-assert-prior-run-results-unchecked
description: Never write an evidence string that asserts a prior-run RESULT (ladder used, slope_gate_pass) without jq-checking that run's plan/result first
metadata:
  type: feedback
  ingested_at: 2026-06-26
---

When writing a reasoned plan's `evidence`, do NOT assert what a prior sibling run *did* or *achieved* unless you verify it with `jq` against that run's `run_plan.json` / `*_result.json`. Cite config/policy (which you can see), not unverified prior-run outcomes.

**Why:** On PSU4 I wrote "[25,50,100] is the validated PSFO ladder (PSU1/PSU2)." Checking proved it false — PSU1 ran [40,160,640], PSU2 ran [40,160,400], and PSU2's `slope_gate_pass=false`. polymer_rules.json default IS [25,50,100], but the prior PSU runs deviated to faster custom ladders. The assertion conflated "the class default" with "what prior runs used + passed." A critic would have burned a round on an unsourceable claim.

**How to apply:** Before any evidence clause of the form "X is validated by/in run N" or "run N passed with Y": run `jq '.decided_params.tg_rates_K_per_ns' data/<N>/raw/run_plan.json` and `jq '.slope_gate_pass' data/<N>/raw/tg_multirate_result.json`. If it confirms, keep it; if you can't confirm (or it contradicts), soften to "polymer_rules.json default for <CLASS>" and state the physics reason (e.g. r100=200 ps/T clears the r400 rigid-aromatic artifact) instead. The slope-gate hard-stop is the real downstream safety net — lean on that, not on prior-run lore. See [[psfo-reasoned-plan]].

Minor (immaterial): rdkit was unavailable in the planner bash env for the D-08 atom-count one-liner; skipped it since the ~11.4k estimate from psfo memory is >10k either way → 1 GPU regardless. Not worth resolving.
