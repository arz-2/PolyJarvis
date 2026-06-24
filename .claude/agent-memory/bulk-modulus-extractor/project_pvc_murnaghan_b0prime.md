---
name: pvc-pvnl-murnaghan-b0prime-high
description: PVNL (PVC) PCFF Murnaghan at ±1000 atm gives B0'~16, R²<0.999; K=2.91 GPa vs exp 4.0 GPa; B_dyn=2.71 GPa consistent; deform fallback warranted
metadata:
  type: project
---

PVC2 run (PVNL, PCFF, 300 K glassy): Murnaghan fit on ±1000 atm (±0.1 GPa) series gives B0_GPa=2.91, B0'=16.34, R²=0.9979, B_dyn=2.71 GPa.

**Why:** Narrow pressure span (±0.1 GPa) with high B0' inflates the pressure derivative and produces R²<0.999. K=2.91 GPa is ~27% below experimental 4.0 GPa, indicating possible PCFF underprediction or insufficient pressure range. B_dyn and Murnaghan K agree within 7.5%, so the value is internally consistent. Similar to PEST and PHYC narrow-span behavior (see [[project_pest_murnaghan_b0prime_narrow]], [[project_phyc_murnaghan_b0prime]]).

**How to apply:** For future PVNL Murnaghan runs, consider widening pressure span to ±2000–5000 atm to constrain B0' to a physically reasonable value (4–10 for glassy PVC). If B0'>15 persists, flag deform fallback. PCFF may systematically underpredict K for PVC; cross-check with literature PCFF PVC densities.
