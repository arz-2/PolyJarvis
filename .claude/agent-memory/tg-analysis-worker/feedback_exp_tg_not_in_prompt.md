---
name: feedback_exp_tg_not_in_prompt
description: experimental_tg_K must be in task prompt; sandbox denies access to polymer_rules.json
metadata:
  type: feedback
---

**Rule:** orchestrator/gen_prompt must supply `Tg_exp_K` (polymer-specific, not class-average) in the task prompt. When absent, report `Tg_exp_K: N/A (not supplied in prompt)` and `Tg_status: N/A`, then note the omission in the RESULT.

**Why:** worker sandbox cannot read `guides/polymer_rules.json` (outside allowed context). Attempting to fetch the value indirectly adds friction and creates opportunities for the worker to report stale/wrong class-averages (known bug in gen_prompt circa 2026-06-11, see [[feedback_genprompt_exp_tg_avg_bug]]). The only reliable source is the prompt itself.

**How to apply:** if `Tg_exp_K` missing from task prompt and you get denied access to polymer_rules.json, emit N/A + request in notes. Do not try alternative read/bash routes — they will also be denied. Do not guess or substitute a remembered value — that violates [[feedback_polymer_rules_sim_sourced_exp_bounds]].
