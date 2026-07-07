# Bulk Modulus Analysis Guide
**Read when:** You are `bulk-modulus-extractor` and need to extract bulk modulus from simulation output.
**Scope:** Extraction only — 3 routing paths. No simulation submission, no Monitor calls, no `generate_run_summary`.

`output_dir`/`graphs_dir` are required on every extraction tool and provided in your prompt — pass
them verbatim. **Distinct `output_dir` per parallel deform call** (each x/y/z direction or rate):
two calls sharing one `output_dir` silently overwrite `bulk_modulus_deform.json` +
`stress_strain.csv` — use `.../raw/deform_x/`, `.../deform_y/`, … (match `graphs_dir`).

---

## Routing

Inspect which inputs are non-null in your prompt:

| Condition | Tool | Method | JSON written |
|-----------|------|--------|-------------|
| `murnaghan_log_files` non-null | `extract_bulk_modulus_murnaghan` + `extract_bulk_modulus` (diagnostic) | `murnaghan` | `bulk_modulus_murnaghan.json` |
| `deform_log_path` non-null | `extract_bulk_modulus_deform` | `deformation` | `bulk_modulus_deform.json` |
| all null | `extract_bulk_modulus` | `fluctuation` | `bulk_modulus.json` |

- **Glassy (`is_glassy=True`):** Murnaghan at 300 K is primary; 3-direction deform is the fallback when Murnaghan fails (`fit_converged=False` or `B0_prime` outside [4, 20]).
- **Rubbery (`is_glassy=False`):** Murnaghan at T>Tg is primary (rubbery classes ship `bm_pressures_atm`). Volume fluctuation overestimates rubbery K (~+70%) — keep it only as the diagnostic B_dyn cross-check, never the reported K when Murnaghan is present. The pure-fluctuation (all-null) path applies only to a rubbery class with no `bm_pressures_atm`.

**Interpretation:**
- PDIE / rubbery Murnaghan: `B0′` 7–10 is normal for polydienes; `B_def` R²≈0 is expected for soft rubber (P vs ln V nonlinear at this scale), not an anomaly — `warning_bdef_unreliable` is standard.
- Deform inverted rate ordering (fast-rate K < slow-rate K): thermal noise dominates the small-strain fit at 10× rate. Trust the slow run; flag if `isotropy_delta` > 10%.

---

## Tool: `extract_bulk_modulus_deform` (glassy fallback)

```python
extract_bulk_modulus_deform(
    log_file=deform_log_path,
    strain_rate=strain_rate_per_fs,   # from prompt
    strain_max=K_strain_max,          # from prompt (~0.03)
    eq_steps=200000,                  # N_EQ_STEPS from npt_deform.in
    strain_start=0.002,               # skip initial transient
    output_dir=output_dir,
    graphs_dir=graphs_dir,
)
```

**Result fields:** `C11_GPa`, `C12_GPa`, `K_GPa`, `G_GPa`, `E_GPa`, `nu_Poisson`, `fit_r2_C11`,
`fit_r2_C12_yy`, `isotropy_delta_pct`, `avg_window_frames`, `stress_strain_csv`, `summary_json`.
- `avg_window_frames` (default 2000): R² is on the smoothed stress series — correct, since raw thermal noise (~0.2 GPa) swamps the elastic signal (~0.09 GPa at 3% strain). Judge quality by `isotropy_delta_pct` + physical plausibility of K/G/E, not raw R².

