# Murnaghan and Tg: proposed protocol fixes

Proposal, not adopted policy. Scope is archive-wide; cis-PBD1 was the trigger, not the subject.
Every number is measured — refits of the archive's own stored `volumes_A3` / `tg_values_K` — or
Monte Carlo on those measured dispersions. Nothing here is applied.

---

# Plain-language summary

## The one problem underneath both

Neither K nor Tg is something the simulation measures directly. Both are numbers read off a
curve fitted to a handful of measured points. So three things decide the answer: the data, the
shape of curve you fit, and how far past the data you read.

Only the first of those gets an error bar. The reported uncertainty counts random scatter in
the data and nothing else — not the curve shape, not the fitting range, not which of two
defensible methods was used. Those unrecorded choices turn out to be the *larger* term in both
properties.

That matters for cost as well as correctness. The pipeline's instinct when a number disagrees
with experiment is to buy more simulation, which reduces random scatter. Random scatter was
already the small term. The wall time was being aimed at the wrong error.

---

## Part 1 in plain terms — bulk modulus

**What K is and how it's obtained.** K is how hard the material is to squeeze. You squeeze the
simulated cell at several pressures, record the volume at each, fit a curve through the points,
and read the slope at *zero* pressure. The reported number is not one of the measured points —
it is an extrapolation off the end of the curve.

**What went wrong.** Polymers stiffen enormously under compression. cis-PBD1 was squeezed to
15,000 atmospheres, where it was six times stiffer than at ambient. Fitting one simple curve
across that whole range and then extrapolating back to zero means the high-pressure points —
where the material behaves like a different substance — are pulling the answer. That is why K
moved between 1.61 and 1.84 GPa depending only on how much of the high-pressure data was
included, against a stated error bar of ±0.12.

**M1 — fit the curve the right way round.** Fitting requires deciding which axis carries the
noise. The simulation *sets* the pressure exactly and *measures* the volume with scatter, so the
noise is in volume. The code assumed the reverse. *Improvement:* the fit finally matches how the
data was produced. Worth ≤0.5% on narrow pressure ranges and 8.3% on cis-PBD1's — larger than
the error bar it reports.

**M2 — don't squeeze so hard.** Stay in the pressure range where the material still behaves the
way it does at ambient. That is also the range the experimental values were measured in, so it
is a fair comparison. Most of the archive already does this; PDIE and PEG are the exceptions.
*Improvement:* three things at once — the answer stops depending on arbitrary choices (spread
falls from 8.3% to ~0.9%), the comparison with experiment becomes like-for-like, and it is
cheaper, since PDIE drops from six squeeze simulations to five.

**M3 — say how much the curve shape mattered.** Fit both standard curve shapes and report how
far apart they land, alongside the existing error bar. *Improvement:* the stated uncertainty
starts including a real source of uncertainty it currently ignores. Usually this adds about 1%,
which is precisely why it is cheap to carry — and on the few bad fits it is 12–18%.

**M4 — one free sanity check.** The Tait curve has a shape parameter that is nearly the same
number (~0.089) for essentially every polymer. If a fit returns something far from that, the
data did not pin the curve down. *Improvement:* costs nothing and catches fits that pass every
current check — archived PEG3 returned 80 instead of 0.089 and was accepted.

**M5 — drop the top point and refit.** If K moves by more than its own error bar, the curve is
not describing the data and the extrapolation is carrying the misfit. *Improvement:* catches
exactly the failure that hit cis-PBD1, using data already on disk.

**M6 — don't reach for Birch–Murnaghan.** It is built for crystals; here it returned 0.879 GPa
and a physically impossible shape parameter. Recorded so the option is not revisited.

**Net effect on cis-PBD1:** K becomes 1.62 ± 0.04 GPa, +17% over experiment instead of +33%.
It still fails the comparison — but now it fails by an amount that means something.

---

## Part 2 in plain terms — glass transition

**What Tg is and why simulation gets it wrong.** Tg is the temperature where the polymer stops
being glassy and turns rubbery. In the lab it is measured cooling at about 10 K per minute. A
simulation cannot afford that and cools roughly a billion times faster. Cooling faster always
pushes the measured Tg higher, so the simulated value is systematically too high — not because
anything is broken, but because it is a different measurement.

**The standard fix, and why it does not work here.** The accepted repair is to run three
different cooling rates, plot Tg against rate, draw a line, and extend it down to lab speed.
Two facts kill it:

1. The rates used sit close together — 40 to 160 K/ns is less than one factor of ten. Across
   that range the real change in Tg is only about 2–3 degrees.
2. Measuring Tg from any single cooling run scatters by about **17 degrees**.

