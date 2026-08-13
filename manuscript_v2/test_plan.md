# Test plan — four sensitivity/benchmark tests for reviewer round 2

Addresses reviewer comments on force-field validation (¶7), bulk-modulus robustness (¶8), replicate
design and Tg robustness (¶4), and the agent contribution benchmark (¶6). Complements
`revision.md`'s sections A–F; where the two differ, this file is the newer design.

Each test has a **free leg** (re-analysis of existing data, no simulation) and a **funded leg** (new
runs). The free legs are sequenced first throughout, because in three of the four tests the free leg
can settle the question the funded leg was built to answer.

---

## 1. Force-field sensitivity

**Reviewer ask.** Controlled calculations under an alternative force field *or charge treatment* on
one to two representative systems; internally consistent routing description; until then, attribution
of errors to PCFF stated as hypothesis, not mechanism.

**What changed since `revision.md`.** The candidate field is no longer COMPASS. Measured coverage:
only **PCFF and GAFF2** can build all nine families; COMPASS fails to type six of nine (including
PMMA and PEEK); PEEK and PSU have GAFF2 as their *only* alternative. Published evidence removed
COMPASS's rationale — in the one same-polymer multi-field benchmark including it (PDMS,
`10.1021/acs.jpcb.4c08471`) COMPASS was worst of five and **over**-predicted density, the opposite
sign from our deficit. GAFF2's own large-scale validation (RadonPy, `10.1038/s41524-022-00906-4`)
admits a systematic density bias, and no located source validates it on aromatic backbones at all.

**Free leg — RUN. It answered the question, and the answer is not the force field.**

Scripts and outputs: `manuscript_v2/test/ff_sensitivity/` (`a0`–`a3`, `results/`).

