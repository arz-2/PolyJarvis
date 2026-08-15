---
name: success-criteria-contradict-gating-path
description: validate_run_plan.py never cross-checks planned_stages[].success_criteria against the gating path D-05 selected — a require_glassy/require_rubbery plan that still asserts overall_pass=true is a real finding the script scores 0 on
metadata:
  type: feedback
---

When D-05 adopts `require_glassy` (glassy DP>=30 **or** class `ct_gate_reliable=false`, e.g. PSFO/PKTN)
or `require_rubbery`, check `planned_stages[equil].success_criteria` by hand. A plan that still
asserts `check_equilibration_comprehensive.overall_pass: true` is gating on a boolean
`decision_policy.json:policies.equilibration.rationale_glassy` calls "unsatisfiable by construction"
for that class. The fix to demand is the gating set as machine-readable companions — density plateau
in band, `density_homogeneity_signal_cv_max` 0.11, P2 < 0.10, `n_eff_density` >= 20, energy
drift/SEM — with the advisory metrics (C(t)/MSD/MSID/Rg CV) named as non-blocking.

**Why:** PSU1 round 1 (2026-08-13). `validate_run_plan.py` returned `{"findings": [], "count": 0}`
on a plan whose equil stage contradicted its own D-05 evidence in the next paragraph. The script does
stage schema + loose stage-vs-`properties` coverage, not semantics; nothing in it reads which
`require_*` branch a decision selected. Same shape one stage later:
`equil-check.success_criteria.equil_verdict: "PASS"` next to a prose exception is the PMMA1 pattern
in [[plan-annotations-never-reach-worker-prompts]].

**How to apply:** a clean validator run is the start of the review, not the end. The three semantic
cross-checks worth doing every time: (1) success_criteria vs the `require_*` branch D-05 picked,
(2) success_criteria vs any exception D-06/D-07 prose grants, (3) operational instructions
("dumps disabled", "assert atom count") that exist only in a stage `note` — those bind no worker.
Spend the bounce at round 1; round 2 has no defined round 3.
