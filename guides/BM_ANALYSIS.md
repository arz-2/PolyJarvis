# Bulk Modulus Analysis Guide
**Read when:** You are `bulk-modulus-extractor` and need to extract bulk modulus from simulation output.
**Scope:** Extraction only — 4 routing paths. No simulation submission, no Monitor calls, no `generate_run_summary`.

---

## Routing

Inspect which inputs are non-null in your prompt:

| Condition | Tool | Method | JSON written |
|-----------|------|--------|-------------|
| `murnaghan_log_files` non-null | `extract_bulk_modulus_murnaghan` + `extract_bulk_modulus` (diagnostic) | `murnaghan` | `bulk_modulus_murnaghan.json` |
| `deform_log_path` non-null | `extract_bulk_modulus_deform` | `deformation` | `bulk_modulus_deform.json` |
| all null | `extract_bulk_modulus` | `fluctuation` | `bulk_modulus.json` |

**Born+NVT has been removed from the pipeline.** `born_matrix_file` and `born_log_path` are always null in standard runs. Do not call `extract_bulk_modulus_born`. See `guides/BORN_MATRIX.md` for the removal rationale (PCFF+PPPM virial incompatibility, failed 3/3 pipeline runs).

Only one path runs per invocation. The `murnaghan` path additionally calls `extract_bulk_modulus(npt_prod_log)` in parallel for a diagnostic B_dyn cross-check (write to same `output_dir`; not the reported K).

**Glassy (is_glassy=True) path:** Murnaghan at 300 K is primary (murnaghan_log_files non-null). 3-direction deform is fallback when Murnaghan fails (`fit_converged=False` or `B0_prime` outside [4, 20]).

**Rubbery (is_glassy=False) path:** Murnaghan at T>Tg is now the **primary** rubbery K method — the rubbery classes (PHYC/PDIE/POXI/PSIL) all ship `bm_pressures_atm` in polymer_rules.json, so the plan emits a murnaghan stage. Volume fluctuation overestimates rubbery K (~+70%, PEG2 2026-06-23) and is kept ONLY as the diagnostic B_dyn cross-check (`extract_bulk_modulus`), never the reported K when Murnaghan is present. The pure-fluctuation path (all-null) now applies only to a rubbery class with no `bm_pressures_atm` defined — add one to polymer_rules.json rather than relying on fluctuation.

---

## Rule: Always Pass `output_dir` and `graphs_dir`

Always pass both to every extraction call:

```python
output_dir = "/home/arz2/PolyJarvis/data/<run_name>/raw/"
graphs_dir = "/home/arz2/PolyJarvis/data/<run_name>/graphs/"
```

Tools that produce PNG figures:
- `extract_bulk_modulus_deform` → `stress_strain.png`
- `extract_bulk_modulus_murnaghan` → `murnaghan_eos.png`
- `extract_bulk_modulus` → `volume_fluctuations.png`

Omitting `output_dir` means JSON files land next to the input log — `generate_run_summary` won't find them.

---

## Tool: `extract_bulk_modulus_deform`

Use for glassy polymers (fallback when Murnaghan fails) — stress-strain fit from `npt_deform` log.

**Call signature:**
```python
extract_bulk_modulus_deform(
    log_file=deform_log_path,
    strain_rate=strain_rate_per_fs,   # K_deform_rate_inv_s × 1e-15 (from prompt)
    strain_max=K_strain_max,          # from prompt (class default ~0.03)
    eq_steps=200000,                  # N_EQ_STEPS used in npt_deform.in
    strain_start=0.002,               # skip initial transient
    output_dir=output_dir,
    graphs_dir=graphs_dir,
)
```

**Acceptance criteria:**
- Both `fit_r2_C11` and `fit_r2_C12_yy` ≥ 0.90
- K > 0 and G > 0
- `isotropy_delta_pct` < 20% — **hard gate**. If ≥ 20%, flag K as BORDERLINE (lower confidence). This is not advisory; a 24% anisotropy (PVC1) means C12_yy and C12_zz disagree by ~25%, so K = (C11 + C12_yy + C12_zz)/3... ± 12%, which is unreliable. For 3-direction deform runs, check K_std/K_mean < 20% instead.

**Result fields:**
- `C11_GPa`, `C12_GPa`, `K_GPa`, `G_GPa`, `E_GPa`, `nu_Poisson`
- `fit_r2_C11`, `fit_r2_C12_yy`, `isotropy_delta_pct`
- `avg_window_frames` — rolling-average window applied to stress before fitting (default 2000 frames). The R² values are on the smoothed series, which is correct: raw thermal noise (~0.2 GPa at THERMO_FREQ=100) swamps the elastic signal (~0.09 GPa at 3% strain). High R² on smoothed data is meaningful; raw R² is not. The real quality indicators are `isotropy_delta_pct` and the physical plausibility of K, G, E (PVC1: K=1.68 GPa is low; PEEK1: K=3.53 GPa is plausible).
- `stress_strain_csv`, `summary_json`

