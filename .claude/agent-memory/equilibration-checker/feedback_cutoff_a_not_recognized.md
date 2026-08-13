---
name: cutoff-a-not-recognized-in-comprehensive
description: check_equilibration_comprehensive ignores cutoff_A parameter; finite_size.cutoff_A and L_over_2cutoff always null
metadata:
  type: feedback
---

**Rule:** When passing `cutoff_A` to `check_equilibration_comprehensive`, the tool does not populate `finite_size.cutoff_A` or `finite_size.L_over_2cutoff` in the output JSON — both remain `null`. The tool still evaluates the `2·Rg` criterion but skips the minimum-image check `L ≥ 2·cutoff_A`.

**Why:** During PEGORE1 equilibration check, I passed `cutoff_A=9.5` explicitly per the prompt guidance and guide requirements. The tool returned `finite_size.cutoff_A: null` and `L_over_2cutoff: null`, with an unarmed flag `min_image_evaluated: false`. The reason string claims "no cutoff_A supplied" even though it was in the call signature. The finite_size verdict still passed (based on `L ≥ 2·Rg` alone), but the minimum-image half of the gate was not evaluated, leaving a gap in the structural assessment. The enforce_equilibration_gate also received the same `finite_size_min_image_unarmed: true` and did not flag it as a failure, treating the partial gate as acceptable.

**How to apply:** When reporting finite_size results, note whether min_image was actually evaluated by checking `min_image_evaluated` in the tool output. If false, add a warning that cutoff_A validation was skipped. Do NOT re-derive or override the finite_size verdict; the tool handles this, but document the asymmetry in the RESULT block.
