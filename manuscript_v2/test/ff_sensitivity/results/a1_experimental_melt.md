# a1 — experimental rho(T) melt reference

Melt density is graded against experimental rho(T) (Mark 2007, `db/polymer_db.sqlite`) evaluated at each run's own T_equil -- no alpha extrapolation anywhere in this number.

## 1. Melt gap against experimental rho(T)

| run | T_equil (C) | rho_melt sim | melt gap % | n eqs | spread pp | evidence | status |
|---|---|---|---|---|---|---|---|
| PEEK1 | 497 | 1.0384 | (+3.64) | 1 | — | insufficient | T_EQUIL_OUTSIDE_EQUATION_RANGE |
| PEEK2 | 497 | 1.0541 | (+5.20) | 1 | — | insufficient | T_EQUIL_OUTSIDE_EQUATION_RANGE |
| PEEK3 | 497 | 1.0398 | (+3.78) | 1 | — | insufficient | T_EQUIL_OUTSIDE_EQUATION_RANGE |
| PEEK4 | 497 | 1.0471 | (+4.51) | 1 | — | insufficient | T_EQUIL_OUTSIDE_EQUATION_RANGE |
| PLA1 | 347 | 1.0878 | — | 0 | — | — | NO_EXPERIMENTAL_EQUATION |
| PLA2 | 347 | 1.1005 | — | 0 | — | — | NO_EXPERIMENTAL_EQUATION |
| PLA3 | 347 | 1.0994 | — | 0 | — | — | NO_EXPERIMENTAL_EQUATION |
| PLA4 | 347 | 1.1125 | — | 0 | — | — | NO_EXPERIMENTAL_EQUATION |
| PMMA1 | 277 | 1.0483 | **+1.03** | 5 | 2.92 | decisive | NEAR_RANGE |
| PMMA2 | 277 | 1.0633 | **+2.46** | 5 | 2.97 | decisive | NEAR_RANGE |
| PMMA3 | 277 | 1.0498 | **+1.17** | 5 | 2.93 | decisive | NEAR_RANGE |
| PMMA4 | 277 | 1.0573 | **+1.89** | 5 | 2.95 | decisive | NEAR_RANGE |
| PS1 | 277 | 0.8815 | **-3.95** | 3 | 1.73 | decisive | IN_RANGE |
| PS2 | 277 | 0.9077 | **-1.09** | 3 | 1.78 | decisive | IN_RANGE |
| PS3 | 277 | 0.9125 | **-0.56** | 3 | 1.79 | decisive | IN_RANGE |
| PS4 | 277 | 0.9049 | **-1.39** | 3 | 1.78 | decisive | IN_RANGE |
| PSU1 | 427 | 1.0451 | (+1.10) | 1 | — | indicative | T_EQUIL_OUTSIDE_EQUATION_RANGE |
| PSU2 | 427 | 1.0503 | (+1.61) | 1 | — | indicative | T_EQUIL_OUTSIDE_EQUATION_RANGE |
| PSU3 | 427 | 1.0527 | (+1.84) | 1 | — | indicative | T_EQUIL_OUTSIDE_EQUATION_RANGE |
| PSU4 | 427 | 1.0433 | (+0.93) | 1 | — | indicative | T_EQUIL_OUTSIDE_EQUATION_RANGE |
| PVC1 | 257 | 1.2099 | (+1.04) | 1 | — | insufficient | T_EQUIL_OUTSIDE_EQUATION_RANGE |
| PVC2 | 257 | 1.2027 | (+0.45) | 1 | — | insufficient | T_EQUIL_OUTSIDE_EQUATION_RANGE |
| PVC3 | 257 | 1.2237 | (+2.20) | 1 | — | insufficient | T_EQUIL_OUTSIDE_EQUATION_RANGE |
| PVC4 | 257 | 1.1793 | (-1.51) | 1 | — | insufficient | T_EQUIL_OUTSIDE_EQUATION_RANGE |

