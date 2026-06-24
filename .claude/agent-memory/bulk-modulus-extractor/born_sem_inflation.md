---
name: born-sem-inflation
description: Born+NVT SEM is inflated (>> K value) when K_Born and fluctuation correction nearly cancel; seen in PS1 (PSTR) at 300 K
metadata:
  type: project
---

In PS1 (polystyrene, PSTR, 300 K), Born+NVT gave:
  K_Born = 94.0 GPa
  fluctuation_correction = 90.6 GPa
  K_T = 3.85 GPa  (small residual of two large numbers)
  SEM = 4.18 GPa  (larger than K_T itself — meaningless uncertainty band)

Block values: [-12.9, 7.4, 4.9, 7.3, 10.5] GPa — high block variance from pressure fluctuation noise.

**Why:** The stress-fluctuation correction (V/kT)*Var(P) is ~90 GPa for PS at 300 K. K_T = K_Born - Var(P)*V/kT + NkT/V. Both leading terms are ~94 GPa, so the result is a small difference of large numbers. Block variance in Var(P) propagates into a huge SEM.

**How to apply:** When bulk_modulus_sem_GPa > bulk_modulus_GPa from Born+NVT, flag the uncertainty as unreliable. Report K_T = 3.85 GPa with a note that SEM is inflated due to cancellation. The point estimate is still physically reasonable for glassy PS (exp 3.5–5.5 GPa). Cross-check against fluctuation K from NPT (2.71 GPa) confirms the Born K is within expected range.

Also: tool issues warning "Fluctuation correction >50% of K_Born" — this is the diagnostic signal.

[[born-vstd-zero]]