The archive already contained the discriminator. `assess_cooling_contraction` splits each glassy run
into a melt density and a glass density; the melt is ergodic and cannot kinetically trap, so it is
the direct probe of the nonbonded parameters. Grading the simulated melt against **experimental
ρ(T)** (Mark 2007, `db/polymer_db.sqlite`, evaluated at each run's own T_equil — no α extrapolation):

| family | melt gap % | glass gap % | evidence | reading |
|---|---|---|---|---|
| PMMA | +1.03, +2.46, +1.17, +1.89 | −6.23 | decisive | melt OK → **cooling protocol** |
| PS | −3.95, −1.09, −0.56, −1.39 | −6.18 | decisive | **MIXED** — 1 of 4 melt-deficient |
| PSU | +0.93 … +1.84 | −4.54 | indicative | melt OK → **cooling protocol** |

PEEK and PVC are excluded: single equation each, extrapolated 1.6–2.1 fit-widths past its range.
A run counts as melt-deficient only when its gap exceeds the spread among the independent
experimental equations for that polymer — a measured tolerance, not a chosen threshold.

Three consequences:

- **The PCFF attribution does not survive as stated.** PMMA reproduces melt density at or above
  experiment while its glass is 6.2% low. PS is mixed and must not be averaged: PS1 is genuinely
  melt-deficient, PS2–PS4 are within tolerance.
- **The uniform 2.04% σ-shrink is falsified.** σ is state-point independent, so shrinking it must
  raise melt density too — it repairs a wrong state point by moving a right one.
- **The α heuristic is biased toward blaming the force field.** Its melt gap runs ~1.5–2 pp below the
  experimental one on both decisive families. That is the mechanism by which the attribution arose,
  and the generic defaults are still in place, so the pipeline will keep making it.

Also delivered, and stronger than the density result for reviewer ¶4 and ¶5:

- **Zero of nine families is a seed-only replicate set** (`a2`). Every family varies 3–7 protocol
  axes across its four runs, and `charge_method` varies within **8 of 9** — PE1/PE2 Gasteiger vs
  PE3/PE4 none is a force-field-level difference inside a set reported as mean ± SD.
- **Two recorded parameters never reached the deck** (`a3`, 36 runs audited by reading the `.in`
  files): `cutoff_A` records 12.0 Å and runs 9.5 for 32/36 runs, and `eq_annealing_cycles` reaches no
  executor at all — including the 5→10 (PMMA) and 8→12 (PEEK) raises applied as remedies. Both are
  now corrected in `polymer_rules.json`, with a `validate_run_plan.py` guard against recurrence.
- **Routing-table audit — the code side is clean.** `polymer_rules.preferred_ff` agrees with the EMC
  server's class routing for all 21 classes (16 pcff, 2 opls-aa, 2 trappe-ua, PURA on RadonPy). The
  reviewer's "internally consistent routing description" concern therefore lands entirely on the
  manuscript/SI prose, which is user-owned and still to be checked — there is no code defect behind it.

**PEG is the exception, and it is a genuine force-field deficit — the case the reviewer names.**
PE, PEG and cis-PBD have no glass state to decompose (no `npt_prod300` stage), so they are outside
the melt/glass split — but they are the *cleanest* force-field test in the archive, because they sit
above Tg at 300 K. Their production cell is an equilibrium liquid (PEG1 runs `npt temp 300.0 300.0`,
actual_T_mean 300.13 K). They do cool 500→300 K, but the ramp terminates above Tg and crosses no
glass transition, so free volume cannot freeze in and the trapping explanation is unavailable.

| family | ρ(300 K) sim | vs experimental ρ(T) | equations | spread |
|---|---|---|---|---|
| PE (TraPPE-UA) | 0.8596 | **+1.09%** | 2 | 0.08 pp |
| **PEG (PCFF)** | 1.0586 | **−5.43%** | 3 | 0.18 pp |

PEG is 5.4% under-dense as an equilibrium liquid *and* its bulk modulus is +50% (3.38 vs [2.0, 2.5]
GPa, 0/4 passing) — consistent as an over-stiff, under-dense PCFF description of PEO, and exactly the
pairing the reviewer flags. **The alternative-force-field arm therefore belongs on PEG, not PMMA**:
PMMA's melt is already correct, so no change of field can improve it.

### The funded arm — RUN, and it answers ¶7 positively

Two arms on PEG, protocol/cell/cutoff/seed held identical to the PEG1-4 baseline (7020 atoms,
dp=100, nchain=10, T_equil 500 K, 9-stage rubbery chain, 2 ns production), **only `preferred_ff`
varying**. Runs `data/PEGCMP1` and `data/PEGORE1`; both equil-check **PASS**; gated plateau means:

| field | plateau ρ(300 K) | block-SEM | vs exp 1.1194 | vs PCFF |
|---|---|---|---|---|
| PCFF (PEG1–4) | 1.0586 | — | −5.43% | — |
| pcff_ore | 1.0557 | 0.03% | −5.69% | −0.28% |
| **COMPASS** | **1.1241** | 0.04% | **+0.42%** | **+6.19%** |

The two arms separate typing from parameters, and the separation is clean. **pcff_ore assigns the
same five atom types as PCFF** and changes only parameter values — it moves nothing (−0.28%, inside
PCFF's own replicate spread 1.0576–1.0612). **COMPASS types the ether backbone finely** — a dedicated
ether oxygen `o2e`, and `c4` vs `c4o` carbons where PCFF lumps every sp3 carbon into one `c` — and
lands on experiment.

**Conclusion: PEG's density deficit is PCFF's coarse ether typing, not mis-fitted parameters.** For a
polymer one-third ether oxygen by backbone atom, a refit of the same functional form on the same
typing cannot help. This is the controlled alternative-force-field calculation ¶7 asked for, and for
PEG the attribution to PCFF is now demonstrated rather than hypothesised.

Two caveats to carry into the write-up. The finite-size minimum-image gate reported **unarmed** on
both arms (`cutoff_A` is unsupported in the deployed `inspect_data_file` schema), so each PASS rests
on the 2·Rg criterion alone — L/2Rg = 1.134 (COMPASS) and 1.024 (pcff_ore, thin). And C(t) is
essentially undecayed on both (τ_relax ≫ trajectory), which the rubbery carve-out makes advisory by
design: PASS means the density plateau is trustworthy, not that the melt is relaxed.

**Funded leg — arms, on PMMA primary and PS secondary.** Both have verified amorphous comparators
(1.19, 1.05 g/cm³), both carry a large measured deficit (−6.2%, −6.5%), and both build under
multiple alternatives.

| arm | field | what it isolates |
|---|---|---|
| A | PCFF (anchor) | baseline; already in hand |
| **E** | **PCFF + heavy melt anneal** | **the cooling-stage hypothesis the free leg indicates** |
| B | **OPLS-AA 2024** | all-atom, **non-Class-II**, same protocol — bounds the field's share |
| C | GAFF2 (RadonPy + QM charges) | breadth; the only path available for PEEK/PSU |
| D | PCFF LJ + alternative charges | **charges vs LJ**, holding the field fixed |

**Arm E is now the indicated arm, and it is new.** The free leg places the deficit in the cooling
stage, and NkepsuMbitou2025 reaches within 2% on PMMA with PCFF via ~10 anneal cycles / ~100 ns from
ρ=0.5 — a literature target for exactly this hypothesis. It needs no new plumbing.

Arm E is applied at equilibration via `add_melt_npt=True` with `melt_npt_steps` at 10× then 50×
`int(1.0e6/dt_fs)`. It is **not** `eq_annealing_cycles`: that parameter reaches no executor, and
`validate_run_plan.py` now fails any plan that sets it. Arm B stays worthwhile on PS, the one family
with a genuine (if single-replicate) melt deficit.

Arm B is the designed test because it is also the **missing control**: cleanly separating "our
protocol" from "PCFF's parameters" needs an all-atom, non-Class-II family run under the same protocol
with a verified comparator, and no such run exists in the archive. TraPPE-UA is united-atom; PHAL and
PSIL do run OPLS-AA but have no experimental density value. Arm B supplies it.

Arm D answers the reviewer's "or charge treatment" directly. PCFF currently runs
`charge_method: none` (EMC bond-increment charges); substituting QM charges on unchanged LJ
parameters separates the two contributions.

Arm D's original rationale was to falsify the uniform 2.04% σ shrink, which fitted all four deficit
families to 0.20 pp by attributing the deficit to LJ radii. **The free leg already falsified it**, on
a stronger argument than arm D could have given: σ is state-point independent, so shrinking it must
raise melt density too — and melt density is at or above experiment. Arm D therefore drops to a
breadth arm and no longer carries a falsification role. Note also that `charge_method` is one of the
axes `a2` found varying *within* replicate sets (8 of 9 families), so some of this contrast is
already present in the archive and should be extracted for free before arm D is scheduled.

**Arm D's cost is unverified and must be checked before it is scheduled as the cheap arm.** RadonPy
assigns QM charges through its own typing path, so putting them onto an EMC-built PCFF cell may
require rewriting the charge column of the `.data` file rather than setting a supported flag. If no
supported path exists, arm D is a plumbing task first and is not the cheapest arm.

**Observable.** Amorphous density at 300 K is the discriminating measurement (0.28 pp replicate
noise floor against a ~6 pp effect). Tg is secondary and expected to *worsen* under OPLS-AA —
`data/PMMA1/raw/run_plan.json` records Tang2022 at 481 K simulated vs 383 K experimental. Report it;
do not treat a density win as a general upgrade.

**Registered prediction, recorded before running.** All arms ≈6% low ⇒ not PCFF-specific, and the
manuscript's PCFF attribution must be withdrawn. Arm B within ~2% ⇒ PCFF-specific, attribution
stands as demonstrated.

**Cost note.** OPLS-AA carries **no** GPU penalty — EMC emits `dihedral_style multi/harmonic` (which
has a `/kk` variant) and no impropers at all, since `opls-aa.prm` defines impropers only for `c3=`
alkene centers. Arm B is as accelerated as arm A and cutoff-matched to it (both `9.5 9.5`). GAFF2 is
the one genuinely slower alternative (`dihedral_style fourier`, `improper_style cvff` host-side);
measure that penalty on one short run before sizing arm C.

---

## 2. Bulk-modulus robustness

**Reviewer ask.** Demonstrate sensitivity to pressure-ladder span, barostat settings, production
length, and system size — or substantially qualify the claim that the EOS result is barostat-insensitive.

**Free leg — settles two of the four axes with zero GPU time.** Both are re-fits of existing
pressure series.

- **Ladder span.** Re-fit every archived Murnaghan series on nested truncations of its own ladder.
  Measured on cis-PBD1, span dominates the answer: on the 1–15000 atm ladder as run, orientation
  disagreement is **8.3%** (P(V) 1.837 vs V(P) 1.685 GPa); truncated to 1–5000 it is 0.5%; to
  1–2500, 0.0%. The wide ladder is the newer setting, so this is a live defect and not a hypothetical.
- **Fit method.** Re-fit under five forms — Murnaghan P(V), Murnaghan V(P), Tait free-C, Tait fixed-C,
  Birch–Murnaghan. Spread on cis-PBD1's wide ladder is **0.879–1.837 GPa** against a stated
  uncertainty of ±0.119. Orientation is the load-bearing choice: NPT *sets* pressure and *measures*
  volume, so residuals belong in V, and the shipped fit is P(V).

Both cis-PBD1 figures are single-system measurements, so each leg's deliverable is the **distribution
of per-run spread across every archived series with ≥4 pressure points** — not one run's number
generalized by assertion. Together they feed one headline change: **a K uncertainty that includes
method dispersion.** Both currently-quoted K uncertainties exclude it.

**Funded leg — one representative system.** Barostat τ_P, production length, and system size are not
recoverable from existing data. Production length is partially free (`prod_ns` already spans
0.625–1.25 ns incidentally); extend only if that range fails to show convergence.

**Standing claim to verify or withdraw.** The manuscript's barostat-insensitivity assertion rests on
an abandoned sweep. Either the supporting evidence is produced or the claim is qualified — the
reviewer explicitly offers that second option, and it is the cheaper honest route.

---

## 3. Tg sensitivity

**Reviewer ask.** Controlled sensitivity to cooling rate, temperature grid, equilibration duration,
and fitting procedure, for representative systems. Separately (¶4): stop conflating stochastic
sampling uncertainty with protocol and finite-size variation across replicates.

**Free leg — the most consequential analysis in this plan.**

- **Fitting-procedure sensitivity**, across all runs: vary bilinear breakpoint window, fit range, and
  bilinear vs WLF form. In 54% of archived fits the quoted `tg_uncertainty_K` is already exceeded by
  the run's own method gap, and the method-gap gate fires on **60% (49/81)** of clean fits — a
  default, not a gate. Expected outcome: the reported Tg uncertainty is not credible as stated and
  must be widened to include method dispersion.
- **Units correction.** `loglinear_slope_K` is per natural log, not per decade (×2.303). Uncorrected,
  six runs appear to pass the slope gate. On physics, **all six fail** — 111.6, 111.6, 36.7, 25.7 and
  12.5 K/decade against a physical 3–5, and cis-PBD2's 5.1 has zero residual degrees of freedom. True
  slope-gate pass rate is **0/25**. Fix the units, re-report, and remove contaminated rows.
- **Replicate-set protocol audit** (shared with test 1's free leg): tabulate which protocol axes vary
  within each family's replicate set, so mean ± SD can be relabelled honestly. The reviewer names
  cooling rate, chain length, atom count, chain count, annealing cycles and pressure ladder.

**Funded leg.**

- **Cooling-rate ladder**, sweep-only from an anchor cell: `[10, 25, 50, 100, 200, 400, 800]` K/ns,
  ~1.9 decades.
- **Temperature-grid step**, `tg_t_step_K ∈ {10, 20, 40}` K at fixed rate — genuinely new axis, no
  existing data.
- **Equilibration duration**, `t_equil_ns ∈ {anchor, +5, +10}` — the one axis needing fresh
  build+equil.

**A design correction the power analysis forces — two separate deliverables, not one.** Per-rate
residual SD is 17.0 K against a 2–3 K signal over the 0.6 decades currently spanned. Monte Carlo
gives 80% power at **7.5 decades** (σ = 5 K) to **24 decades** (σ = 17 K). The 1.9-decade ladder is
therefore badly underpowered to *measure the log-linear slope*, and no affordable ladder is not.

These are different results and the plan must not collapse them:

1. **Cooling-rate sensitivity — delivered regardless.** The ladder yields per-rate Tg values at seven
   rates on a fixed protocol. That *is* the controlled cooling-rate sensitivity analysis ¶4 asks for,
   and it stands whether or not the slope is resolvable. Report it as the primary output.
2. **Rate extrapolation — predicted to fail, and that prediction is registered in advance.** If the
   slope is unresolvable at 1.9 decades as the power analysis forecasts, that justifies retiring the
   multi-rate DSC-equivalent extrapolation in favour of single-rate values with explicit
   rate-artifact annotation.

Registering (2) beforehand is what distinguishes a predicted null from an avoided test, but (1) is
what answers the reviewer, and it is not contingent on (2).

---

## 4. Agent contribution benchmark

**Reviewer ask.** Show the strongest agent-only cases *resuming and completing* end-to-end, not
stopping at diagnosis. Define recovery as successful completion of the intended simulation and
property calculation. Repeat over trials, preferably on unseen failures. Provide an end-to-end
deterministic baseline to quantify the LLM's incremental contribution.

**Definition, predeclared.** *Recovered* = the pipeline resumes and produces a property value that
clears the strict mechanized gate. Not "no further errors in the log", and not a diagnosis or a
proposed reroute. This definition depends on the gate being trustworthy, which is why tests 2 and 3
sequence ahead of this one.

**Three arms, unchanged in structure from the existing ablation harness.**

| arm | configuration | isolates |
|---|---|---|
| 1 | stock EMC defaults, no recovery | task difficulty |
| 2 | scripted catalog recovery only | value of the encoded playbook |
| 3 | full agent + literature grounding | **incremental LLM contribution** |

Metric: fraction of trials reaching a gate-passing property value. Report wall-clock and count of
human interventions alongside, but the completion fraction is the headline.

**Trials and faults.** N ≥ 3 trials per fault across F1–F6 plus at least one genuinely new fault, so
the result is a recovery *rate* rather than an anecdote.

**Two honesty requirements that will otherwise be caught.**

- **Of the six existing faults, only F6 is genuinely novel to the agent.** F5's fix is encoded in the
  EMC system instructions the agent already reads, so F5 must be reported as
  recovered-from-encoded-knowledge. Overstating the inferred count is the single most likely
  credibility failure in this section.
- **The PE over-densification must be shown to be autonomously catchable**, which the reviewer notes
  the corrected result does not demonstrate. This needs its own injected-fault trial: reproduce the
  original over-densified condition and verify the mechanized gate fires on it unaided. A corrected
  number is not evidence of detection.
- **Arm 3 must not inherit cached literature work.** The literature-grounding worker is what separates
  arm 3 from arm 2, and its output for the force-field question is already written
  (`docs/ff_selection_literature.json`). Arm 3 trials must re-run the search for their own systems;
  reusing an existing file would credit the agent with work it did not do in-trial.

**Unseen failure cases.** One to two genuinely off-table polymers with no `polymer_rules.json` entry,
run full-pipeline end to end with real failures allowed to occur. This is the strongest available
evidence for the reviewer's "preferably unseen" and doubles as new-class generality.

---

## How these tests help the workflow and the presented problem

**They convert unrecorded choices into reported uncertainties.** Three of the four tests are the same
disease in different places. The pressure-ladder span and EOS orientation (test 2), the bilinear
breakpoint and fit form (test 3), and the force field itself (test 1) are all choices the pipeline
makes silently and does not record, each spanning more than the uncertainty we publish: 0.879–1.837
GPa against ±0.119; a method gap exceeding the quoted Tg uncertainty in 54% of fits; a ~6 pp field
effect against a 0.28 pp noise floor. The workflow fix generalizes past these three instances — **any
fit or protocol choice not recorded in `decided_params` should be swept and reported, not defaulted.**
That is a concrete, checkable change to the pipeline, and it is what the reviewer's "conflate
stochastic sampling uncertainty with protocol effects" objection is pointing at.

**One free analysis serves three separate purposes.** The replicate-set protocol audit and
size/equilibration stratification answers the reviewer's ¶4 (separate stochastic from protocol
variance), supplies ¶5's per-run gate disposition table, and decides whether our density deficit is
PCFF or protocol — which determines whether test 1's funded arms are worth running at all. It costs
no GPU time and should run first for that reason alone.

**They discipline the force-field selection design.** Test 1 is the first real execution of the
selection funnel: stage 0 buildability is now mechanized (`ff_capability.py`, verified on PMMA and
PEEK), and arm B/C/D is exactly the stage-3 cross-field spread. The design's central commitment —
that for a polymer with no experimental value the honest output is the *spread* across defensible
fields, not a single number — is what makes the reviewer's "hypothesis, not demonstrated mechanism"
objection answerable rather than fatal. If arms B–D disagree by 6%, that spread is the result.

**They set the sequencing.** Test 4's recovery definition depends on gates from tests 2 and 3; test
1's funded legs depend on its own free leg not having already explained the deficit. So the order is:
all free legs → test 1 funded arms on PMMA → tests 2/3 funded axes → test 4. Running test 4 first
would measure agent performance against gates we already know are miscalibrated.

**The honest risk.** The free legs are likely to *widen* published uncertainties and shrink the
slope-gate pass rate to zero. That weakens specific claims while strengthening the manuscript's
central one — that the workflow's uncertainty accounting is trustworthy. The reviewer scored the
science 7 and importance 8; the gap is credibility of the error bars, not ambition, and these tests
close it by making the error bars larger and correct rather than small and wrong.
