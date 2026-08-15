---
name: plan-prohibitions-must-be-machine-effective
description: A "do not use X" written in plan prose reaches no worker — disarm the value in decided_params and verify the call chain (PLA1 critic round-1 blocking finding)
metadata:
  type: feedback
---

If the plan forbids a value, the prohibition must live in `decided_params`, not in `assumptions[]` or a stage `note`. Only `decided_params` reaches runtime (`gen_prompt.apply_plan`: `effective = {**cls, **decided_params}`, gen_prompt.py:129); every other field of `run_plan.json` is documentation that no worker prompt ever sees.

**Why:** PLA1 round 1 was blocked on exactly this. The plan said in two places that PEST's PET/PBT-derived `exp_K_GPa` [3.0,4.5] must not grade PLA — and it would have graded it anyway, because `_exp_K_range` reads `exp_K_GPa` off the plan-overlaid class dict and `decided_params` carried no such key. The archived PLA K (4.46–5.39 GPa) would have come back FAIL-high against a band the plan itself rejected.

**How to apply:**
- To suppress a class value, set the key to `null` in `decided_params`. Verify the reader is shape-guarded first: `_exp_K_range` (gen_prompt.py:291-295) returns `[None,None]` for anything that is not a dict with `min` and `max`, so `null` disarms cleanly. A key whose reader does `cls.get(k, default)` would instead need a different tactic.
- Then walk the whole chain and cite it in the decision evidence, because omission is handled differently at each hop: prompt resolver (CLI > DB > class) → worker `.md` ("pass only if both non-null") → MCP server (`if x is not None: parts.append(...)`) → the analysis script's own `default=None` branch. For K that terminates at `generate_run_summary.py:279-282` with `K_status = "no exp ref"`, which is the intended N/A.
- Leave any higher-priority evidence path INTACT and say so — nulling the class fallback must not suppress a real polymer-specific value that exp-lookup or the DB may supply.
- Same test for any other prohibition: if you can't name the line that reads the key, the prohibition is decorative ([[feedback-decided-params-can-be-decorative]]).

Related: [[pest-reasoned-plan]], [[glassy-stage-criteria-and-unknobbed-instructions]].
