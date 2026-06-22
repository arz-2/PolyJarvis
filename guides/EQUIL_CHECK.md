# Equilibration Check Guide
**Read when:** You are `equilibration-checker` and need to validate the equil chain and extract density.
**Scope:** Equilibration quality check + density extraction only.

---

## Rule: Always Pass `output_dir` and `graphs_dir`

Default `output_dir` scatters files into subdirectories next to the input log. Always pass both:

```python
output_dir = "/home/alexzhao/PolyJarvis/data/<run_name>/raw/"
graphs_dir = "/home/alexzhao/PolyJarvis/data/<run_name>/graphs/"
```

Tools that produce PNG figures (always pass `graphs_dir`):
- `check_equilibration_comprehensive` → `equilibration_convergence.png`
- `extract_equilibrated_density` → density plateau PNG

---

## Tool: `check_equilibration_comprehensive`

Returns `overall_pass` verdict and a ready-to-paste D-05 markdown block. Copy `result["d05_markdown"]` directly into run_log.md as the D-05 CONVERGENCE DETAIL section.

`backbone_types` is **REQUIRED** — from `inspect_data_file()`; do not guess.

**Thermo and structural checks read different files — this is deliberate.** The tool decouples Section A (thermo, from `log_file`) from Sections B/C (chain conformation + spatial, from `dump_file`):
- `log_file` = `npt_prod_log_path` — the production NPT log (`npt_prod300` glassy / `npt_production` rubbery), where density/energy convergence is meaningful.
- `dump_file` = `melt_dump_path` — the **melt** `nvt_production.dump` (T_workflow, chains mobile), where C(t)/MSD/Rg/R_ee actually report chain relaxation. Do **not** point this at the production NPT dump: for a glassy polymer the production state is below Tg, so C(t) never decays and MSD shows a kinetic trap *by construction* — the structural check would be meaningless. `gen_prompt.py` already resolves all three paths; use them verbatim, do not construct them.

**`ct_min_decay_melt` may be `null`.** When the prompt gives a number, pass it as `ct_min_decay` (C(t) becomes a hard gate). When it is `null` (aromatic main-chain classes — PSU/PEEK/PC/Kapton/PPS/PPV — where the backbone path cannot be defined by atom-type selection, so C(t)/C∞ are meaningless), **omit `ct_min_decay` entirely**: C(t)/C∞ are then reported as advisory warnings and never block `overall_pass`. This is the property-aware default that prevents the spurious aromatic-backbone FAIL; do not hand-override it back on.

**Call signature:**
```python
kwargs = dict(
    log_file=npt_prod_log_path,   # npt_prod300.log (glassy) or npt_production.log (rubbery)
                                  # → thermo convergence: density/energy drift + block-SEM
    dump_file=melt_dump_path,     # nvt_production.dump — always the MELT dump, both phases
                                  # → structural checks: C(t)/MSD/Rg/R_ee on MOBILE chains
                                  # Do NOT use npt_prod300.dump — chains are frozen below Tg
    data_file=equil_data_path,
    backbone_types=backbone_types,
    output_dir=output_dir,
    graphs_dir=graphs_dir,
)
if ct_min_decay_melt is not None:        # null ⇒ aromatic main chain: leave C(t) advisory
    kwargs["ct_min_decay"] = ct_min_decay_melt
check_equilibration_comprehensive(**kwargs)
```

**Key result fields:**
- `overall_pass` — True/False gate
- `d05_markdown` — ready-to-paste run_log.md block
- `density_converged`, `energy_converged`, `ct_decayed`
- `warnings` — list of soft warnings (non-fatal)

**C(t) and R_ee numeric fields** (extract from result dict — all from a single `check_equilibration_comprehensive` call):
- `result["chain"]["ct"]["decay_fraction_at_end"]`  → `ct_decay_fraction` (0.0–1.0)
- `result["chain"]["ct"]["tau_relax_ps"]`            → `ct_tau_relax_ps` (KWW chain relaxation time in ps)
- `result["chain"]["ree"]["mean_R_ee_A"]`            → `end_to_end_r_mean_A`
- `result["chain"]["ree"]["std_R_ee_A"]`             → `end_to_end_r_std_A`
- `result["chain"]["ree"]["n_chains"]`               → `end_to_end_n_chains`
- Histogram PNG auto-saved to `graphs_dir/end_to_end_distribution.png`
- C(t)/MSD/R_ee are computed on the melt dump in both phases, so `ct_decay_fraction` and `ct_tau_relax_ps` are always populated (no N/A rubbery branch)

For PHYC class (PE): `ct_decayed=True` plus `tau_relax_ps` is the chain relaxation evidence R1M10 requires. Include both in the RESULT block even for passes.

---

## Tool: `extract_equilibrated_density`

**Call signature:**
```python
extract_equilibrated_density(
    log_file=npt_prod_log_path,
    output_dir=output_dir,
    graphs_dir=graphs_dir,
    eq_fraction=0.5,                 # discard first 50% as burn-in (default)
    target_temp=npt_prod_temp_K,     # production temperature from prompt — filter to those rows if log is multi-T
)
```

**Result fields:**
- `plateau_density_mean`, `plateau_density_std` — primary output
- `plateau_step_range` — verify plateau starts after compression ramp ends
- `naive_mean`, `naive_std` — compare to plateau for sanity

Density passes if `plateau_density_mean` is within ±5% of experimental; flag if outside ±10%.

---

## Common Failures

**`check_equilibration_comprehensive` returns `overall_pass=False`:**
- Convergence failure (density drift, energy not plateaued) → return `EXTEND`
- Hard structural failure (box collapse, charge imbalance, C(t)=0% for a rubbery class) → return `FAIL`

**`extract_equilibrated_density` returns implausibly low density (<0.5 g/cm³):**
The NPT production log may contain the compression ramp rather than the production plateau. Verify `plateau_step_range` starts after the ramp ends. Increase `eq_fraction` to 0.7.

**`overall_pass=False` on a glassy DP≥30 system blocked SOLELY by melt chain-self-diffusion (C(t) decay, MSD, MSID slope, Rg chain-chain CV):** This is NOT a FAIL. Rigid-aromatic (PKTN/PEEK) and high-DP glassy melts have τ_relax ~10⁹ ps — terminal relaxation is unreachable in MD and a 1–2 ns EXTEND cannot move C(t). Per `decision_policy.json:require_glassy`, gate on the STRUCTURAL set only (density plateau in range, density-homogeneity CV<0.25, P2<0.10, thermo drift/SEM); the four chain-diffusion metrics are ADVISORY (non-blocking). Do not loop EXTEND. Flag the dynamic-relaxation lower-bound caveat (Tg over-estimate, K low) in the run summary.