Bracketed gaps are extrapolated beyond the equation's fitted range and are NOT measurements. `spread pp` is the disagreement across all equations for that polymer, including widely extrapolated ones -- small spread despite differing extrapolation distance is what makes a NEAR_RANGE call defensible.

## 2. Alpha sensitivity — how much the recorded verdict rested on a default

| run | generic 6.0e-4 | simulated alpha variants | experimental rho(T) | spread (pp) |
|---|---|---|---|---|
| PEEK1 | +2.01 | — | — | 0.0 |
| PEEK2 | +3.54 | tg_r160: -3.94, tg_r40: -1.53, tg_r400: -5.37 | — | 8.91 |
| PEEK3 | +2.14 | tg_r25: -2.86 | — | 5.0 |
| PEEK4 | +2.87 | tg_r100: -3.12, tg_r100_rec1: -3.11, tg_r100_rec2: -2.09, tg_r25: -2.43, tg_r25_rec1: -0.78, tg_r25_rec2: -0.60, tg_r50: -1.03, tg_r50_rec1: -2.66, tg_r50_rec2: -2.81 | — | 5.99 |
| PMMA1 | -1.10 | — | +1.03 | 2.13 |
| PMMA2 | +0.31 | tg_r160: -4.79, tg_r40: -4.64, tg_r400: -5.65 | +2.46 | 8.11 |
| PMMA3 | -0.96 | tg_r100: -6.27 | +1.17 | 7.44 |
| PMMA4 | -0.25 | tg_r100: -5.28, tg_r25: -3.98, tg_r50: -2.42 | +1.89 | 7.17 |
| PS1 | -5.60 | — | -3.95 | 1.65 |
| PS2 | -2.79 | tg_r160: +1.47, tg_r400: -3.64 | -1.09 | 5.11 |
| PS3 | -2.28 | tg_r160: -4.74, tg_r40: -4.24, tg_r400: -5.06 | -0.56 | 4.5 |
| PS4 | -3.09 | tg_r100: -5.02, tg_r25: -4.96, tg_r50: -5.31 | -1.39 | 3.92 |
| PSU1 | -0.30 | tg_r160: -3.12, tg_r40: -2.94, tg_r640: -3.90 | — | 3.6 |
| PSU2 | +0.20 | tg_r160: -3.55, tg_r40: -1.82, tg_r400: -4.77, tg_rec1_r400: -5.10 | — | 5.3 |
| PSU3 | +0.43 | tg_r100: -2.54, tg_r25: -2.23, tg_r50: -0.17 | — | 2.97 |
| PSU4 | -0.47 | tg_r100: -3.52, tg_r25: -1.82, tg_r50: -3.33, tg_r80: -2.52 | — | 3.05 |
| PVC1 | -2.24 | — | — | 0.0 |
| PVC2 | -2.82 | tg_r160: -4.97, tg_r40: -3.97, tg_r400: -5.02, tg_r40_recov07: -3.82 | — | 2.2 |
| PVC3 | -1.12 | tg_r100: -2.85, tg_r25: -2.22, tg_r50: -2.59 | — | 1.73 |
| PVC4 | -4.71 | tg_r25: -5.42 | — | 0.71 |

## 4. Classification: force field or cooling protocol?

The melt is ergodic and cannot kinetically trap, so melt density is the direct probe of the nonbonded parameters. A glass that is low under a correct melt is a cooling-stage artifact.

A run counts as melt-deficient only when its gap exceeds the spread among the independent experimental equations for that polymer -- a measured tolerance, not a chosen one. Families whose runs straddle that line are reported MIXED rather than averaged: the melt densities themselves differ by up to 3.5% across cells that a2 shows are not seed-only replicates, so a family mean would hide the disagreement.

Only decisive and indicative evidence appears here; PEEK and PVC are excluded (single equation, extrapolated 1.6-2.1 fit-widths past its range).

