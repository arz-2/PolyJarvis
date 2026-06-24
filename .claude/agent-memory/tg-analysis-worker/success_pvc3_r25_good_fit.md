---
name: pvc3_r25_good_fit
description: PVC3 r25 (slowest rate): GOOD fit (R²=0.9845), Tg 310.6 K; primary fit swap (hyperbola → bilinear)
metadata:
  type: project
---

PVC3 r25 K/ns (rate index 0, slowest/most-equilibrated of [25,50,100]):

**Result summary:**
- Tg_K: 310.6 K
- Tg_alternative_K: 282.0 K (primary hyperbola fit, deemed degenerate)
- R²: 0.9845 → GOOD fit_quality
- Fit method: bilinear_curvefit (swapped from primary invalid hyperbola)
- Primary fit invalid: false (swap was legitimate)
- Transition width: null (hyperbola was degenerate)
- n_temperature_bins: 52 clean plateaus

**Why:**
Primary hyperbola fit gave Tg_alt = 282.0 K but width_c → null (degenerate transition); slopes valid but the curved parameterization collapsed. Bilinear fit is physically valid and recovers Tg = 310.6 K with R² = 0.9845, matching multirate trend (r100 = 284 K, r50 = 267.6 K). Lower rates → higher Tg is expected (more equilibration time at each T).

**CTE & ΔCp:**
- α_glassy: 0.000257 K⁻¹
- α_rubbery: 0.000530 K⁻¹
- α_r / α_g: 2.06 (normal, within 1.5–5)
- ΔCp: 0.2785 J/(g·K), H_r² = 0.9796 (ACCEPTABLE enthalpy fit)

**Tg vs experimental:**
PVC expt Tg ≈ 354 K. PVC3 r25 Tg = 310.6 K → −43.4 K underprediction. Consistent with PVC2/PVC3 pattern (PCFF underpredicts Tg by ~13–15% for PVC). Multirate Tg_0 (VF extrapolation to DSC rate) will refine this.

**Data quality notes:**
- 305 plateaus skipped for drift > 1%; 283 for n_eff < 5 (high attrition, expected for undersampled sweep)
- Temp range [150, 560] K, 52 accepted bins → sufficient coverage
- No fit warnings beyond the primary-swap note
- Equilibration fraction 0.5 is standard

**Verdict:** GOOD fit. Tg reportable with caveat on PVC underestimation. Move to multirate aggregation for Tg_0.
