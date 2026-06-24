---
name: pstr-murnaghan-b0prime-high
description: PCFF PS at 300 K (glassy) gives B0'~13.5, high but within [4,20]; B0=2.44 GPa below exp [3.3,4.0] due to short DP (screening grade)
metadata:
  type: project
---

PCFF PSTR (polystyrene PS2) Murnaghan fit at 300 K, ±1000 atm pressure span: B0'=13.47, B0=2.44 GPa, R²=0.9998, fit_converged=true. B_dyn=2.50 GPa (2.3% agreement) cross-validates the fit.

**Why:** B0' ~13.5 is high but physically plausible for PCFF PS glassy (comparable to TraPPE-UA PE B0'~13.5 seen in PHYC runs). The 26% underestimation vs exp [3.3–4.0 GPa] is explained by DP=40 << Me@160 — plan D-04/D-07 flags this as screening-grade.

**How to apply:** For PSTR Murnaghan runs, B0' in 10–15 range is normal for PCFF at ±1000 atm. Do not flag as anomalous — the fit quality (R²>0.999) and B_dyn agreement validate the result. Report as WARNING (below exp range) with screening-grade caveat, not FAIL. [[pvc-murnaghan-b0prime-high]]
