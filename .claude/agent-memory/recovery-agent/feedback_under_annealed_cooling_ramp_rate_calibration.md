---
name: under-annealed-cooling-ramp-rate-calibration
description: UNDER_ANNEALED_COOLING is a cooldown ramp-RATE defect, not a melt-anneal defect — decompose the deficit by localizing per-bin alpha_V in npt_cool300, and calibrate the needed ramp against the run's own npt_cool (630->T_equil) stage
metadata:
  type: feedback
---

On a `phase=full` STRUCTURAL_FAIL with `structural_fail_remedy=re_melt_slow_recool`, do not stop at
the tool's `UNDER_ANNEALED_COOLING` verdict. Two cheap computations turn it into an actionable,
quantified diagnosis.

**1. Localize the lost contraction with per-bin alpha_V.** Block-average the `npt_cool300` thermo
table into ~25 T-bins and compute local `alpha_V = ln(rho_i/rho_{i-1}) / (T_{i-1}-T_i)`, comparing
against `alpha_melt_per_K` above `tg_K` and `alpha_glass_per_K` below. This says *where* the
contraction was lost. If the lag sits in the **liquid** leg (well above Tg) it is a ramp-too-fast
protocol defect and is genuinely recoverable; a lag confined to the near-Tg/glass leg would be the
irreducible log-weak quench-rate effect instead.

**2. Calibrate the required ramp against the run's OWN `npt_cool` stage.** The melt-phase
`npt_cool` (annealing_T_high_K -> T_equil_K) is a second NPT ramp on the same cell at a different
rate — a free control that separates "ramp too fast" (H1) from "melt kinetically arrested" (H2).
Aggregate its `alpha_V` and take the ratio to `alpha_melt_per_K`. Ratio ~1 ⇒ H1, volume response is
normal and slowing the ramp works. Ratio well below 1 at an already-slow rate ⇒ H2, expect rung 1
to underdeliver and pre-position for rung 3 (FF re-plan).

PMMA1 (2026-08-10, PACR/PCFF, dp=50, Tg 378 K, T_equil 550 K, dt 1.0 fs):
- `npt_cool` 630->550 K over 2e6 steps = **40 K/ns** -> alpha_obs 5.87e-4, **ratio 0.95** to melt
  CTE 6.15e-4. H1 confirmed; the melt tracks equilibrium volume almost perfectly.
- `npt_cool300` 550->300 K over 1e6 steps = **250 K/ns** -> liquid leg ratio **0.40**, glass leg
  ratio 0.90. The whole -6% deficit was generated in the liquid leg of this one stage.
- Melt density at 550 K was correct (-0.4%); applying literature CTEs to it lands at 1.193 vs exp
  1.19. Note this back-extrapolation is *algebraically the same datum* as the -0.4% gap, not
  independent corroboration — the per-bin alpha_V is the independent evidence.
- Implied class-level target: ~40 K/ns for the T_equil->300 K leg = `npt_cool300_steps` ~6.25e6,
  i.e. **6x** baseline `int(1.0e6/dt_fs)`. `recover.md`'s RE-ANNEAL rung-1 ladder (2x then 4x) tops
  out at 62.5 K/ns and can plausibly clear the +/-5% band without reaching rate-convergence.

**Why:** `eq_annealing_cycles` (raised 5->10 for PACR on 2026-08-04 to fix exactly this signature on
PMMA2/3/4) acts on the **melt-mixing** anneal and shapes the melt state. When the melt density is
already correct, that knob cannot address the deficit — it is the wrong stage. `npt_cool300_steps`
is a `generate_equilibration_workflow` default, absent from `decided_params`, so overriding it on
the worker is an in-pipeline fix, not a `decided_params` change (no `escalate_human` trigger).

**How to apply:** run both computations before returning; report the ramp rate in K/ns, not just the
step count. Warn that a gate pass obtained at 2x is a **rate-dependent density**, not a converged
property — material when density is the run's headline number. Note also that a flat MSD /
undecayed C(t) in the melt does NOT by itself imply volume cannot track: volume equilibration needs
only segmental packing relaxation, and the `npt_cool` control settles the question empirically.

Related: [[density-homogeneity-mass-cv-false-positive]], [[degenerate-kww-tau-extend-sizing]],
[[diagnosis-tooling-friction]]
