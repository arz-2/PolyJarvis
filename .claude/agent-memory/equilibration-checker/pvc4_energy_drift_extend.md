---
name: pvc4-energy-drift-extend
description: PVC4 equil-check D-05 EXTEND verdict; energy drift 5.55% (p=0.0005) exceeded threshold; density excellent 1.3496±0.0078 g/cm³
metadata:
  type: feedback
---

**Root cause:** PVC4 npt_prod300 stage (1.0 ns) showed energy drift 5.55% over the production window, failing the hard gate (threshold <1%, p<0.01). Density convergence was excellent (0.1096% drift, PASS; block-SEM 0.0909%, PASS) and spatial checks passed (P2=0.027, density CV=18.5%), but energy trajectory is not plateau — indicates sub-equilibrated thermal degrees of freedom.

**Why:** Short production window (1 ns) after 8-stage equilibration may be insufficient for glassy PVC at 300 K to fully relax; energy is still in transient decay phase. This is not a structural failure (density is stable; no box collapse or charge issues), so EXTEND is appropriate per the guide.

**How to apply:** Orchestrator will spawn extend_mode="npt_extend" from npt_prod300_out.data with extend_ns=1-2 at same temp (300 K) and pressure (1.0 atm). Re-check after extension. If energy drift persists >2%, escalate (FAIL).

**Density verdict:** Extracted density 1.3496 g/cm³ is in excellent agreement with prior PVC runs (PVC2: 1.349, PVC3: 1.344) and experimental range (1.38 ± 0.04). No density anomaly flagged.

**Chain dynamics (advisory, non-blocking):** MSID slope 1.209 (Gaussian tolerance 1.0±20% ≈ 0.8–1.2) is borderline high, suggesting slight non-Gaussian chain behavior — normal for glassy PVC at short timescale. C(t) decay 16% at trajectory end (τ_relax=14.4 ns >> 0.95 ns traj) is expected for glassy systems below Tg; not a convergence failure.
