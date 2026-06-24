---
name: pvc2-degenerate-multirate
description: PVC2 (PVNL) exhibits degenerate bilinear Tg fits across all cooling rates (40, 160, 400 K/ns); density drift and undersampling pattern suggests NPT production inadequacy
metadata:
  type: project
---

## Observation (2026-06-23)

PVC2 cooling rates r40, r160, r400 all show the same pathology:
- **n_plateaus_skipped_drift: 88–100%** (density drift > 1% threshold)
- **n_plateaus_low_n_eff: 100%** (all plateaus undersam pled; relax_warning flags)
- **transition_width_c_K > 20** (degenerate signature)
- Tool falls back to Tg_alternative = input guess (354 K)

### Fitted Tg values (unreliable):
- r40:  271 K → alt=354 K
- r160: 271 K → alt=354 K
- r400: 271.6 K → alt=354 K

## Root Cause

Not a fitting problem. NPT production at each temperature-hold is **undersized or underthermalized**:
- Density plateaus reach only n_eff ~ 3–50 at most temperatures (target: n_eff > 20)
- Autocorrelation time >> equilibration burn-in fraction (0.5)
- Drift filtering removes most points

## Action

Exclude all three rates from multirate registry. Report status as **FAIL** with recovery note: _"NPT production time insufficient; all rates show < 5 K-eff at > 80% of T-holds. Extend NPT production duration in equilibration template, re-equilibrate, and rerun thermal track."_

## Experimental Reference

PVC literature Tg range: 354–358 K (PVNL class nominal). The alternative fallback (354 K) happens to match experiment — do NOT trust this as a result.
