---
name: n-eff-density-tau-inflation
description: n_eff_density fails on a raw (non-detrended) tau that one in-window random-walk excursion inflates 3x — test size-invariance with detrended tau + sigma~1/sqrt(N), and size the EXTEND from the fact that the re-gate scores the extension stage alone, halved
metadata:
  type: feedback
---

`thermo.n_eff_density` = `n_production_rows / tau_rows`, and `tau_rows =
tau_eff_density_fraction * n_production_rows` is a **raw** integrated autocorrelation — a single
low-frequency density excursion of order sigma inside the window inflates it 3-4x. Reproduce it
before believing it: parse `<stage>/<stage>.log` (dt=1 fs, `thermo 1000` => 1 row = 1 ps), Sokal
auto-windowed ACF on the last-50% window matches the gate to ~20%.

**Is a tau rise a real size effect? Three tests, PEEK1 8-chain (8720 at) vs 17-chain (18530 at),
both 770 K melt, both 751-row windows (2026-08-12):**
1. **Detrended tau** — 8.6 ps vs 8.9 ps, identical. Raw tau 11.5 -> 33.2 ps (gate: 12.0 -> 39.6
   rows). The whole "rise" is one in-window excursion; global density tau is set by the barostat
   (`Pdamp` in time units, N-independent), so it should *not* scale with cell size.
2. **sigma_rho ~ 1/sqrt(N)** — 0.834% -> 0.600%, ratio 0.73 vs sqrt(8720/18530)=0.686. Equilibrium
   NPT volume fluctuation in both cells.
3. **Same mean state** — melt density 1.0392 vs 1.0401 g/cm3 (0.09% apart), C(t) tau *shorter* in
   the big cell, MSD alpha 0.296 -> 0.318. A less-equilibrated larger cell would move all three.

**Do NOT use block-SEM as an independent n_eff.** `(sigma/SEM)^2` only works if the block scan has
plateaued; PEEK1's rose monotonically (25/50/75/100 ps -> 0.058/0.070/0.081/0.097%), so the gate's
`density_sem` is whatever block size it used, and `(0.600/0.0806)^2 = 55` is not evidence. An
unconverged rising block-SEM argues *for* a low-frequency component, not against.

**Sizing the EXTEND — the gate's formula under-sizes ~2x.** The re-gate scores the **extension
stage alone, halved** (archived precedent: `npt_extend` 1.5 ns -> 1501 rows -> 751 production;
every PEEK1 check used exactly half). So n_eff_at_regate ~ `500 * extend_ns / tau_rows`, and
`extend_ns = 1.5 * n_eff_min/n_eff` (1.67 ns at 18/20) yields only n_eff 21.5 at the observed
tau — 7% margin. Recommend 2.5 ns (n_eff 31.6, covers tau up to 62 rows), stating the gate value as
the floor it derives from; that is a refinement of the formula, not an override. Never propose a
larger `eq_fraction`/full-window re-score as the alternative action — changing the estimator on the
one check that failed makes it incomparable to the ones that passed.

**Archived-attempt comparator trap:** after a REBUILD, `attempt1_*/raw/equilibration_comprehensive
.json` (unsuffixed) is the **last** check written — on PEEK1 that was `npt_prod300`, the 300 K glass
(phase=full). The melt comparator is the suffixed `.melt_pass.json` / `.premelt_extend.json`. An
injected symptom quoting "0.0138 on the old cell" was quoting the 300 K glass against a 770 K melt.
Always confirm `log_file` + `meta.T_mean` on any JSON you compare across attempts, and put the
correction in `root_cause` — it changes which comparison governs.

**Ladder budget:** recover.md's "Cap 2 extensions **per gate** (`phase=full`/`phase=melt`
independent budgets)" — the parenthetical *is* the definition: per phase gate, never per failing
metric. A REBUILD-LARGER resets it with the trajectory. A repeat n_eff shortfall must not escalate
to rung 3 (different force field); a sampling deficit is not an FF problem.

**Friction hit on this diagnosis, and codebase improvements worth raising with the user:**
- The reviewer had to kill two arguments I had drafted: the block-SEM `(sigma/SEM)^2 = 55` one
  (above), and a "re-score at a larger `eq_fraction`" alternative that I had wanted to put in
  `notes`. Anything offered in `notes` gets taken as a free path — never surface a cheaper action
  there unless it is one you would defend as the verdict.
- `check_equilibration_comprehensive` already computes a tau; computing `n_eff_density` from the
  **raw** one lets a single stationary excursion fail the gate on a physically converged cell.
  Detrending before the ACF sum (or reporting raw *and* detrended, with n_eff from the smaller)
  would have avoided a ~7 GPU-h extension here. Same tool, same root defect as
  [[marginal-density-drift-autocorrelation]]'s OLS p-value.
- recover.md's `n_eff_density` row hands over the gate's `extend_ns = 1.5 * n_eff_min/n_eff`
  verbatim, but the re-gate scores only half the new stage — the formula should carry the factor 2,
  or the row should say "size so that `0.5 * extend_ns * 1000 / tau_rows >= 2 * n_eff_min`".
- Archived-attempt gate JSONs are suffixed by *outcome* (`.melt_pass`, `.premelt_extend`) with the
  unsuffixed name left holding whichever check ran last — suffixing by stage/phase instead would
  remove the cross-attempt comparator trap above.
- Disk sat at 55 GB free (under recover.md's 60 GB guard) with 12.7 GB of equil dumps present, so
  every EXTEND recommendation on a long chain needs a `df` + a delete list attached; the retention
  policy (keep nvt/npt_production only) is not applied automatically at stage exit.

Related: [[marginal-density-drift-autocorrelation]], [[diagnosis-tooling-friction]]