**Acceptance:**
- `fit_r2_C11` and `fit_r2_C12_yy` ≥ 0.90; K > 0.
- `isotropy_delta_pct` < 20% — **hard gate**. If ≥ 20%, flag K BORDERLINE. For 3-direction deform, check cross-direction `K_std/K_mean` < 20% instead.
- **G<0 in y/z is NOT a hard failure.** On small amorphous cells C11<C12 in some directions → negative shear G, but K=(C11+2C12)/3 averages transverse stresses and stays robust. Report K_mean as `bulk_modulus_GPa` if cross-direction K_std/K_mean<20% and all fit_r²≥0.90; report G and E from the x-direction only, and note "G<0 y/z — small-cell anisotropy; K_mean robust." (The tool's per-direction `isotropy_delta_pct` — C12_yy vs C12_zz within one direction — is a DIFFERENT metric from cross-direction K spread; check the latter manually.)

**Report:** `fit_r2_C11`, `fit_r2_C12_yy`, `isotropy_delta_pct`, `avg_window_frames`. If `isotropy_delta_pct` ≥ 20%, add WARNING "K BORDERLINE — anisotropy exceeds 20%; Murnaghan should have been primary".

---

## Tool: `extract_bulk_modulus_murnaghan`

```python
extract_bulk_modulus_murnaghan(
    log_files=murnaghan_log_files,   # from prompt, one per pressure
    pressures_atm=bm_pressures_atm,  # from prompt, matching log_files order
    eq_fraction=0.5,
    output_dir=output_dir,
    graphs_dir=graphs_dir,
)
```

**Result fields:** `bulk_modulus_GPa` (=B0, the reported K), `B0_prime` (dK/dP), `V0_A3`,
`r_squared`, `fit_converged`, `bulk_modulus_sem_GPa`, `method` ("murnaghan" | "linear_fallback"), `warnings`.

**Acceptance:**
- `fit_converged=True` (linear_fallback = EOS curvature not resolved → WARNING).
- `r_squared ≥ 0.999` for a 5-point series; lower → poor equilibration at some pressure.
- **B0′ out of [4, 20] with `fit_converged=True` is WARNING, not FAIL** (the ±1000 atm span under-constrains curvature): high B0′≥13 with r²<0.999 = EOS-nonlinearity artifact (K still correct); low B0′<4 with r²≥0.999 = under-constrained curvature (K robust). Note the artifact; route to deform fallback or a wider pressure series.
- **Rubbery:** flag any Murnaghan-vs-fluctuation divergence >15% prominently; fluctuation is often more reliable for low-K rubber at ±1000 atm.

**Report:** `bulk_modulus_sem_GPa`, `r_squared`, `B0_prime`.

---

## Tool: `extract_bulk_modulus` (fluctuation)

```python
extract_bulk_modulus(
    log_file=npt_prod_log_path,
    eq_fraction=0.5,
    block_count=5,
    output_dir=output_dir,
    graphs_dir=graphs_dir,
)
```

**Result fields:** `bulk_modulus_GPa`, `bulk_modulus_sem_GPa`, `isothermal_compressibility_per_Pa`,
`V_mean_A3`, `V_std_A3`, `tau_eff_frames`, `tau_eff_fraction`, `n_effective_samples`, `diagnostics`.

**Volume drift:**
- `volume_equilibrated=false` → re-run with `eq_fraction=0.25`; bracket between that and `K_block_mean_GPa`. Flag WARNING.
- `B_def R² < 0.1` → cross-check unusable; report K_dyn only.

**Report:** `bulk_modulus_sem_GPa`, `n_effective_samples`, `tau_eff_frames`, `tau_eff_fraction`.

---

## Common Failures

**`extract_bulk_modulus` K < 0.1 or > 20 GPa:** not fully equilibrated (`diagnostics.drift_check` warns) — raise `eq_fraction` to 0.7.

**`extract_bulk_modulus_murnaghan` K < 0 or `fit_converged=False`:** EOS not resolved — check `volume_equilibrated` per pressure. Glassy: narrow to ±500 atm if ±1000 causes creep. `linear_fallback` underestimates K — add pressure points.

**`extract_bulk_modulus_murnaghan` B0_prime outside [4, 20]:** pressure range too wide (glass yielding) or too narrow (curvature not captured). Route to deform fallback.

**`extract_bulk_modulus_deform` fit_r2 < 0.90:** noisy stress-strain — check THERMO_FREQ ≤ 100; strain rate may be too high (try the slow-rate comparison if `K_deform_rate_slow_inv_s` is set).

**`extract_bulk_modulus_deform` isotropy_delta_pct ≥ 20%:** too small / not isotropic. 3-direction: acceptable if K_std/K_mean < 20%. Single-direction: BORDERLINE — Murnaghan should have been primary.
