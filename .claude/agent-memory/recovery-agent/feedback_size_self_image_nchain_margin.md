---
name: size-self-image-nchain-margin
description: inspect_data_file's nchain_suggested for SIZE_CHAIN_SELF_IMAGE targets L/2Rg exactly 1.0, which is inside the ~7% SEM of the mean Rg it was derived from — always re-target with margin, and verify the forecast by unwrapping cell.data yourself
metadata:
  type: feedback
---

`finite_size_forecast.remedy` (`nchain_factor`, `nchain_suggested`) solves for `L/2Rg == 1.0`
exactly. Never transcribe it as the retry target — add margin, aiming for a forecast ratio
**≥ ~1.08–1.11**.

**Why:** PSU1 (2026-08-14, pre-submit gate at step=build). Forecast: L/2Rg=0.946 at nchain=20,
suggestion 24 → ratio 1.005, i.e. **0.5% margin against a 7.0% SEM on ⟨Rg⟩** (n=20 chains,
Rg 35.24 Å, std 11.01 Å, CV 31%). The suggestion is a point estimate of a noisy quantity, and the
gate that re-checks it post-equilibration measures Rg again on the relaxed melt. Recommended
nchain=32 (ratio 1.105, tolerates +10.5% Rg growth, 43,264 atoms = 1.60× cost).

Sizing rule: `ratio(nchain) = ratio_0 * (nchain/nchain_0)^(1/3)` — L grows only as nchain^(1/3),
so margin is expensive and must be bought once, deliberately.

**Cost asymmetry runs the other way from the usual recovery instinct:** the EMC rebuild is
~12 min (compare cell.data vs run_plan.json mtimes) and the *same* pre-submit forecast re-runs on
the new pack before anything is submitted, so an undershoot costs minutes, not the 8–15 h equil
chain. Sampling noise is therefore common-mode and caught for free; the only uncalibrated risk is
post-equilibration Rg **drift**. Size margin for drift, and tell the orchestrator the rebuilt
pack's own forecast must clear ≥1.08 — if it doesn't, re-target from *that* pack's numbers rather
than stepping a fixed ladder.

**Verify the forecast yourself — it is cheap and it is the only auditable part.** Parse
`lammps/cell/cell.data` (`id mol type q x y z`, no image flags), BFS the bond graph per molecule
unwrapping with the minimum image, mass-weight Rg. This reproduced PSU1's 35.244 Å / 0.9459 to four
digits, converting the injected symptom from testimony into a measurement
(see [[diagnosis-tooling-friction]] §2). It also rules out the one hypothesis that would invalidate
the whole extrapolation: if EMC had clamped chains to the build box, ⟨Rg⟩ would be a truncated
mean — falsified here by max Rg 66.1 Å > L/2 = 42 Å.

**Don't reach for `dp` as the box lever** even though it is stronger per unit cost
(ratio ∝ dp^(-1/2) at fixed atom count, vs nchain^(1/3) at fixed dp). recover.md's REBUILD-LARGER
names nchain, and dp buys box margin with Mn fidelity — fatal when Tg against a pinned experimental
value is a requested property.

**Report shape:** `step: build` with the governing row cited as Foundation → equil
`SIZE_CHAIN_SELF_IMAGE`; **omit `ladder_rung`** (no gate verdict, zero stages completed — same
precedent as the `emc_build.params` row); **omit `economics`** — REBUILD-LARGER is Class A and
explicitly exempt from step 5b, *and* the script is out of Bash scope (give both reasons).
