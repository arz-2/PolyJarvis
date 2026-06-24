---
name: pvc-pvnl-murnaghan-b0prime-high
description: PVNL (PVC) PCFF Murnaghan: ±1000 atm gives B0'~16 (too high); widened span [-1000,0,1500,3000,5000] atm gives B0'=9.5, R²=0.9990, K=2.80 GPa — still ~30% below exp 4.0 GPa (PCFF systematic underprediction)
metadata:
  type: project
---

**PVC2 run** (PVNL, PCFF, 300 K glassy): Murnaghan on ±1000 atm gives B0'=16.34, R²=0.9979, K=2.91 GPa.

**PVC3 run** (PVNL, PCFF, 300 K glassy): Widened span [-1000, 0, 1500, 3000, 5000] atm. B0'=9.53 (within [4,20]), R²=0.9990 (just below 0.999), K=2.80 GPa. B_dyn=2.93 GPa (fluctuation cross-check, 4.6% agreement with Murnaghan). Both values are ~30% below exp [3.5, 4.5] GPa.

**Why:** PCFF systematically underpredicts PVC bulk modulus (~30% deficit) independent of pressure span. The narrow ±1000 atm span also inflates B0' (16→9.5 after widening), confirming pressure range was a fit artifact. The K value itself remains consistent across span widths (2.91 vs 2.80 GPa) and methods (Murnaghan vs fluctuation).

**How to apply:** For PVNL/PCFF bulk modulus, expect K ~2.8–2.9 GPa (vs exp 4.0 GPa). Always use span ≥ [-1000, 5000] atm to keep B0' in [4,12]. Widening further is unlikely to fix the ~30% FF underprediction — consider flagging PCFF as inappropriate for quantitative PVC K, or note as a known systematic. B0'~9.5 is physically reasonable for glassy PVC at 300 K. R²~0.999 borderline is acceptable for 5-point compression-biased series.

Related: [[project_pstr_murnaghan_b0prime]]