| family | per-run melt gap % | tol (pp) | deficient runs | glass gap % | evidence | reading |
|---|---|---|---|---|---|---|
| PMMA | +1.03, +2.46, +1.17, +1.89 | 2.92 | 0/4 | -6.23 | decisive | melt OK -> **cooling protocol** |
| PS | -3.95, -1.09, -0.56, -1.39 | 1.73 | 1/4 | -6.18 | decisive | **MIXED** (1/4 deficient) |
| PSU | +1.10, +1.61, +1.84, +0.93 | n/a (1 eq) | 0/4 | -4.54 | indicative | melt OK -> **cooling protocol** |

### 4b. Rubbery families — the cleanest force-field test in the archive

PE, PEG and cis-PBD sit ABOVE Tg at 300 K, so npt_production samples an equilibrium liquid (verified: PEG1 runs `npt temp 300.0 300.0`, actual_T_mean 300.13 K). These runs do cool -- 500 K to 300 K via npt_cool -- but the ramp terminates above Tg and crosses no glass transition, so the system stays ergodic and cannot freeze in free volume. A deficit here is therefore not a trapping artifact. PEG is the case the reviewer names in paragraph 7.

| family | rho(300 K) sim | gap vs exp rho(T) % | eqs | spread pp | closest eq starts (C above 27) |
|---|---|---|---|---|---|
| PE | 0.8596 | **+1.09** | 2 | 0.08 | +103 |
| PEG | 1.0586 | **-5.43** | 3 | 0.18 | +3 |

**PEG is a genuine force-field deficit, not a cooling artifact.** Three independent equations agree within 0.18 pp and the closest starts only 3 C above 300 K. PEG is PCFF, is an equilibrium liquid at 300 K, and is still 5.5% under-dense -- and its bulk modulus is +50% against experiment (3.38 vs [2.0, 2.5] GPa, 0/4 passing). The two errors are consistent with one another: an over-stiff, under-dense PCFF description of PEO.

PE (TraPPE-UA) is fine at +1.1%, so this is not a general melt-stage problem.

**Consequence for the funded leg:** the alternative-force-field arm belongs on **PEG**, not PMMA. PMMA's melt is already correct, so no change of field can improve it. PEG fails to build under opls-aa and trappe-eh but builds under **compass and pcff_ore** -- those are its candidate arms.

**PMMA is the decisive case**: all four runs sit at +1.0 to +2.5%, i.e. melt density at or above experiment, while the glass is 6.2% low. The nonbonded parameters reproduce the melt; the cooling stage loses the density.

