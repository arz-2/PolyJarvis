---
name: marginal-density-drift-autocorrelation
description: equil-check density_drift p-values are OLS-on-correlated-samples, so a marginal (~1%) drift is never resolved by its p-value alone — break the tie with the P-vs-rho quarter trajectory, and size the EXTEND from the stationary-noise scale
metadata:
  type: feedback
---

`check_equilibration_comprehensive`'s `density_drift.p_value` regresses ~500 thermo rows as if
independent. Density in an NPT melt has an integrated autocorrelation time of order 5-20 ps, so
`p=0.0` on a marginal drift is not evidence of a real trend. Never call a marginal exceedance
either "genuine" or "artifact" from the p-value.

**Why:** the two available tau estimates bracket rather than decide. Raw tau is inflated if the
trend is real; detrended tau is deflated by construction. PEEK1 (2026-08-11, PKTN/PCFF, 8720 atoms,
770 K melt): drift -1.0691% vs <1%, tau_raw 16.6 ps -> 2.1 sigma, tau_detrended 4.5 ps -> 4.0 sigma.
Same data, opposite conclusions.

**How to apply — three cheap checks, all from `<stage>/<stage>.log`:**
1. **Is the scatter equilibrium?** Compare the production-window density sigma against
   `sqrt(kB*T*kappa_T/V)`. PEEK1: 0.813% observed vs 0.52-0.85% predicted for kappa_T 3e-10..8e-10
   Pa^-1 — the scatter is the physical NPT volume fluctuation, so an apparent drift of order sigma
   is expected from a random walk, not a defect.
2. **The tie-breaker: the joint (P, rho) quarter trajectory.** Relief of over-compression looks
   like P decaying from positive *toward* setpoint while rho falls. PEEK1 showed P *rising*
   (-161 -> -82 -> +45 -> +109 atm) while rho fell — a coupled excursion, i.e. the random-walk
   branch. Also tau-correct the mean P against the `fix npt` setpoint: PEEK1 full-run
   -21.8 +/- 39.2 atm vs 1 atm (t=-0.58) — barostat on target, no residual compressive load.
3. **Sign matters diagnostically, not for routing.** Expanding rules out incomplete compaction /
   void closure (cross-check `spatial.density_homogeneity` near its Poisson floor); densifying
   would point back at the pack. Either way `recover.md` routes to the same MELT-MIXING EXTEND.

**Sizing:** apparent drift for a stationary series scales as `sigma*sqrt(12*tau/n)`. At PEEK1's
numbers a 1.5 ns extension (n=750 production rows) gives ~0.42% expected apparent drift, so the
`recover.md` 1.5 ns floor already passes cleanly if stationary and fails informatively if real —
no reason to over-size extension 1. Recommend the escalation (3 ns for extension 2, same sign and
magnitude) in `notes` rather than baking it into `params_changed`.

**tau_relax sizing, second variant:** `chain.ct.tau_ps` need not be bound-pinned to be unusable.
PEEK1 had `tau_ps=2.256e5` (not the 1e9 bound), `beta=0.641` (healthy), but
`decay_fraction_at_end=0.029` over `trajectory_ps=1951` — a fit extrapolated ~116x past the data.
Unresolved, so the 1.5 ns floor applies. Extends [[degenerate-kww-tau-extend-sizing]], which only
covers the bound-pinned signature.

Related: [[density-homogeneity-mass-cv-false-positive]], [[diagnosis-tooling-friction]],
[[under-annealed-cooling-ramp-rate-calibration]]