You are trying to see a 2-degree trend with measurements that wobble by 17. Simulating it: to
have a reasonable chance of detecting the trend you would need to vary the cooling rate over
roughly **24 factors of ten**. About 2 is affordable.

**The evidence it is already failing.** All six archived runs whose slope "passed" report rate
effects of 12 to 112 degrees per factor of ten, where the physics is 3 to 5. They are fitting
noise. Each used three points to fit two numbers, which leaves one point of slack — enough that
a near-perfect-looking fit is essentially guaranteed regardless of the data.

**T1 — stop paying for extra cooling rates.** *Improvement:* one such attempt costs about 28
GPU-hours and returns a number that is noise. This is a direct saving, and it stops the pipeline
publishing a fitted rate dependence it cannot support. It also corrects the rung-pricing check
shipped on 2026-08-11, which currently recommends buying exactly this.

**T2 — look the correction up instead of measuring it.** The rate effect is a well-established
3–5 degrees per factor of ten. *Improvement:* free, and it works. Applied to cis-PBD1 it says
the simulation should read 34–57 degrees above the lab value, i.e. 208–231 K. It read 220. That
is a successful validation obtained at zero cost, from the same data on which the expensive
method returned nothing.

**T3 — commit to the fitting method before seeing the answer.** *Improvement:* on cis-PBD1 the
two available methods gave 220 K and 175 K, and the worker recommended 175 because it matched
the experimental 174. Writing the method into the plan up front makes that impossible rather
than merely discouraged. The flag to do it already exists.

**T4 — alarm on the right quantity.** The current alarm fires when two fitting methods disagree
by more than 20 degrees, which happens on 60% of runs. An alarm that fires on most runs is not
an alarm; it is the normal state, and each one costs a human decision. What it is really
detecting — a broad, smeared transition — is already measured and written into the same file.
*Improvement:* alarm on the measured width instead. It becomes rare and informative, and most
runs stop needing a human.

**T5 — stop quoting a precision that is not there.** In over half the archived fits, the quoted
uncertainty on Tg is smaller than the disagreement between two fits of the same data. Report the
larger. *Improvement:* removes the possibility of passing or failing a comparison with
experiment on precision the run does not have — the mechanism behind more than one past
misgrading.

**T6 — if Tg time is spent, spend it holding each temperature longer, not on more rates.**
Flagged as an untested hypothesis: the archive has no controlled comparison, and one rerun at
double the dwell would settle it.

---

# Part 1 — Murnaghan

## The problem

K is not a measurement; it is the P→0 limit of a fitted EOS. Three choices set it, none of them
recorded: ladder width, fit orientation, and EOS form. On cis-PBD1's 1–15000 atm ladder those
three span **0.879 → 1.837 GPa** — a factor of two — against a reported ±0.119 GPa (6.5%).

| EOS form (cis-PBD1) | 1–15000 atm | 1–5000 atm |
|---|---|---|
| Murnaghan, P(V) — as shipped | **1.837** | 1.628 |
| Murnaghan, V(P) | 1.685 | 1.619 |
| Tait, free C | 1.593 | 1.586 |
| Tait, universal C=0.0894 | 1.709 | 1.655 |
| Birch–Murnaghan 3rd order | 0.879 | 1.406 |

Narrowing the ladder collapses the disagreement. **The spread is a symptom of ladder width, not
of EOS choice** — which is why the fixes below are mostly about the ladder.

## M1 — Fit V(P), not P(V)

`extract_bulk_modulus_murnaghan.py` minimizes residuals in P with V as the independent variable.
In an NPT ladder the pressure is *set* and the volume is *measured*; the errors are in V. The
orientation is backwards.

Impact: ≤0.5% on narrow ladders, 8.3% on cis-PBD1's. One-line change, and it makes the quoted
uncertainty mean what it says.

## M2 — Bring the wide ladders back to the narrow one that already works

The archive's ladders, by frequency:

| runs | ladder (atm) | 3-model spread |
|---|---|---|
| 16 | `[-1000, -500, 0, 500, 1000]` | ~0.9% median |
| 7 | `[1, 100, 300, 600, 1000]` | ~0.9% median |
| 7 | `[-1000, 0, 1500, 3000, 5000]` | ~1.9% median |
| 4 | `[-1000, 0, 3000, 7000, 15000]` | ~1.9% median |
| 2 | `[1, 500, 1000, 2000, 5000]` | — |
| — | cis-PBD1: `[1, 1000, 2500, 5000, 10000, 15000]` | **8.3%** |

