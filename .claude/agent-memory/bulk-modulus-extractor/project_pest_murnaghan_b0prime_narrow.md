---
name: project_pest_murnaghan_b0prime_narrow
description: PEST/PLA Murnaghan B0'=1.0 collapse when pressure span is only ±0.1 GPa (±1000 atm); K value still reliable, corroborated by fluctuation cross-check
ingested_at: 2026-06-22
metadata:
  type: project
---

PLA1 (PEST, PCFF, 300 K, 5-pressure Murnaghan series ±1000 atm = ±0.1 GPa):
- B0 = 4.58 GPa, B0' = 1.00, R² = 0.9999 (fit converged but B0' hits lower bound)
- Fluctuation B_dyn = 4.54 GPa — excellent agreement (0.8% difference), strongly corroborates K
- B_def R² = 0.023 — unreliable (EOS nonlinearity or noise at narrow span)
- exp_K_range = [3.0, 4.5] GPa; result is marginally above upper bound by ~0.08 GPa

**Why:** The Murnaghan EOS cannot resolve B0' from a ±0.1 GPa pressure window. B0' collapses to 1.0 (the lower parameter bound) because the P(V) curve is nearly linear over such a small range — the fit is insensitive to the pressure derivative. The K value (B0) itself is still accurate: it is set by the slope at V0, which is well-constrained even at narrow span. The fluctuation cross-check (B_dyn=4.54 GPa) independently confirms this.

**How to apply:**
- For PEST (and likely other glassy PCFF polymers) where the murnaghan-worker uses ±1000 atm, expect B0'=1.0 warning. Do not flag this as a fit failure — treat it as a known narrow-span artifact.
- Report K from Murnaghan B0, corroborated by B_dyn. Status = WARNING if outside exp_K_range.
- For more accurate B0', the murnaghan-worker should use ±5000 atm (±0.5 GPa) or wider for glassy PCFF polymers. Flag this as a future improvement for the planner.
- PLA experimental K ~ 3–4.5 GPa; PCFF may slightly overestimate for glassy polyesters.