**PS is mixed and must not be collapsed to a mean.** PS1 is genuinely melt-deficient (its gap exceeds PS's own reference tolerance); PS2-PS4 are within tolerance. `polymer_rules.json` already records PS as MELT_STAGE_DEFICIT pending a heavy-melt-anneal probe, and this analysis does not overturn that -- it narrows it to one replicate and shows the other three do not support it.

### Why this falsifies the uniform sigma-shrink

The 2.04% sigma reduction was fitted to close the glass-state deficit. But sigma is a state-point-independent parameter: shrinking it necessarily raises melt density by the same excluded-volume mechanism. Melt density is already at or above experiment for PMMA and for three of four PS runs, so the fit repairs a state point that is wrong by moving one that is right. The magnitude (volume ~ sigma^3, so ~6%) is supporting detail; the state-point independence is the argument.

### The heuristic is biased toward blaming the force field

Section 2 shows the alpha-based melt gap runs ~1.5-2 pp BELOW the experimental one on both decisive families. The shipped default therefore systematically overstates the melt deficit, which is the mechanism by which the manuscript's PCFF attribution arose. `assess_cooling_contraction`'s generic defaults are still in place, so the pipeline will keep making this error until the heuristic is gated against an experimental reference.

## 3. Simulated vs assumed expansivity (reported, not applied)

| run | rate | alpha_rubbery simulated | vs generic 6.0e-4 |
|---|---|---|---|
| PEEK2 | tg_r160 | 3.453e-04 | -42.5% |
| PEEK2 | tg_r40 | 4.274e-04 | -28.8% |
| PEEK2 | tg_r400 | 2.964e-04 | -50.6% |
| PEEK3 | tg_r25 | 4.273e-04 | -28.8% |
| PEEK4 | tg_r100 | 3.948e-04 | -34.2% |
| PEEK4 | tg_r100_rec1 | 3.953e-04 | -34.1% |
| PEEK4 | tg_r100_rec2 | 4.300e-04 | -28.3% |
| PEEK4 | tg_r25 | 4.187e-04 | -30.2% |
| PEEK4 | tg_r25_rec1 | 4.750e-04 | -20.8% |
| PEEK4 | tg_r25_rec2 | 4.813e-04 | -19.8% |
| PEEK4 | tg_r50 | 4.665e-04 | -22.3% |
| PEEK4 | tg_r50_rec1 | 4.106e-04 | -31.6% |
| PEEK4 | tg_r50_rec2 | 4.055e-04 | -32.4% |
| PMMA2 | tg_r160 | 2.680e-04 | -55.3% |
| PMMA2 | tg_r40 | 2.777e-04 | -53.7% |
| PMMA2 | tg_r400 | 2.121e-04 | -64.7% |
| PMMA3 | tg_r100 | 2.501e-04 | -58.3% |
| PMMA4 | tg_r100 | 2.707e-04 | -54.9% |
| PMMA4 | tg_r25 | 3.562e-04 | -40.6% |
| PMMA4 | tg_r50 | 4.581e-04 | -23.6% |
| PS2 | tg_r160 | 8.783e-04 | +46.4% |
| PS2 | tg_r400 | 5.446e-04 | -9.2% |
| PS3 | tg_r160 | 4.402e-04 | -26.6% |
| PS3 | tg_r40 | 4.727e-04 | -21.2% |
| PS3 | tg_r400 | 4.195e-04 | -30.1% |
| PS4 | tg_r100 | 4.734e-04 | -21.1% |
| PS4 | tg_r25 | 4.773e-04 | -20.4% |
| PS4 | tg_r50 | 4.545e-04 | -24.2% |
| PSU1 | tg_r160 | 4.589e-04 | -23.5% |
| PSU1 | tg_r40 | 4.680e-04 | -22.0% |
| PSU1 | tg_r640 | 4.197e-04 | -30.1% |
| PSU2 | tg_r160 | 4.132e-04 | -31.1% |
| PSU2 | tg_r40 | 4.993e-04 | -16.8% |
| PSU2 | tg_r400 | 3.525e-04 | -41.2% |
| PSU2 | tg_rec1_r400 | 3.359e-04 | -44.0% |
| PSU3 | tg_r100 | 4.525e-04 | -24.6% |
| PSU3 | tg_r25 | 4.675e-04 | -22.1% |
| PSU3 | tg_r50 | 5.701e-04 | -5.0% |
| PSU4 | tg_r100 | 4.471e-04 | -25.5% |
| PSU4 | tg_r25 | 5.324e-04 | -11.3% |
| PSU4 | tg_r50 | 4.566e-04 | -23.9% |
| PSU4 | tg_r80 | 4.973e-04 | -17.1% |
| PVC2 | tg_r160 | 4.593e-04 | -23.4% |
| PVC2 | tg_r40 | 5.246e-04 | -12.6% |
| PVC2 | tg_r400 | 4.559e-04 | -24.0% |
| PVC2 | tg_r40_recov07 | 5.347e-04 | -10.9% |
| PVC3 | tg_r100 | 4.892e-04 | -18.5% |
| PVC3 | tg_r25 | 5.296e-04 | -11.7% |
| PVC3 | tg_r50 | 5.059e-04 | -15.7% |
| PVC4 | tg_r25 | 5.529e-04 | -7.8% |
