---
name: tg-steps-per-t-is-the-rate-lever
description: In a staircase tg_sweep deck, doubling tg_steps_per_t IS halving the cooling rate — which reconciles recover.md's conflicting analyze-tg and tg TG_REVIEW rows; also, tg r^2 is dominated by the linear rho(T) trend, not the kink
metadata:
  type: feedback
---

`recover.md`'s two `TG_REVIEW` / `tg_method_gap_K>20` rows look contradictory — Thermal → analyze-tg
says "double `tg_steps_per_t`, or widen the sweep", Thermal → tg says "no amount of sampling
resolves it, halt to human, never spend a slower rate". They reconcile through an identity.

**Rule: in a staircase deck, `rate = ΔT / (steps_per_T · dt)`.** Read it off the `.in`:
`timestep 1` + `run 200000` + `variable temps` spaced 20 K ⟹ 100 K/ns exactly. At fixed T-range and
fixed `tg_t_step_K`, *any* increase in time-per-T lowers the effective cooling rate. So the
analyze-tg row's first lever resolves to the next-slower entry in `tg_rates_K_per_ns` — the very
lever the tg row forbids by name. The analyze-tg row is written as if steps/T were rate-independent;
in a staircase deck it never is.

**Why:** the rows presuppose different root causes. analyze-tg's remedies are valid only when its
stated cause holds ("noisy density OR sweep range doesn't bracket the transition"). Falsify both
disjuncts before touching either lever; if both fail, it is the tg row's case (two admissible fits
disagreeing on adequate data) and the verdict is `escalate_human`.

**How to apply — discriminating the two causes (PMMA1 r100, 2026-08-11):**
- **`r_squared`/`fit_quality` are near-useless here.** Re-fit a *single straight line* over the whole
  sweep: PMMA1 gave r²=0.99527 vs the bilinear's 0.9968. The EXCELLENT grade was reporting the
  overall ρ(T) trend, not a localized transition. Always run this control before believing a
  high-r² Tg.
- Lead with the tool's own `tg_uncertainty_K` (90.1 K) — a 32.3 K gap is 0.36σ of it, i.e. the two
  fits do not disagree in any statistical sense. Corroborate with a free-knot bilinear scan
  (PMMA1 1σ knot band 280–399 K, optimum 340 K — nearer `Tg_alternative_K` than the headline).
- Per-bin α_V from `tg_density_bins_plateau.csv` shows whether a kink exists at all: PMMA1's
  bin-to-bin α_V scatter (1.1–3.4e-4) swamped the glass↔rubber contrast (1.85 vs 2.6e-4). A
  signal-amplitude problem, not a sample-count problem — √2 more samples cannot fix it.
- Check whether the sweep re-creates a defect the equil track already diagnosed: PMMA1's sweep
  300 K plateau (1.12512) matched the defective `npt_prod300` cell (1.1257) to 0.05% *despite*
  sourcing the clean 550 K melt, and α_rubbery was ~43% of the equilibrium melt CTE — the same
  liquid-leg tracking fraction `assess_cooling_contraction` measured. **Sourcing a clean melt only
  removes the pre-existing glass defect; it cannot remove one the sweep's own ramp creates.**

Step 5b is not required for this row (`not a rung-pricing question`) — and
`orchestration/scripts/remedy_economics.py` is outside Bash scope anyway
(see [[diagnosis-tooling-friction]]). Say both, or the denial reads as an incomplete diagnosis.
