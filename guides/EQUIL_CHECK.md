# Equilibration Check Guide
**Read when:** You are `equilibration-checker` and need to validate the equil chain and extract density.
**Scope:** Equilibration quality check + density extraction only.

---

## Tool: `check_equilibration_comprehensive`

Returns `overall_pass` and a ready-to-paste `d05_markdown` block.

`backbone_types` is **REQUIRED** — do not guess, and your toolset has no `inspect_data_file`.
Extract from the `.data` file with Bash: read the **Masses** section
(`awk '/^Masses/,/^Atoms/' file.data`), pick heavy backbone atoms (C≈12, O≈16, N≈14), never
hydrogens (mass 1.008); cross-check the Bonds section (backbone types appear in
chain-continuing bonds) when side-group heavies (e.g. carbonyl O) could be confused with
backbone ones. E.g. PEEK = `[1,2,5]` (aromatic C + ether O); `[3,4]` are H → degenerate R_ee/P2.

**Call signature:**
```python
kwargs = dict(
    log_file=npt_prod_log_path,   # production NPT log → thermo convergence (density/energy drift + block-SEM)
    dump_file=melt_dump_path,     # MELT nvt_production.dump (both phases) → C(t)/MSD/Rg/R_ee on mobile chains.
                                  # NOT the production dump: below Tg C(t) never decays (meaningless by construction)
    data_file=equil_data_path,
    backbone_types=backbone_types,
    output_dir=output_dir,
    graphs_dir=graphs_dir,
)
if ct_min_decay_melt is not None:        # null ⇒ aromatic main chain: leave C(t) advisory, do NOT pass ct_min_decay
    kwargs["ct_min_decay"] = ct_min_decay_melt
check_equilibration_comprehensive(**kwargs)
```

**Result fields for the RESULT block** (all from this single call):
- `overall_pass`, `d05_markdown`, `density_converged`, `energy_converged`, `ct_decayed`, `warnings`
- `result["chain"]["ct"]["decay_fraction_at_end"]` → `ct_decay_fraction`
- `result["chain"]["ct"]["tau_relax_ps"]` → `ct_tau_relax_ps`
- `result["chain"]["ree"]["mean_R_ee_A"|"std_R_ee_A"|"n_chains"]` → `end_to_end_r_mean_A` / `_std_A` / `_n_chains`
- C(t)/MSD/R_ee are computed on the melt dump in both phases, so `ct_decay_fraction`/`ct_tau_relax_ps` are always populated.

For PHYC (PE): include `ct_decayed` + `tau_relax_ps` in the RESULT block even on passes.

---

## Tool: `extract_equilibrated_density`

```python
extract_equilibrated_density(
    log_file=npt_prod_log_path,
    output_dir=output_dir,
    graphs_dir=graphs_dir,
    eq_fraction=0.5,                 # discard first 50% as burn-in
    target_temp=npt_prod_temp_K,     # filter to production-T rows if log is multi-T
)
```
Primary output: `plateau_density_mean` ± `plateau_density_std`. Verify `plateau_step_range`
starts after the compression ramp. Density passes within ±5% of experimental; **below −5% is
BINDING, not a soft warning.**

### Convergence ≠ correctness — under-anneal check before accepting a low density

A converged density proves the cell stopped moving, not that it stopped at the right value: an
under-annealed glass converges perfectly at a too-low density (free volume frozen in on
cooling). So when a glassy 300 K density is below −5%, decompose melt vs cooling before any verdict:

```
assess_cooling_contraction(
    melt_data  = <npt_production_out.data>,   # melt at T_equil
    glass_data = <npt_prod300_out.data>,      # glass at 300 K
    exp_density_gcm3 = <class exp density>, tg_K = <Tg>, t_equil_K = <T_workflow>)
```
Route on `verdict`:
- **`UNDER_ANNEALED_COOLING`** (melt OK, under-contracted on cooling) → return `RE-ANNEAL` (re-melt + slow re-cool, see EQUILIBRATION.md). Do NOT `EXTEND` at 300 K, do NOT accept as FF bias — it's fixable.
- **`MELT_STAGE_DEFICIT`** (melt already low, or rubbery) → FF underbinding or melt-stage under-annealing. Accept as "FF bias" ONLY with the `assess_cooling_contraction` evidence pasted into D-05 and flagged unresolved.
- **`extrapolation_reliable=False`** (cooling span >300 K, e.g. PEEK) → split is indicative only; prefer `RE-ANNEAL`, lean on absolute glass-vs-exp density.

---

## Verdict routing (Common Failures)

**`overall_pass=False`:**
- Density still drifting / energy not plateaued → `EXTEND` (more NPT at the SAME T).
- Converged but glassy density below −5% → NOT `EXTEND`; run `assess_cooling_contraction` → `RE-ANNEAL` for `UNDER_ANNEALED_COOLING`. Symptom: SEM tiny AND ~5–7% low AND MSD kinetic-trap flagged.
- Box collapse / charge imbalance / C(t) exactly 0% (dead cell) → `FAIL`. (C(t) decaying-but-incomplete is reptation-limited, not a FAIL — see carve-outs.)

**Blocked SOLELY by chain-diffusion/reptation metrics** (C(t) decay, MSD, τ_relax, MSID slope,
Rg CV): NOT a FAIL, NOT an EXTEND — unreachable in MD at finite DP, and EXTEND cannot move them.
- Glassy DP≥30 (`is_glassy`, e.g. PKTN/PEEK): per `require_glassy`, gate on the STRUCTURAL set only (density plateau in range, homogeneity CV<0.25, P2<0.10, thermo drift/SEM). Flag the dynamic-relaxation lower-bound caveat (Tg over-estimate, K low).
- Rubbery (`regime: rubbery`, e.g. PHYC/PDIE/POXI): per `require_rubbery`, gate ONLY on density block-SEM<2% AND homogeneity CV<25% AND energy drift/SEM. Return `PASS` even with `overall_pass=False`.

**`extract_equilibrated_density` returns <0.5 g/cm³:** log likely contains the compression ramp — verify `plateau_step_range` after the ramp; raise `eq_fraction` to 0.7.

**Marginal density-homogeneity CV in [24.5%, 25.5%] on a small DP<30 aromatic cell:**
Poisson-limited finite-size noise, not underpacking. Route `EXTEND` (not FAIL) when density
SEM<0.5% and drift p significant; FAIL only if SEM>1% or drift p>0.05. A co-marginal Rg
chain-chain CV (~36%) on the same small cell is the same finite-size noise — treat as
marginal→EXTEND, never a standalone FAIL.

**`check_equilibration_comprehensive` hangs on a large dump (>~1 GB / >1000 frames):**
trajectory I/O can time out. Do NOT block the verdict: rely on `extract_equilibrated_density`
plus the most recent pre-extension comprehensive result — the structural metrics cannot have
moved over a 2 ns 300 K extension of an already-equilibrated cell.
