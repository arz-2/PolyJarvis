---
name: tg-ladder-steps-floor-arithmetic
description: always recompute the tg_rates steps-per-T floor yourself; planners have mis-stated 100 ps as clearing the 200 ps floor (PVC4 D-06)
metadata:
  type: feedback
---

When critiquing a reasoned D-06 tg ladder, independently recompute the steps-per-T floor for EVERY rate — never trust the decision's prose arithmetic.

**Formula (tg_protocol.require[2]):** `N = tg_t_step_K / (rate_K_per_ns * dt_fs * 1e-6)`. Floor = 200000 steps = 200 ps at dt=1fs (TraPPE-UA dt=2fs → floor 100000). A rate PASSES only if N >= 200000.

**Why:** PVC4 (PVC/PVNL) D-06 proposed [12.5,25,50,100,200] K/ns to widen the slope-gate span past PVC3's failed 0.6 decades. The top rate 200 K/ns gives N=20/(200*1e-6)=100000 = 100 ps/T-hold, which is BELOW the 200 ps floor — yet the decision's own evidence asserted "200 K/ns = 100 ps/T-hold; both clear the steps-per-T floor". 100 ps does NOT clear a 200 ps floor. This is the exact degenerate-fit regime the policy warns about (retired [40,160,400] gave 50/125 ps degenerate fits). The planner conflated the floor (200 ps) with the rate's actual hold (100 ps). Caught as a HARD require violation → revise.

**How to apply:** Run the floor arithmetic in a quick python loop for every rate in tg_rates_K_per_ns. The widest-span temptation (a fast top rate) is exactly where the floor gets violated — scrutinize the FASTEST rate hardest. Don't confuse `tg_steps_per_t` (a separate per-T equilibration-steps field, e.g. 500000) with the cooling-rate-derived hold N; the floor check is rate-driven only. Note the tg-span tension: dropping the fast rate narrows the decade span the planner was trying to widen, so suggest BOTH fixes (drop 200 → [12.5,25,50,100]=0.9 dec, or swap in a slower top rate) and let the planner re-derive. See [[pvc-pcff-tg-degenerate-underpredict]] for the PVC slope-gate history.
