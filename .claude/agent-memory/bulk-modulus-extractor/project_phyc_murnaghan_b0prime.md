---
name: project_phyc_murnaghan_b0prime
description: TraPPE-UA PE at 300 K shows B0'~13.5 (high nonlinearity); B_def cross-check unreliable (R²<0.05)
ingested_at: 2026-06-20
metadata:
  type: project
---

PE1 (PHYC, TraPPE-UA, 300 K, 5-pressure Murnaghan series 1–1000 atm):
- B0 = 1.46 GPa, B0' = 13.46, r² = 0.9996 (fit converged cleanly)
- B_def cross-check R² = 0.049 — the P vs ln V relationship is highly nonlinear; B_def is unreliable
- B_dyn (fluctuation) = 1.59 GPa — reasonable agreement with Murnaghan (8% difference)
- vol_std ~ 540–590 Å³ across pressures, monotonic V(P) confirmed

**Why:** Soft rubbery melts like PE show high pressure derivatives (B0'~7–15 is normal); the Murnaghan EOS handles this correctly. B_def assumes a linear ln V vs P relationship which breaks down at high B0'.

**How to apply:** For PHYC (and likely PDIE) rubbery polymers, always use Murnaghan multi-pressure path. The B_def diagnostic will likely fail (low R²) — this is expected, not an error. The warning in bulk_modulus.json about B_def unreliability is correct and should be passed through to the orchestrator.
