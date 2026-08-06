---
name: feedback-dangling-uncertainty-citation
description: Never write decision evidence that names an uncertainties[] entry as its safety net without adding that entry in the same edit — verified by critic round 1 on PVDF1
metadata:
  type: feedback
---

When a decision's `evidence` prose says "this risk is recorded/folded into `uncertainties[]` as `<name>`, so it's OK not to pre-emptively fix it now," that citation must be TRUE at the moment you write it — add the matching entry to `uncertainties[]` (with the same 4-field shape the other entries in the plan use: `name`, `dominant`, `reduction_probe`, `note`) in the same pass, not as a follow-up.

**Why:** PVDF1's D-06_tg_ladder evidence justified keeping a 0.602-decade Tg rate span by citing a `tg_rate_span_slope_gate` uncertainty as the safety net — but that entry didn't exist in `uncertainties[]` (only `ff_transferability`, `glassy_rubbery_regime_ambiguity_300K`, `hardware_optimum` were present). Critic round 1 caught it as a blocking finding: "the safety net cited as the reason NOT to pre-widen is not actually armed." The underlying physics/numbers were fine (critic independently recomputed the steps-per-hold and agreed) — this was purely a self-consistency gap between prose and structured data.

**How to apply:** before finalizing any reasoned plan, grep every decision's `evidence[].claim`/`.note` text for uncertainty names you reference, then `jq '.uncertainties | map(.name)'` the plan and confirm every referenced name is actually present. Do this as a final pass, not just when writing each decision, since it's easy to write the citation sentence first and forget the array entry (or vice versa — reference the wrong/renamed uncertainty after an edit).

Same root-cause class as a related but distinct issue: D-06's `criteria_evaluated` must literally match `decision_policy.json:policies.<decision>.evaluate`'s key list, not a free-text paraphrase of it — the critic checks for coverage by exact key membership, not semantic equivalence. See [[phal-reasoned-plan]] for the concrete PVDF1 case.
