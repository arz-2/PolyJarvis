# Stage 4: Analysis & Validation
**Read when:** You have simulation output and need to extract and validate properties

---

## Rules

### Rule A: Never Report Tg Without Checking Fit Quality

**Fit quality tiers** — rated independently on R² and F-stat; overall is the stricter of the two:

| R² | F-stat p-value | Quality | Action |
|---|---|---|---|
| ≥ 0.99 | < 0.001 | EXCELLENT | Report with confidence |
| ≥ 0.97 | < 0.01 | GOOD | Report with confidence |
| ≥ 0.90 | < 0.05 | ACCEPTABLE | Report with caveat |
| < 0.90 | ≥ 0.05 | POOR | Do not report — investigate |

`Tg_K` vs `Tg_alternative_K`: disagreement >20 K means the transition region is noisy or the sweep range is too narrow. Investigate before reporting.

### Rule B: Always Specify `atom_type_pairs` in `calculate_rdf`

`atom_type_pairs=None` computes all pairs and can exceed 2 GB RAM per frame for 10k-atom systems. Always pass explicit pairs.

### Rule C: Always Pass `output_dir` to Every Analysis Tool

Default `output_dir` for each tool scatters files into different subdirectories next to its input file. Always pass:

```python
output_dir = "/home/arz2/PolyJarvis/data/<run_name>/raw/"
```

Omitting `output_dir` means outputs land in `tg_analysis/`, `eq_comprehensive/`, `deform_analysis/`, etc. — `generate_run_summary` won't find them.

---

## Tool: `extract_tg`

Key params:
- `initial_tg_guess` (K) — hint for secondary curve_fit; primary F-stat method is guess-free
- `equilibration_fraction` — 0.5 (default) for 2 ns/T; 0.7 for large/slow systems. Minimum 4 clean temperature bins required.

**Result fields:**
- `Tg_K` — primary Tg from F-stat exhaustive split
- `Tg_alternative_K` — cross-check via scipy curve_fit bilinear
- `r_squared`, `f_statistic`, `f_statistic_pvalue`
- `fit_quality` — EXCELLENT / GOOD / ACCEPTABLE / POOR
- `n_plateaus_skipped_drift`, `n_temperature_bins`, `temp_range_K`
- `bins_csv` — path to `tg_density_bins.csv`

---

## Tool: `check_equilibration_comprehensive`

Returns `overall_pass` verdict and a ready-to-paste D-05 markdown block. Copy `result["d05_markdown"]` directly into run_log.md as the D-05 CONVERGENCE DETAIL section.

`backbone_types` is **REQUIRED** — from `inspect_data_file()`; do not guess.

Hard gates and soft warnings are identical to Stage 2 — see `STAGE_2_EQUILIBRATION.md`. If `overall_pass=False`, flag all properties as ⚠ but do not abort — report what failed.

---

## Tool: `extract_equilibrated_density`

Key params:
- `eq_fraction` — discard first N% as burn-in (default 0.5)
- `target_temp` — filter to a specific temperature if log is multi-T
- `plateau_shift_sigma` — sensitivity of plateau edge detection (default 1.0)

**Result fields:**
- `plateau_density_mean`, `plateau_density_std`, `plateau_density_sem`
- `plateau_n_points`, `plateau_fraction`, `plateau_step_range`
- `naive_mean`, `naive_std` — compare to plateau for sanity

---

## Tool: `extract_bulk_modulus`

Use for rubbery polymers (`is_glassy=False`) — volume-fluctuation method from NPT log.

Key params:
- `eq_fraction` — use only the most stable portion (default 0.5; increase if drifting)
- `block_count` — blocks for uncertainty estimation (default 5)

**Result fields:**
- `bulk_modulus_GPa`, `bulk_modulus_sem_GPa`
- `isothermal_compressibility_per_Pa`
- `V_mean_A3`, `V_std_A3`
- `diagnostics` — T, P, density means + volume drift check

---

## Tool: `extract_bulk_modulus_deform`

Use for glassy polymers (`is_glassy=True`) — stress-strain fit from npt_deform log.

Key params:
- `strain_rate` — in 1/fs (convert from `K_deform_rate_inv_s × 1e-15`)
- `strain_max` — from `polymer_rules.json`
- `eq_steps` — N_EQ_STEPS used in npt_deform.in (default 200000)
- `strain_start` — skip initial transient (default 0.002)

**Acceptance criteria:**
- Both `fit_r2_C11` and `fit_r2_C12_yy` ≥ 0.90
- K > 0 and G > 0
- `isotropy_delta_pct` < 20%

**Experimental ranges for common glassy polymers:**

| Polymer | K (GPa) | G (GPa) | E (GPa) |
|---------|---------|---------|---------|
| BPA-PC | 3–4 | 1.0–1.5 | 2.5–3.5 |
| PSU/Udel | 3–5 | 1.0–1.5 | 2.5–4.0 |
| Kapton (PIMD) | 4–6 | 1.5–2.5 | 4–7 |

**Result fields:**
- `C11_GPa`, `C12_GPa`, `K_GPa`, `G_GPa`, `E_GPa`, `nu_Poisson`
- `fit_r2_C11`, `fit_r2_C12_yy`, `isotropy_delta_pct`
- `stress_strain_csv`, `summary_json`