**Reporting (R1M9):** Report `fit_r2_C11`, `fit_r2_C12_yy`, `isotropy_delta_pct`, and `avg_window_frames`. If `isotropy_delta_pct` ≥ 20%, include WARNING "K estimate is BORDERLINE — anisotropy exceeds 20%; Murnaghan path should have been primary".

---

## Tool: `extract_bulk_modulus_murnaghan`

Use for rubbery polymers with `bm_pressures_atm` set — Murnaghan EOS fit to multi-pressure NPT series.

**Call signature:**
```python
extract_bulk_modulus_murnaghan(
    log_files=murnaghan_log_files,    # list of absolute paths, one per pressure (from prompt)
    pressures_atm=bm_pressures_atm,  # list matching log_files order (from prompt)
    eq_fraction=0.5,                  # discard first 50% of each log as burn-in
    output_dir=output_dir,
    graphs_dir=graphs_dir,
)
```

**Result fields:**
- `bulk_modulus_GPa` (alias for B0_GPa — the reported K)
- `B0_prime` — pressure derivative of K (expected 7–11 for polymer melts)
- `V0_A3` — reference volume at zero pressure
- `r_squared` — EOS fit quality (expect ≥ 0.999 for 5-point series)
- `fit_converged` — True if scipy curve_fit converged; False → `method = linear_fallback`
- `bulk_modulus_sem_GPa` — bootstrap uncertainty (None if not available)
- `method` — "murnaghan" or "linear_fallback"
- `warnings`

**Acceptance:**
- `fit_converged=True` — linear_fallback means EOS curvature not resolved; flag as WARNING
- B0' in [4, 20] — outside this range is unphysical for polymers
- `r_squared ≥ 0.999` for a 5-point series; lower suggests poor equilibration at one or more pressures

**Reporting (include in RESULT block):** `bulk_modulus_sem_GPa`, `r_squared`, `B0_prime`

---

## Tool: `extract_bulk_modulus`

Use for rubbery polymers without `bm_pressures_atm` set (fluctuation path) — volume-fluctuation method from NPT log.

**Call signature:**
```python
extract_bulk_modulus(
    log_file=npt_prod_log_path,
    eq_fraction=0.5,    # use only the most stable portion
    block_count=5,      # blocks for uncertainty estimation
    output_dir=output_dir,
    graphs_dir=graphs_dir,
)
```

**Volume drift handling:**
- **`volume_equilibrated=false`:** Re-run with `eq_fraction=0.25`; bracket the result between this value and `K_block_mean_GPa`. Flag K as WARNING.
- **`B_def R² < 0.1`:** Cross-check is not usable; report K_dyn only.

**Result fields:**
- `bulk_modulus_GPa`, `bulk_modulus_sem_GPa`
- `isothermal_compressibility_per_Pa`
- `V_mean_A3`, `V_std_A3`
- `tau_eff_frames`, `tau_eff_fraction`, `n_effective_samples`
- `diagnostics` — T, P, density means + volume drift check

**Reporting (include in RESULT block):** `bulk_modulus_sem_GPa`, `n_effective_samples`, `tau_eff_frames`, `tau_eff_fraction`

---

## Common Failures

**`extract_bulk_modulus` gives unreasonable K (< 0.1 GPa or > 20 GPa):** Not fully equilibrated — `diagnostics.drift_check` will warn. Increase `eq_fraction` to 0.7.

**`extract_bulk_modulus_murnaghan` returns K < 0 or `fit_converged=False`:** EOS not resolved — volume may not be equilibrated at one or more pressure points. Check `volume_equilibrated` per pressure point. For glassy polymers, narrow the pressure range (±500 atm) if ±1000 atm causes creep. `method = "linear_fallback"` means EOS curvature not resolved — add more pressure points. The linear fallback underestimates K for soft rubbery systems; for glassy systems it is particularly unreliable.

**`extract_bulk_modulus_murnaghan` gives B0_prime outside [4, 20]:** Pressure range is too wide (glass yielding at high compression) or too narrow (EOS curvature not captured). Typical glassy polymer at ±1000 atm: B0_prime ~7–12. Route to deform-worker fallback.

**`extract_bulk_modulus_deform` fit_r2 < 0.90:** Stress-strain data is noisy. Check THERMO_FREQ in the deform log (should be ≤ 100 for dense output). May also indicate strain rate too high — try the slow-rate comparison if `K_deform_rate_slow_inv_s` is non-null in prompt.

**`extract_bulk_modulus_deform` isotropy_delta_pct ≥ 20%:** System is too small or not isotropic. For 3-direction deform (x+y+z), this is acceptable if K_std/K_mean < 20% across directions. For single-direction (x-only), flag as BORDERLINE — the Murnaghan path should have been primary.
