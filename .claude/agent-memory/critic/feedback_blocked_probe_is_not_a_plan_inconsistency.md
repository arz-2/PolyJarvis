---
name: blocked-probe-is-not-a-plan-inconsistency
description: A dominant uncertainty naming reduction_probe fast_density_screen (or hardware_benchmark) with no probe stage scheduled is policy-prescribed, not a contradiction — decision_policy.json says record it as planned, not executed
metadata:
  type: feedback
---

Do NOT flag "uncertainty declares a `reduction_probe` but the plan schedules no probe stage" as an
inconsistency. `decision_policy.json:uncertainty_reduction_probes.fast_density_screen.mechanism`
says verbatim: *"(ROADMAP E3, currently BLOCKED on A1/A2 — record as planned, not executed, until
unblocked)"*. `hardware_benchmark` is likewise routinely carried as planned-not-executed when the
plan keeps a `by_forcefield` default rather than pinning a deviation.

**Why:** raised as a suspected contradiction on cis-PBD1 (2026-08-11). The probe is named so the
uncertainty is *addressable later*, not so a stage runs now; `validate_run_plan.py` checks only
that the probe name is a valid key, and correctly returns no finding.

**How to apply:** confirm the named probe is a real key under
`decision_policy.json:uncertainty_reduction_probes`, then state in `findings` that the
named-but-unscheduled probe is deliberate and cite the BLOCKED/planned-not-executed wording.
Also note there is usually no top-level `probe` key at all in the plan schema — `jq .probe`
returning `null` means *absent*, not *set to null*, so don't build a finding on that premise.

Related: [[critic-scope-blocks-default-source-checks]]