---

## Tool: `extract_end_to_end_vectors`

`backbone_types` is **REQUIRED** — always determine from `inspect_data_file()` output; do not assume. Incorrect types return wrong terminal atoms.

**Result fields:**
- `overall_mean_R` — mean end-to-end distance (Å)
- `overall_mean_R2` — mean ⟨R²⟩ (Å²)
- `per_chain` — list of per-chain stats: `mean_R`, `std_R`, `n_frames`
- `csv_file`

Large per-chain variance in R suggests poor equilibration.

---

## Tool: `calculate_rdf`

Always pass `atom_type_pairs` explicitly (Rule B). `data_file` is required for MDAnalysis topology.

**Result fields:**
- `rdf_files` — dict of pair → CSV path, e.g. `{"2-2": "/path/rdf_t2-t2.csv"}`
- `pairs_computed`

Expected peaks for PE: C-C first peak ~1.54 Å (bonded), second ~2.54 Å; convergence to g(r)=1 beyond ~10 Å.

---

## Tool: `unwrap_coordinates`

Use only when feeding dump files to external tools (OVITO, VMD) that don't handle image flags. Output file is same size as input — check disk space first.

**Result fields:** `output_file`, `frames_written`, `natoms`, `size_bytes`

---

## Final Step: `generate_run_summary`

Call after all analysis tools have completed. Reads every JSON in `output_dir`, assembles `run_summary.json` with sections: `run`, `decisions` (D-01–D-06), `results` (Tg/density/K with PASS/FAIL vs experiment), `convergence`, `structural_checks`, `artifacts` (all figure and CSV paths), `provenance`.

```python
generate_run_summary(
    output_dir   = "/home/arz2/PolyJarvis/data/<run_name>/raw/",
    run_name     = run_name,
    smiles       = smiles,
    polymer_class = polymer_class,
    ff           = ff,
    simulation_dir = sim_base,
    d05          = "PASS",        # from check_equilibration_comprehensive verdict
    d06          = fit_quality,   # from extract_tg result
    exp_tg_min   = exp_tg_range[0],
    exp_tg_max   = exp_tg_range[1],
    exp_density_min = exp_density_range[0],
    exp_density_max = exp_density_range[1],
    # ...other metadata from run_params
)
```

**Result fields:** `status`, `summary_json` (absolute path to `run_summary.json`)

---

## Validation Against Experimental Data

| Property | Acceptable Error | Source |
|---|---|---|
| Tg | ±20 K | Afzal 2021, Webb 2024 |
| Density | ±5% | Multiple studies |
| Thermal conductivity | ±30% | High uncertainty property |

| Polymer | Exp Tg | Exp Density (300K) |
|---|---|---|
| PE | ~195 K | ~0.85 g/cm³ |
| PS | ~373 K | ~1.05 g/cm³ |
| PMMA | ~378 K | ~1.18 g/cm³ |
| PEO/PEG | ~206 K | ~1.12 g/cm³ |

**Red flags — investigate before reporting:**
- Density outside ±10% of experimental
- Tg outside ±50 K of experimental
- R² < 0.90 on bilinear fit
- `Tg_K` and `Tg_alternative_K` disagree by >20 K
- RDF shows no clear peaks or does not converge to 1.0
- Large per-chain variance in end-to-end R

---

## Common Failures

**`extract_tg` fails with "fewer than 4 temperature bins":** Sweep range too narrow, T_STEP too large, log incomplete, or too many plateaus excluded for excessive drift (check `n_plateaus_skipped_drift`).

**`Tg_K` and `Tg_alternative_K` disagree by >20 K:** Noisy density data or range doesn't bracket the transition — increase N_STEPS_PER_T or extend range.

**`fit_quality` is POOR despite clean log:** Plot `tg_density_bins.csv` manually. Check for velocity re-initialization discontinuities (Stage 3 Rule A). Check `n_plateaus_skipped_drift`.

**`calculate_rdf` runs out of memory:** `atom_type_pairs=None` was used (Rule B), or `data_file` not passed.

**`extract_end_to_end_vectors` returns unreasonably large R:** `backbone_types` not set correctly — confirm from `inspect_data_file()`. Check dump includes image flags (ix, iy, iz).

**`check_equilibration_comprehensive` returns `overall_pass=False`:** Extend final NPT by 1–2 ns and re-run. Check `warnings` to identify which gate failed.

**`extract_bulk_modulus` gives unreasonable K:** Not fully equilibrated — `diagnostics.drift_check` will warn. Increase `eq_fraction`.

**`extract_tg` returns "Bilinear curve_fit failed":** Before retrying with different params, parse the Temp column of the sweep log. If Temp spans < ~100 K total or collapses to a single bin, the log is a defective single-isothermal run (no staircase). Return FAIL and recommend regenerating the Tg sweep. Do NOT tune `initial_tg_guess` — that won't help.


**C∞ > 15 warning for PE/PHYC:** This is soft INFO, not a gate failure. Semicrystalline-tendency PE at melt temperature legitimately sits at the top of the [3, 15] heuristic. Confirm conformational pass (Rg CV < 30%, MSID slope ≈ 1.0 ±20%, P2 < 0.10) and proceed.
