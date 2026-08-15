---
name: grounding-vs-rules-conflicts
description: literature_grounding.json can contradict polymer_rules.json and can hide its best-looking numbers behind verified=false — how to arbitrate (PSU1, 2026-08-13)
metadata:
  type: feedback
---

When a run is grounded, arbitrate `literature_grounding.json` against `polymer_rules.json` field by field instead of adopting the grounding wholesale. Three failure modes seen on PSU1:

1. **`verified: false` on exactly the numbers you want.** `density_target_gcm3` [1.24,1.25] and `tg_target_K` [458,460] were both unverified (the only PSU-specific MD paper, Fan & Hsu 1992 `10.1021/ma00027a044`, resolves via CrossRef but is ACS-paywalled). They sit within a hair of the in-repo values, which is what makes copying them feel safe. Pin the in-repo values instead (PSU 463 K, 1.24 g/cm3) and say in `assumptions[]` that the unverified grounding fields were excluded.
2. **`notes_only` prose can be flat-out wrong for the chosen FF.** Grounding's electrostatics note asserted sulfone S ~ +1.3 e / O ~ -0.55 e; `polymer_rules.json:classes.PSFO.notes` states those are OPLS/QM magnitudes and that native PCFF bond increments are S ~ +0.08 / O ~ -0.11, with exactly 0.0000 meaning a MISSING increment. `notes_only` carries no `verified` flag at all — treat it as unsourced.
3. **Null `cte_glass_melt` is not an instruction to delete the class alphas.** planner.md's "leave both keys unset" means don't fabricate from absent grounding; the scaffold's `alpha_glass_per_K`/`alpha_melt_per_K` (Mark 2007 density(T) derivation) must stay, or `density_value_binding` falls back to generics that run 1.5-2 pp low and bias the diagnosis toward blaming the force field.

**Why:** grounding is advisory evidence produced by a worker that never sees the rules file, so it can duplicate, contradict, or under-verify what the repo already holds with a better provenance note.

**How to apply:** adopt a grounding recommendation only where it is `verified: true` AND either adds something the rules lack or beats the rules' provenance. On PSU1 that was exactly one field: `system_size.nchain=20` (Bejagam2020 `10.1039/D0CP03163A`, verified) — adopted, while its companion `dp=40` was declined because `L/2Rg ~ nchain^(1/3) * dp^(-1/6)` makes larger dp WORSEN the binding finite-size gate. Also: once a run is grounded, `literature_anchor` is a SPENT probe — never name it as the dominant uncertainty's `reduction_probe` in the same plan.

See [[psfo-reasoned-plan]], [[planner-scope-denials]].
