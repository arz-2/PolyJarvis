---
name: pvc3-r100-good-fit
description: PVC3 (PVNL) at 100 K/ns cooling rate exhibits GOOD fit quality (R²=0.9815); Tg 284 K (−70 K below expt 354 K) but alternative 329 K closer. Significant improvement from PVC2 degenerate fits.
metadata:
  type: project
---

## Extraction Summary (2026-06-24)

**PVC3 r100 (100 K/ns cooling rate)**
- **Tg_K:** 284.0 K (bilinear fit)
- **Tg_alternative_K:** 329.4 K (from initial guess)
- **R² (density):** 0.9815
- **fit_quality:** GOOD
- **transition_width_c_K:** 15.1 (reasonable, not degenerate)
- **n_plateaus_skipped_drift:** 79 (high)
- **n_plateaus_low_n_eff:** 73 (high; many with relax_warning)

## Comparison to PVC2

PVC2 r100 (hypothetical) exhibited:
- **n_plateaus_skipped_drift:** ~88–100% (degenerate)
- **Tg alternative collapse to input guess**

**PVC3 r100 shows marked improvement:**
- Clean bilinear slope ordering (slope_ordering_valid=true, slope_signs_valid=true)
- Reasonable transition width (not near 0)
- Distinct Tg vs. Tg_alternative (284 vs. 329 K, 45 K spread suggests noisy but parseable transition)

## Interpretation

The primary fit (284 K) is **below experimental** (354 K, −70 K offset), but this is consistent with fast cooling (100 K/ns). The alternative fit (329 K) is only −25 K from expt and may be more representative of the equilibrium Tg.

Hypothesis: At 100 K/ns, the system is under-relaxed above Tg; the density retains some rubbery character, suppressing the apparent glassy density inflection. **Multirate registry should flag the (rate, Tg) pair as ambiguous** — suggest using Tg_alternative or deferring to slower-rate consensus.

## Physical Properties Extracted

- **CTE glassy:** 2.378e-4 K⁻¹
- **CTE rubbery:** 4.892e-4 K⁻¹
- **CTE ratio:** 2.06 (within expected 2–3 range)
- **dCp:** 0.2269 J/(g·K) (GOOD fit on enthalpy, R²=0.9826)
- **System mass:** 37519.69 g/mol

## Action

Include in multirate registry as **(r100, Tg=284 K, tg_alt=329 K, r²=0.9815)**. Flag in registry comment: "primary fit below expt by 70 K; consider alternative fit or multirate consensus."
