---
name: feedback_born_nonstationarity
description: Block-K values growing in magnitude over production window = non-stationary glass; fluctuation-dominated Born K diagnostic
ingested_at: 2026-06-20
metadata:
  type: feedback
---

When Born+NVT K_T is negative or far outside physical range, check block-K time evolution before investigating column order or formula bugs.

**Why:** Born+NVT K = K_Born + NkT/V - (V/kT)*Var(P). If the glass is non-stationary (aging, drifting), pressure variance grows over the production window, making fluctuation correction dominate. Block-K values growing in magnitude (e.g., [-19, -18, -18, -29, -25]) confirm non-stationarity — a genuinely converged glass gives stationary block values. Column order in born_matrix.dat (verified via header: TimeStep b11 b22 b33 b12 b13 b23) is not the issue in this case.

**How to apply:** If Born K is unphysical: (1) Check block_averaging.block_K_GPa_values in bulk_modulus_born.json. (2) If values grow in magnitude → non-stationary glass, root cause is upstream (failed equil, under-density). (3) Deform fallback is the correct recovery path, not re-running extract_bulk_modulus_born with different eq_fraction. (4) Report Born K as FAIL with unphysical flag and note root cause.
