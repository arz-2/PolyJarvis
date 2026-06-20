---
name: project_pmma4_born_failure
description: PMMA4/PACR/PCFF Born+NVT gave K_T=-21.9 GPa (unphysical); root cause failed equilibration + under-density; block-K worsens
ingested_at: 2026-06-20
metadata:
  type: project
---

PMMA4 Born+NVT K_T = -21.898 GPa (unphysical, negative). K_Born=79.67 GPa but fluctuation correction=101.99 GPa dominated.

**Why:** Upstream equilibration failed (kinetic trap at 550 K, density homogeneity CV=25.8% > 25% threshold, C(t) never decayed). Under-dense config (1.119 g/cm3 vs exp [1.145, 1.265]) was fed to NVT Born run. Under-dense, non-stationary glass has inflated virial pressure fluctuations (P_std=889 atm).

Key diagnostic: block-K values `[-19.0, -17.9, -17.9, -28.7, -25.3]` — growing in magnitude over production blocks = non-stationary, not converged. A converged glass would show stationary block values.

**How to apply:** If Born K_T is negative and the fluctuation correction exceeds K_Born, check block-K time trend first. Growing-magnitude block-K = non-stationarity from failed upstream equilibration, not a formula/column-order bug. Fix requires re-equilibration or density correction before re-running born-worker. Deform fallback is the recovery path (see [[feedback_born_nonstationarity]]).
