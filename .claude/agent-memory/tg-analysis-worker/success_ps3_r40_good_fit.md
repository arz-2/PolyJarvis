---
name: success_ps3_r40_good_fit
description: PS3 r40 sweep yields GOOD fit (R²=0.9918), Tg=376.5 K, within experimental range
metadata:
  type: feedback
---

## Run: PS3 (PSTR/aPS, PCFF)
**Rate:** 40 K/ns (slowest multirate point)

**Tg Result:**
- Tg_K: 376.5 (bilinear_curvefit, post-swap)
- R²: 0.9918 (GOOD fit quality)
- Tg_alternative: 380.9 K (hyperbola method, rejected as degenerate)

**Experimental validation:**
- Expt Tg range: 373–383 K (polymer_rules.json PSTR)
- 376.5 K: OK (within ±7 K of mid-point)

**CTE & ΔCp:**
- CTE_glassy: 0.000262 K⁻¹
- CTE_rubbery: 0.000473 K⁻¹
- ΔCp: 0.1557 J/(g·K) [GOOD H-fit, R²=0.9886]

**Plateau equilibration:**
- 35 usable bins, 127 bins skipped (drift >1% + n_eff <5)
- Most high-T plateaus flagged relax_warning=true (n_eff ~3–5), but lower-T glassy region well equilibrated (n_eff >100)
- Bilinear fit constraints enforced (slope signs, ordering valid)

**Key insight:** Primary fit (hyperbola) was physically invalid (degenerate transition_width) and was swapped to bilinear. This is a normal fallback; bilinear R² is excellent. The aromatic ring charge handling in PCFF PSTR appears sound for single-rate analysis.

**No recovery needed.** Run passes overall_verdict=PASS.
