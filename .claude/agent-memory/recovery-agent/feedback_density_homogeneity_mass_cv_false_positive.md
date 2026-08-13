---
name: density-homogeneity-mass-cv-false-positive
description: equil-check density_homogeneity CV is mass-weighted but its poisson_cv floor is count-based (both the old raw-CV<25% and the new cv_signal<=11% forms) — on small H-rich cells the gate false-FAILs below its own true noise floor; verify against a randomized-placement baseline before recommending MELT-MIXING/EXTEND
metadata:
  type: feedback
---

Before recommending a MELT-MIXING or EXTEND respawn for a `density_homogeneity`-only
STRUCTURAL_FAIL, verify the CV against a randomized-placement baseline. The gate's own
`poisson_cv` is **not** the right floor.

**Why:** `check_equilibration_comprehensive` reports `cv_mean` as a **mass-weighted** voxel CV but
reports `poisson_cv` as the **count-based** floor `1/sqrt(atoms_per_voxel)`. For polymers with a
wide atomic-mass spread (H=1 vs C=12 vs O=16) these differ a lot, so `poisson_limited` can read
`false` when the measurement is in fact pure shot noise. The correct floor is the compound-Poisson
value `sqrt(E[m^2] / (atoms_per_voxel * E[m]^2))`.

PMMA1 (2026-08-10, PACR, dp=50, 10 chains, 7520 atoms, 7^3 grid, 21.9 atoms/voxel):
- gate: `cv_mean=0.2827`, `poisson_cv=0.214`, `poisson_limited=false` → STRUCTURAL_FAIL vs 25%
- count-based CV on the same frames: 0.206-0.214 (= the count Poisson floor exactly)
- compound-Poisson mass floor: **0.291**; randomized-placement control: **0.2896 +/- 0.0105**
- measured 0.2827 is *below* the uncorrelated-random baseline → the melt is marginally **more**
  homogeneous than a random gas. Zero physical heterogeneity. No extension can ever pass this gate.

**How to apply:** recompute from the dump the gate names in `dump_file` (a ~10-line numpy voxel
bin + a shuffled-position control, using `Masses` from the `.data` file). If
`cv_mean <= randomized baseline`, the FAIL is an artifact — recommending EXTEND burns the 2-extension
MELT-MIXING budget plus ladder attempts for nothing, then escalates to rung 3 (FF re-plan) for a
non-existent defect. Corroborates the user-level memory `feedback-equilcheck-homogeneity-melt-dump`
(PSU2, 2026-06-23: 2 ns extension moved CV 25.60% -> 25.59%, ~3h wasted) and extends it with a
quantitative test that works regardless of regime or which dump the gate read.

Also checked and found NOT to be the cause on PMMA1: the gate reads
`nvt_production/nvt_production.dump` even when a newer `npt_production.dump` exists (see
[[feedback-equilcheck-homogeneity-melt-dump]] on the `gen_prompt.py --npt_prod_dump` default). Both
trajectories gave the same CV (0.2849 vs 0.2805), so re-gating on the newer dump is not a fix
either.

**The 2026-08-11 gate-taxonomy overhaul did not fix this — it repackaged it.** The gate now reports
`cv_signal` against a `cv_signal_max=0.11` threshold instead of raw `cv_mean` against 0.25, rendered
as "18.5% (raw 28.3% − Poisson 21.4%)". That is literally
`cv_signal = sqrt(cv_mean^2 - poisson_cv^2) = sqrt(0.2827^2 - 0.214^2) = 0.1852` — the *same*
mass-CV-minus-count-floor mismatch, now quadrature-subtracted. Since the correct compound-Poisson
**mass** floor (0.2914) exceeds `cv_mean` (0.2827), the true signal CV is zero and `cv_signal` is
pure arithmetic on mismatched units. Recognize the new form on sight: if
`sqrt(cv_mean^2 - poisson_cv^2)` reproduces the reported `cv_signal` to 3 digits, it is this bug.
Also note `verdict=HOMOG_HETEROGENEOUS` / `heterogeneous_flag=true` carry no extra evidence — they
are just the threshold restated.

Related: [[feedback-degenerate-kww-tau-extend-sizing]], [[diagnosis-tooling-friction]]
