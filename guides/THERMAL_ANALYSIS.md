# Tg Analysis Guide
**Read when:** You are `tg-analysis-worker` and need to extract thermal properties from a Tg sweep log.
**Scope:** `extract_thermal` — the default single-rate path.

---

## Rules

**Fit quality** — rated independently on R² and F-stat; overall is the stricter of the two:

| R² | F-stat p-value | Quality | Action |
|---|---|---|---|
| ≥ 0.99 | < 0.001 | EXCELLENT | Report with confidence |
| ≥ 0.97 | < 0.01 | GOOD | Report with confidence |
| ≥ 0.90 | < 0.05 | ACCEPTABLE | Report with caveat |
| < 0.90 | ≥ 0.05 | POOR | Do not report — investigate |

**Reportability** — `extract_thermal` emits `tg_gate_verdict`; use it directly rather than
re-deriving reportability from the numbers:
- `TG_REPORTABLE` — report the Tg.
- `TG_REVIEW` — `tg_method_gap_K` (|`Tg_K` − `Tg_alternative_K`|) exceeds 20 K: the transition region
  is noisy or the sweep range too narrow. Investigate before reporting. `method_gap_exempt` is
  always passed to `extract_thermal` from the prompt's value; when that value is `true` the class
  has documented highest-rate degeneracy, so the gap is recorded as a reason without forcing REVIEW.
- `TG_NOT_REPORTABLE` — `fit_quality=POOR` or `primary_fit_invalid`. Do not report the Tg. This blocks
  *reporting* only; the `is_glassy` routing in THERMAL_TRACK.md may still fall back to the plan's
  experimental Tg.

Read `tg_gate_reasons` into the D-06 row verbatim. `dCp_weak_step_flag` is informational.

**CTE sanity:** α_r/α_g ≈ 2–3 (flag if outside 1.5–5).

**Delocalized transition:** when `tg_uncertainty_K ≈ transition_width_c_K` and both >150 K, a high-r²/EXCELLENT fit can still be a spurious primary fit to under-equilibrated high-T plateaus (e.g. PLA2 r100: primary 516 K vs alternative 379 K matching the density slope). Also check `relaxation_metrics`: high-T plateaus with `n_eff < 5` + `relax_warning=true` signal the same contamination. Cross-check the density slope; if the primary is >80 K from exp — or >50 K above exp with the alternative closer — flag SUSPECT, verdict WARNING, recommend the alternative + fresh equilibration.

---

## Workflow

### `extract_thermal`

Pass every argument below on every call, including the ones whose value is null or false.
Omitting one is a schema error, not a default.

```python
extract_thermal(
    log_file=tg_log_path,        # the Tg sweep log (prompt key is tg_log_path)
    tg_data_file=tg_data_file,   # for ΔCp mass normalisation — omitted, ΔCp is skipped entirely
    per_t_dump_file=per_t_dump_file,  # one frame per T step; with tg_data_file it enables the
                                      # structural block (per-T Rg/P2, Rg-kink Tg)
    backbone_types=backbone_types,    # P2 is null at every T without it; Rg and Tg_dynamic_K
                                      # still compute, so a null shows up as a partial block
    enthalpy_col=enthalpy_col,
    method_gap_exempt=method_gap_exempt,   # pass the false too, never omit
    output_dir=output_dir,
    graphs_dir=graphs_dir,
)
```
Non-obvious optional params (rest are schema defaults):
- `equilibration_fraction` — 0.5 for 2 ns/T, 0.7 for large/slow systems. Minimum 4 clean temperature bins.
- `initial_tg_guess` (K) — hint for the secondary curve_fit only; the primary F-stat method is guess-free.

**Result fields to report:**
- `Tg_K`, `Tg_alternative_K`, `r_squared`, `fit_quality`
- `cte_glassy_per_K`, `cte_rubbery_per_K`
- `dCp_J_per_g_K`, `dCp_status` — if `dCp_status` is "skipped" (Enthalpy column absent), report N/A; do NOT re-run the sweep for this alone
- `n_plateaus_skipped_drift`, `n_temperature_bins`, `temp_range_K`
- `structural_analysis_status`, `Tg_dynamic_K` — report the status verbatim; "skipped"/"partial" means the block did not fully run, not that the structure is fine
