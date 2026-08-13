---
name: plan-annotations-never-reach-worker-prompts
description: decided_params._* annotation fields and decisions[].evidence prose reach no worker prompt — a plan "MUST annotate" requirement only binds via planned_stages[].success_criteria companions
metadata:
  type: feedback
---

Prose obligations a plan places on downstream stages ("K MUST be reported with the density-deviation
annotation") bind nothing unless encoded as machine-readable keys in
`planned_stages[<stage>].success_criteria`. Verify, don't assume:
`gen_prompt.py --stage murnaghan|analyze-bm|run-summary --plan <plan>` and grep the render for the
annotation text — custom `decided_params._*` keys merge into gen_prompt's `effective` dict but are
rendered by no template — and grep `.claude/agents/<worker>.md` for `run_plan`: analysis/summary
workers do not read the plan file at all.

**Why:** PMMA1 rung-3 (2026-08-11) accepted a -5.40% density and made the K/density annotation the
entire mitigation. Rendering all three downstream stages produced zero mentions of it. The working
pattern already in the repo is the PVC1 companion field: `planned_stages[tg].success_criteria.exp_tg_K`
sits next to the gate threshold precisely so a worker sees it.

**How to apply:** when a plan accepts a documented gate exception, require (a) companion keys on
every stage that must carry it, and (b) that the *stage schema itself* stop asserting the thing the
exception contradicts — PMMA1 still had `equil-check.success_criteria.equil_verdict: "PASS"` while
D-05's prose said "NOT a pass". There is no `STRUCTURAL_FAIL_ACCEPTED_EXCEPTION` vocabulary in
`decision_policy.json:gate_classes.verdict_vocabulary` yet; that gap is the underlying friction.
Both items are execution-neutral (nothing changes what is submitted), so at `critic_round == 2`
prefer approve-with-binding-findings over `revise` — the loop has no defined round 3 and a bounce
risks UNRESOLVED on a human-authorized run. See [[glassy-tg-sweep-starts-from-glass-cell]].
