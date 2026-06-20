# Equilibration Check Guide
**Read when:** You are `equilibration-checker` and need to validate the equil chain and extract density.
**Scope:** Equilibration quality check + density extraction only.

---

## Rule: Always Pass `output_dir` and `graphs_dir`

Default `output_dir` scatters files into subdirectories next to the input log. Always pass both:

```python
output_dir = "/home/arz2/PolyJarvis/data/<run_name>/raw/"
graphs_dir = "/home/arz2/PolyJarvis/data/<run_name>/graphs/"
```

Tools that produce PNG figures (always pass `graphs_dir`):
- `check_equilibration_comprehensive` → `equilibration_convergence.png`
- `extract_equilibrated_density` → density plateau PNG

---

## Tool: `check_equilibration_comprehensive`

Returns `overall_pass` verdict and a ready-to-paste D-05 markdown block. Copy `result["d05_markdown"]` directly into run_log.md as the D-05 CONVERGENCE DETAIL section.

`backbone_types` is **REQUIRED** — from `inspect_data_file()`; do not guess.

**`ct_min_decay` usage:** Pass the value from the worker prompt (`ct_min_decay_melt`). Pass `None` for the NPT 300 K log (`npt_prod300`) and all rubbery polymer checks.

**Call signature:**
```python
check_equilibration_comprehensive(
    equil_log=equil_log_path,        # nvt_production.log — melt NVT at T_equil
    npt_log=npt_prod_log_path,       # npt_prod300.log — 300 K NPT
    dump_file=npt_prod_dump_path,
    data_file=equil_data_path,
    backbone_types=backbone_types,
    ct_min_decay=ct_min_decay_melt,  # from prompt; pass None for rubbery
    output_dir=output_dir,
    graphs_dir=graphs_dir,
)
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
- For rubbery classes (`ct_min_decay=None`): set `ct_decay_fraction` and `ct_tau_relax_ps` to N/A; R_ee is still available

For PHYC class (PE): `ct_decayed=True` plus `tau_relax_ps` is the chain relaxation evidence R1M10 requires. Include both in the RESULT block even for passes.

---

## Tool: `extract_equilibrated_density`

**Call signature:**
```python
extract_equilibrated_density(
    log_file=npt_prod_log_path,
    output_dir=output_dir,
    graphs_dir=graphs_dir,
    eq_fraction=0.5,       # discard first 50% as burn-in (default)
    target_temp=300.0,     # filter to 300 K rows if log is multi-T
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
- Convergence failure (density drift, energy not plateaued) → return `EXTEND` — orchestrator extends chain 1–2 ns and re-Monitors
- Hard structural failure (box collapse, charge imbalance, C(t)=0% for a rubbery class) → return `FAIL` — orchestrator writes UNRESOLVED

**`extract_equilibrated_density` returns implausibly low density (<0.5 g/cm³):**
The NPT production log may contain the compression ramp rather than the production plateau. Verify `plateau_step_range` starts after the ramp ends. Increase `eq_fraction` to 0.7.

**`overall_pass=False` on a glassy DP≥30 system blocked SOLELY by melt chain-self-diffusion (C(t) decay, MSD, MSID slope, Rg chain-chain CV):** This is NOT a FAIL. Rigid-aromatic (PKTN/PEEK) and high-DP glassy melts have τ_relax ~10⁹ ps — terminal relaxation is unreachable in MD and a 1–2 ns EXTEND cannot move C(t). Per `decision_policy.json:require_glassy`, gate on the STRUCTURAL set only (density plateau in range, density-homogeneity CV<0.25, P2<0.10, thermo drift/SEM); the four chain-diffusion metrics are ADVISORY (non-blocking). Do not loop EXTEND. Flag the dynamic-relaxation lower-bound caveat (Tg over-estimate, K low) in the run summary.
