# Tg Analysis Guide
**Read when:** You are `tg-analysis-worker` and need to extract thermal properties from a Tg sweep log.
**Scope:** `extract_thermal` (single-rate) or run the injected `extract_tg_multirate.py` command (multi-rate). No equil/density/BM work.

---

## Rule A: Never report Tg without checking fit quality

Rated independently on R² and F-stat; overall is the stricter of the two:

| R² | F-stat p-value | Quality | Action |
|---|---|---|---|
| ≥ 0.99 | < 0.001 | EXCELLENT | Report with confidence |
| ≥ 0.97 | < 0.01 | GOOD | Report with confidence |
| ≥ 0.90 | < 0.05 | ACCEPTABLE | Report with caveat |
| < 0.90 | ≥ 0.05 | POOR | Do not report — investigate |

`Tg_K` vs `Tg_alternative_K` disagreement >20 K means the transition region is noisy or the sweep range is too narrow — investigate before reporting.

---

## Tool: `extract_thermal`

```python
extract_thermal(
    log_file=tg_log_path,        # the Tg sweep log (prompt key is tg_log_path)
    tg_data_file=tg_data_file,   # for ΔCp mass normalisation
    enthalpy_col=enthalpy_col,
    output_dir=output_dir,
    graphs_dir=graphs_dir,
)
```
Non-obvious optional params (rest are schema defaults):
- `equilibration_fraction` — 0.5 for 2 ns/T, 0.7 for large/slow systems. Minimum 4 clean temperature bins.
- `initial_tg_guess` (K) — hint for the secondary curve_fit only; the primary F-stat method is guess-free.

**Result fields to report:**
- `Tg_K`, `Tg_alternative_K`, `r_squared`, `fit_quality`
- `cte_glassy_per_K`, `cte_rubbery_per_K` — CTE sanity: α_r/α_g ≈ 2–3 (flag if outside 1.5–5)
- `dCp_J_per_g_K`, `dCp_status` — if `dCp_status` is "skipped" (Enthalpy column absent), report N/A; do NOT re-run the sweep for this alone
- `n_plateaus_skipped_drift`, `n_temperature_bins`, `temp_range_K`

**Red flags — investigate before reporting:**
- `fit_quality` POOR / R² < 0.90; or `Tg_K` vs `Tg_alternative_K` disagree by >20 K; or Tg outside ±50 K of experimental.
- **Delocalized transition:** when `tg_uncertainty_K ≈ transition_width_c_K` and both >150 K, a high-r²/EXCELLENT fit can still be a spurious primary fit to under-equilibrated high-T plateaus (e.g. PLA2 r100: primary 516 K vs alternative 379 K matching the density slope). Also check `relaxation_metrics`: high-T plateaus with `n_eff < 5` + `relax_warning=true` signal the same contamination. Cross-check the density slope; if the primary is >80 K from exp — or >50 K above exp with the alternative closer — flag SUSPECT, verdict WARNING, recommend the alternative + fresh equilibration.

---

## Common Failures

**"fewer than 4 temperature bins":** sweep range too narrow, T_STEP too large, log incomplete, or too many plateaus excluded for drift (`n_plateaus_skipped_drift`).

**`Tg_K` vs `Tg_alternative_K` disagree by >20 K:** noisy density or range doesn't bracket the transition — increase N_STEPS_PER_T or extend range.

**`fit_quality` POOR despite a clean log:** plot `tg_density_bins.csv`; check for velocity re-init discontinuities (Tg-sweep Rule A) and `n_plateaus_skipped_drift`.

**"Bilinear curve_fit failed":** parse the sweep log's Temp column. If it spans <~100 K or collapses to a single bin, the log is a defective single-isothermal run (no staircase) — return FAIL, recommend regenerating the sweep. Do NOT tune `initial_tg_guess`.
