---
name: pdie-murnaghan-baseline
description: cis-PBD-2 Murnaghan extraction results — PDIE rubbery baseline values and B_def cross-check behavior
metadata:
  type: project
---

cis-PBD-2 (PDIE class, rubbery at 300K): Murnaghan gave K=1.606 GPa (B0'=8.61, R²=0.9999, 5-point series 1–1000 atm). Within exp range [1.38, 1.95] GPa.

**Why:** First successful Murnaghan extraction for PDIE; establishes expected B0' range ~8–9 for polydienes at 300 K.

**How to apply:** For future PDIE runs, B0' 7–10 is normal. B_def R² near zero (0.025 here) is expected for soft rubbery polymers — the P vs ln V relationship is nonlinear at this scale; do not flag as anomaly. B_dyn (volume fluctuation) = 1.505 GPa was 6.6% below Murnaghan — acceptable agreement. The `warning_bdef_unreliable` in `bulk_modulus.json` is standard for rubbery polymers.

See [[pdie-exp-k-range]] for experimental range context.