The narrow ±1000 atm ladder is both the majority default and the one that works. It is also the
range the experimental comparators live in — Mark's PVT K_T values are Tait fits over roughly
0–200 MPa, so a narrow ladder is comparator-matched as well as better-conditioned.

The ask is therefore **not a new default**: keep `[-1000, -500, 0, 500, 1000]`, and bring PDIE's
and PEG's wide ladders back to it. Signal is ample there — ΔV between 1 and 1000 atm is 4.8%
against a 0.27% per-point volume SD, ~14:1. Cost falls: per-pressure wall time is uniform
(1449–1506 s across cis-PBD1's six points), so PDIE drops from six points to five.

**Do not shrink to 3 points.** Three points against three free parameters is exactly determined
(r² = 1.000000); the apparent orientation-independence is interpolation, not agreement.

## M3 — Report a model-spread term alongside B0_sem

Fit Murnaghan and Tait; report max−min as a second uncertainty component. Refitting all 37
archived Murnaghan runs both orientations plus Tait:

- median 3-model spread **0.9%** on narrow ladders (Pmax < 0.2 GPa, n=24), **1.9%** on wide (n=13)
- the outliers are exactly the runs whose quoted SEM is already the largest in the set:
  PE3 12.3%, PEG3 18.0%, cis-PBD3 8.2%, PEG4 7.4%

Usually negligible — which is why it is cheap to always report, and why it is worth having when
it is not.

## M4 — Gate on the fitted Tait C

Tait's C is near-universal at 0.0894 for polymers; the archive's fitted median is 0.0808. It is a
free, sensitive conditioning diagnostic: archived **PEG3 fits C = 80.2**, a 900× violation, on a
fit the current gate passed. C outside roughly [0.04, 0.18] means the ladder does not constrain
the EOS, whatever r² says.

## M5 — Ladder-truncation sensitivity when Pmax > 0.5 GPa

Refit without the top pressure point. If B0 moves by more than B0_sem, one EOS form is being
asked to span a stiffening range it cannot and the P→0 extrapolation is carrying the misfit.
cis-PBD1 fails this badly: 1.837 (n=6) → 1.680 (n=5) → 1.628 (n=4), while K itself rises 6× along
the ladder (secant 2.08 GPa at 1–1000 atm → 12.71 GPa at 10000–15000 atm).

## M6 — Birch–Murnaghan is not a candidate

Finite-Eulerian-strain form for crystalline solids. On the wide ladder it returned B0′ = 28 and
K0 = 0.879 GPa. Recorded so the option is closed rather than revisited.

## Effect on cis-PBD1's headline

Narrow ladder, any of the three polymer-appropriate forms: **K ≈ 1.59–1.66 GPa**, i.e.
**1.62 ± 0.04 (model) GPa**, +17% over exp 1.38. The FAIL verdict survives — 1.62 is still
outside the 1.241–1.517 band — but +33% does not.

---

# Part 2 — Tg

## The finding that reframes the rest

The multi-rate extrapolation is not underpowered at the margin. **It is unmeasurable by an order
of magnitude**, and no archived run has ever produced a physically credible slope.

Fitting log-linear Tg(ln Γ) to each archived multirate run and taking the residual SD:

| quantity | archive value |
|---|---|
| per-rate residual SD (median, 23 runs) | **17.0 K** (range 0.2–102.9) |
| rate span actually used (median) | **0.6 decades** |
| true rate signal over that span at 3–5 K/decade | **2–3 K** |

**The six runs that pass the `b>0, r²≥0.5` slope gate all fail on physics.** `loglinear_slope_K`
is stored per **ln**, not per decade; converting (×2.303) against a physical 3–5 K/decade:

| run | b (K/decade) | r² | n | residual dof | σ |
|---|---|---|---|---|---|
| PE3 | 111.6 | 0.987 | 3 | 1 | 5.6 K |
| PE4 | 36.7 | 0.999 | 3 | 1 | 0.4 K |
| PEG1 | 12.5 | 1.000 | 3 | 1 | 0.2 K |
| PS3 | 25.7 | 0.673 | 3 | 1 | 12.8 K |
| PS4 | 111.6 | 0.558 | 3 | 1 | 42.3 K |
| cis-PBD2 | 5.1 | 1.000 | 2 | **0** | 0.0 K |

Every one is 2.5–22× too steep, and the only near-physical value has zero residual degrees of
freedom. At n=3 there is 1 residual dof, so r²=0.999 is not evidence of anything. The honest pass
rate is **0/25**, not 6/25. Vogel–Fulcher never converged either: 0/25 well-constrained (ten
POOR, thirteen FAILED, two skipped).

**How much span would be needed.** Monte Carlo, n=3 log-spaced rates, true slope 4 K/decade,
detection at t≥3 with the correct sign:

| span (decades) | σ=5 K | σ=10 K | σ=17 K |
|---|---|---|---|
| 0.6 (archive median) | 15% | 12% | 12% |
| 2 | 29% | 18% | 15% |
| 8 | 85% | 53% | 33% |
| 24 | 100% | 97% | 80% |

Span for 80% power: **7.5 decades at σ=5 K, 14.5 at σ=10, 24 at σ=17.** A feasible span is about
1.5–2 decades. The gap is a factor of 4–12 even in the most optimistic case.

This subsumes several separately-logged footguns — PEST `b<0`, PACR floor violation,
near-zero-r² slopes passing the gate. They are one phenomenon.

## T1 — Make the slope rung conditional, and expect it never to be purchasable

This corrects what shipped on 2026-08-11. `remedy_economics.py` on cis-PBD1's real state returns
`SPEND, one rung` — buy the multirate slope. That rung would cost ~28 GPU-h to measure a quantity
the data cannot resolve. The check prices a rung's *cost* correctly and assumes its *measurement*
will succeed.

Proposed precondition, evaluated before the rung is offered:

> The slope rung is purchasable only if `span_decades ≥ span_for_80pct_power(σ, b=4)`, with σ
> taken from the single-sweep fit instability already in hand — the method gap is the available
> pre-purchase proxy.

cis-PBD1's method gap is 45 K, at the top of the archive's σ distribution, so it fails the
precondition — and that is knowable *before* spending anything. No archived run clears it either.
Note also that a small σ estimated from n=3 (1 dof) is a lucky draw, not a measurement, so a low
σ should not by itself unlock the purchase.

## T2 — Report MD Tg at a stated rate; apply the rate offset as an annotation, not a fit

The rate offset is a known physical constant (3–5 K/decade). Used as an annotation it is free
and, on cis-PBD1, stronger evidence than any extrapolation this pipeline can fit: 40 K/ns against
DSC 10 K/min is 11.4 decades, predicting +34 to +57 K, i.e. 208–231 K against exp 174 K — and the
measured 220.2 K lands inside that window. That is a validation of the MD result at zero GPU cost.

Corollary already in the record: never grade a single-rate MD Tg against a DSC value as
agreement. It is a different observable.

## T3 — Pre-register the fit method per class

`extract_thermal.py` already takes `--fit_method {auto,hyperbola,bilinear}`. Choosing after
seeing which fit agrees with experiment is the documented failure mode, and cis-PBD1's worker
recommended exactly that (175.0 K, "matches exp within 1 K").

Pin it in `polymer_rules.json` at plan time. Hyperbola is the defensible default: it carries an
explicit width parameter, and where the transition is broad the bilinear model is misspecified —
it forces a kink onto data with no kink, which is why it lands 45 K away.

## T4 — Replace the method-gap gate with a transition-width gate

The gate fires on `|Tg_primary − Tg_alt| > 20 K`. Across 81 clean archived single-rate fits:

- **60% (49/81) exceed 20 K.** A gate that halts the majority of runs to human review is not a
  gate, it is a default.
- median gap 29.3 K, median transition width 49.8 K
- corr(width, gap) = 0.49; median gap 34.7 K where width > 50 K vs 19.3 K where width ≤ 50 K

The gap is a noisy proxy for a quantity already measured directly and reported in the same JSON
(`transition_width_c_K`). Gate on the width.

Better still, gate on whether a break exists at all. The free-breakpoint SSE scan run by hand on
cis-PBD1 is the right test and is cheap to mechanize: sweep the split point, and if SSE is flat in
it while the fitted Tg slides continuously (172 → 257 K there), no unique Tg exists in the data
and no fit choice will produce one.

## T5 — Set a Tg uncertainty floor

Quoted `tg_uncertainty_K` (median 19.3 K) is exceeded by the same fit's own method gap in **54%**
of archived fits. Report `max(fit uncertainty, method gap, ~17 K reproducibility floor)`. Quoting
an MD Tg to better than about ±20 K is not supportable in this pipeline; cis-PBD1's r²=0.9997 /
±8.9 K against a 45.2 K gap is the illustration.

## T6 — If Tg wall time is spent, spend it on dwell, not on rates (untested)

σ per rate is 17 K; the rate signal over a purchasable span is 2–3 K. Longer per-T dwell and
denser bins through the transition attack σ; more rates do not. This is a hypothesis, not a
result — the archive has no controlled dwell comparison. It is cheap to test: rerun one sweep at
2× dwell and see whether σ and the transition width fall.
