---
name: rate-ladder-is-not-a-sweep-list
description: decided_params.tg_rates_K_per_ns is a configured ladder, not a list of sweeps to run — orchestrator prompts have described a single-rate plan as an "N-rate Tg ladder"; the binding value is planned_stages[tg].success_criteria.rate_swept_K_per_ns
metadata:
  type: feedback
---

A reasoned plan carrying `tg_rates_K_per_ns: [25,50,100]` schedules **one** sweep, not three.
`decision_policy.json:policies.tg_protocol.require` makes single-rate-primary the default and
calls multirate extrapolation (`extract_tg_multirate.py`, `select_tg_path.py`, the
`analyze-tg-multirate` stage) "a legacy/opt-in capability, not part of the default reasoned plan".
For classes with `tg_slope_gate_fallback="slowest_rate"` (PKTN, PSFO) the swept entry is
`tg_rates_K_per_ns[0]`, not the highest.

**Why:** on PEEK1 (2026-08-11) the orchestrator prompt asked the critic to judge cell cost against
"a 3-rate Tg ladder" while the plan under review was single-rate at 25 K/ns. 20 ns vs 35 ns is a
1.75x divergence in the exact quantity being judged; silently answering the prompt's framing would
have either bounced a sound plan or blessed an unauthorised 3x execution.

**How to apply:** resolve sweep count from the plan, never from the prompt's prose. The binding
field is `planned_stages[tg].success_criteria.rate_swept_K_per_ns`; corroborate with the absence
of an `analyze-tg-multirate` stage. Then state it as an explicit finding so the executing
orchestrator inherits the correction. When wall clock is the real constraint, the in-policy lever
is dropping the slowest ladder entry (rates[0]=50 still gives 400 ps/bin, 2x the 200,000-step
floor) — not shrinking the cell, which trades away MW convergence.

Related: [[critic-scope-blocks-default-source-checks]]
