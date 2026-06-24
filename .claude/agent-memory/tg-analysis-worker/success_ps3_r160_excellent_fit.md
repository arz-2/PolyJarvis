---
name: success_ps3_r160_excellent_fit
description: PS3 160 K/ns run achieved EXCELLENT fit (R²=0.9969) with clean bilinear plateau detection; Tg 377.5 K matches experiment (373–383 K). Template for PSTR success.
metadata:
  type: project
---

**Run:** PS3, rate 160 K/ns, PSTR (polystyrene)

**Tg outcome:** 377.5 K ± 21.4 K uncertainty; fit_quality=EXCELLENT (r²=0.9969).
Experimental range: 373–383 K → **OK (within ±5 K)**

**Why it worked:**
- Bilinear curve_fit converged cleanly (slope_signs_valid=true, slope_ordering_valid=true).
- 28 temperature bins across 200–600 K range; 19 bins skipped for density drift >1%.
- Relaxation metrics mostly healthy (only 8 plateau_warnings out of 43 for low n_eff).
- Good hyperparameter choice in extractorfor equilibration_fraction=0.5.

**How to apply:**
- PSTR builds with PCFF show strong bilinear transitions when plateaus have adequate equilibration (n_eff ≥ 5).
- If future PSTR multirate studies show inverted slopes or low r², check equilibration duration in NPT production, not extraction settings.
