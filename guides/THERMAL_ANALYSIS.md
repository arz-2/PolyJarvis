# Tg Analysis Guide
**Read when:** You are `tg-analysis-worker` and need to extract thermal properties from a Tg sweep log.
**Scope:** `extract_thermal` only. Equilibration check, density, and bulk modulus extraction are handled by separate workers.

---

## Rule A: Never Report Tg Without Checking Fit Quality

**Fit quality tiers** — rated independently on R² and F-stat; overall is the stricter of the two:

| R² | F-stat p-value | Quality | Action |
|---|---|---|---|
| ≥ 0.99 | < 0.001 | EXCELLENT | Report with confidence |
| ≥ 0.97 | < 0.01 | GOOD | Report with confidence |
| ≥ 0.90 | < 0.05 | ACCEPTABLE | Report with caveat |
| < 0.90 | ≥ 0.05 | POOR | Do not report — investigate |

`Tg_K` vs `Tg_alternative_K`: disagreement >20 K means the transition region is noisy or the sweep range is too narrow. Investigate before reporting.

---

## Rule B: Always Pass `output_dir` and `graphs_dir`

```python
output_dir = "data/<run_name>/raw/"
graphs_dir = "data/<run_name>/graphs/"
```

---

## Tool: `extract_thermal`

Key params:
- `log_file` — path to the Tg sweep log
- `tg_data_file` — LAMMPS .data file from the Tg sweep input; required for ΔCp mass normalisation
- `initial_tg_guess` (K) — hint for secondary curve_fit; primary F-stat method is guess-free
- `equilibration_fraction` — 0.5 (default) for 2 ns/T; 0.7 for large/slow systems. Minimum 4 clean temperature bins required.
- `output_dir`, `graphs_dir` — always pass both

**Result fields to report:**
- `Tg_K`, `Tg_alternative_K`, `r_squared`, `fit_quality`
- `cte_glassy_per_K`, `cte_rubbery_per_K`
- `dCp_J_per_g_K`, `dCp_status`
- `n_plateaus_skipped_drift`, `n_temperature_bins`, `temp_range_K`

If `dCp_status` contains "skipped (column 'Enthalpy' not in log)" — report N/A; do not re-run the sweep for this alone.

**CTE sanity check:** α_r / α_g ≈ 2–3 (flag if outside 1.5–5).

**ΔCp:** Requires `tg_data_file` for mass normalisation. Reports `dCp_status: "skipped"` if file absent or Enthalpy column missing from log.

---

**Red flags — investigate before reporting:**
- `fit_quality` POOR or R² < 0.90
- `Tg_K` and `Tg_alternative_K` disagree by >20 K
- Tg outside ±50 K of experimental
- **Delocalized transition:** when `tg_uncertainty_K ≈ transition_width_c_K` and both >150 K, a high r²/EXCELLENT fit can mask a spurious primary Tg fit to under-equilibrated high-T plateaus (PLA2 r100: primary 516 K vs alternative 379 K matching the density slope). Cross-check the density slope; if the primary is >80 K from exp, flag it SUSPECT, set verdict WARNING, and recommend the alternative + fresh equilibration.

---

## Common Failures

**`extract_thermal` fails with "fewer than 4 temperature bins":** Sweep range too narrow, T_STEP too large, log incomplete, or too many plateaus excluded for excessive drift (check `n_plateaus_skipped_drift`).

**`Tg_K` and `Tg_alternative_K` disagree by >20 K:** Noisy density data or range doesn't bracket the transition — increase N_STEPS_PER_T or extend range.

**`fit_quality` is POOR despite clean log:** Plot `tg_density_bins.csv` manually. Check for velocity re-initialization discontinuities (Tg sweep Rule A). Check `n_plateaus_skipped_drift`.

**`extract_thermal` returns "Bilinear curve_fit failed":** Parse the Temp column of the sweep log. If Temp spans < ~100 K total or collapses to a single bin, the log is a defective single-isothermal run (no staircase). Return FAIL and recommend regenerating the Tg sweep. Do NOT tune `initial_tg_guess` — that won't help.
