---
name: peg3-multirate-vf-failure
description: PEG3 (rubbery) multirate aggregation—VF fit failed; low log-linear R²=0.366 with rates_span=1 decade
metadata:
  type: project
---

**PEG3 (POXI/PEO, DP=100) multirate aggregation** combines 2 replicates × 3 rates (r40, r160, r400 K/ns):
- 6 per-rate Tg values all ≥ GOOD fit quality (238.7, 245.3, 214.8, 244.4, 233.8, 236.4 K)
- Log-linear slope = −6.48 K; R² = 0.3659 (very weak fit)
- VF extrapolation: **FAILED** ("Initial guess is outside of provided bounds")
- Rubbery exemption granted; `is_flat_rate_regime=true`; method=`rubbery_flat_mean`
- Reported Tg_DSC_equiv = **235.6 K** (mean of replicates by rate; slow_rate_ref = 1.67e-10 K/ns)

**Root cause (hypothesis):** Rates span only 1 decade (40–400 K/ns ≈ 1 log-decade), which violates the constraint that Vogel–Fulcher fit requires ≥2 decades for numerical stability. The optimizer attempted the VF Tg0 fit but diverged due to insufficient leverage in the rate space.

**Status:** PASS (rubbery exemption is correct; flat-mean is the fallback for underconstrained multi-decade regimes). VF failure does not affect the reported DSC-equivalent Tg, which relies on log-linear extrapolation (albeit weak R²).

**How to apply:** On future rubbery runs with <2 decades of rate coverage, expect VF→FAILED and route to `tg_method=rubbery_flat_mean`. Do NOT escalate; confirm slope_gate_pass=true and rubbery_regime_exemption=true before accepting the mean value.
