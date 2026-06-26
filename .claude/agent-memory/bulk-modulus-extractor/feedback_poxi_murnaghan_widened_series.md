---
name: poxi-murnaghan-widened-series-success
description: "PEG4 (POXI) widened Murnaghan pressure series [-1000,0,3000,7000,15000] atm successfully resolved B0'=8.96 (no clamp); V(P) smooth, R²=0.9997"
metadata:
  type: feedback
---

For **rubbery POXI (PEO/PEG)** at 300 K, the widened Murnaghan pressure series
`[-1000, 0, 3000, 7000, 15000]` atm (reaching ~1.52 GPa) successfully resolved
EOS curvature that the narrow PEG3 series `[1,100,300,600,1000]` atm could not.

**PEG4 results:** B0 = 3.498 GPa, B0' = 8.96, R² = 0.9997, fit_converged=True.
The B0' = 8.96 is physically reasonable (expected [4–20] for soft melts); PEG3
had B0' collapse to the 1.0 lower clamp on the narrow series.

**Vitrification kink check:** dV/dP ratios at successive intervals (2.26 → 1.67 →
1.71) show smooth, monotonic stiffening — no discontinuity. vol_std decreases
monotonically (321 → 134 Å³). High-P points (7000/15000 atm) likely sample a
partially vitrified state but the EOS transition is continuous. R²=0.9997 rules
out any phase-transition kink.

**Fluctuation cross-check:** B_dyn = 3.216 GPa (NPT production log, 1001 frames),
within 8.5% of Murnaghan B0. Note B_def (P vs ln V slope) returned R²=0.035 —
expected for rubbery melts with large B0'; B_dyn is not biased here because the
vol_std=298 Å³ is large and the production run is well-equilibrated.

**Why:** both K values fall within exp range [2.0, 4.0] GPa (Murnaghan=3.50,
fluctuation=3.22). The widened series is the correct route for POXI when
Murnaghan is required; use [-1000, 0, 3000, 7000, 15000] atm as default.

**How to apply:** When POXI Murnaghan B0' was previously clamped at 1.0 (narrow
series), retry with the widened 5-point series above. Check V(P) kink in
dV/dP ratios; if ratio jump >3× at any interval, flag vitrification and report
only low-P points. If R²>0.999, trust the full-range fit.

Related: [[rubbery-murnaghan-vitrification-ceiling]], [[pvc-murnaghan-tension-cavitation]]
