# Bulk Modulus Analysis Guide
**Read when:** You are `bulk-modulus-extractor` and need to extract bulk modulus from simulation output.
**Scope:** Extraction only — 3 routing paths. No simulation submission, no Monitor calls, no `generate_run_summary`.

---

## Rules

`output_dir`/`graphs_dir` are required on every extraction tool and provided in your prompt — pass
them verbatim.

Inspect which inputs are non-null in your prompt to route:

| Condition | Tool | Method | JSON written |
|-----------|------|--------|-------------|
| `murnaghan_log_files` non-null | `extract_bulk_modulus_murnaghan` + `extract_bulk_modulus` (diagnostic) — call both together in one message, not sequentially | `murnaghan` | `bulk_modulus_murnaghan.json` |
| `deform_log_path` non-null | `extract_bulk_modulus_deform` | `deformation` | `bulk_modulus_deform.json` |
| all null | `extract_bulk_modulus` | `fluctuation` | `bulk_modulus.json` |

- **Glassy (`is_glassy=True`):** Murnaghan at 300 K is primary; single-direction deform (with a paired slow-rate rate-sensitivity check, when `deform_log_path_slow` is present) is the fallback when Murnaghan fails (`fit_converged=False` or `B0_prime` outside [4, 20]).
- **Rubbery (`is_glassy=False`):** Murnaghan at T>Tg is primary (rubbery classes ship `bm_pressures_atm`). Volume fluctuation overestimates rubbery K (~+70%) — keep it only as the diagnostic B_dyn cross-check, never the reported K when Murnaghan is present. The pure-fluctuation (all-null) path applies only to a rubbery class with no `bm_pressures_atm`.

**Interpretation:**
- PDIE / rubbery Murnaghan: `B0′` 7–10 is normal for polydienes; `B_def` R²≈0 is expected for soft rubber (P vs ln V nonlinear at this scale), not an anomaly — `warning_bdef_unreliable` is standard.
- Deform rate-sensitivity WARNING (`K` differs >10% between rates): trust the slow-rate fit if `fit_r2_C11_rate2 ≥ 0.90` — the tool already auto-substitutes it into `K_GPa`/`method` when so (`method: "uniaxial_deformation_slow_rate"`); just surface the flag, don't re-derive it.
- Even when the tool substitutes the slow-rate fit (`method: "uniaxial_deformation_slow_rate"`), still report `bulk_modulus_method: deformation` in the RESULT block — never invent a new method label; note the substitution in `notes`.

---

## Workflow

### `extract_bulk_modulus_deform` (glassy fallback)

```python
extract_bulk_modulus_deform(
    log_file=deform_log_path,
    strain_rate=strain_rate_per_fs,   # from prompt
    strain_max=K_strain_max,          # from prompt (~0.03)
    eq_steps=200000,                  # N_EQ_STEPS from npt_deform.in
    strain_start=0.002,               # skip initial transient
    output_dir=output_dir,
    graphs_dir=graphs_dir,
    # rate-sensitivity check — only when the orchestrator ran the paired slow-rate leg:
    log_file_2=deform_log_path_slow,      # None if not present
    strain_rate_2=strain_rate_slow_per_fs,  # None if not present
)
```

**Result fields:** `C11_GPa`, `C12_GPa`, `K_GPa`, `G_GPa`, `E_GPa`, `nu_Poisson`, `fit_r2_C11`,
`fit_r2_C12_yy`, `isotropy_delta_pct`, `avg_window_frames`, `stress_strain_csv`, `summary_json`,
`rate_sensitivity` (present only when `log_file_2` was passed — see Interpretation above).
- `avg_window_frames` (default 2000): R² is on the smoothed stress series — correct, since raw thermal noise (~0.2 GPa) swamps the elastic signal (~0.09 GPa at 3% strain). Judge quality by `isotropy_delta_pct` + physical plausibility of K/G/E, not raw R².

**Acceptance:**
- `fit_r2_C11` and `fit_r2_C12_yy` ≥ 0.90; K > 0.
- `isotropy_delta_pct` < 20% — **hard gate** (C12_yy vs C12_zz within this single run). If ≥ 20%, flag K BORDERLINE.
- **G<0 in y/z is NOT a hard failure.** On small amorphous cells C11<C12 in some directions → negative shear G, but K=(C11+2C12)/3 averages transverse stresses and stays robust. Report K as `bulk_modulus_GPa` if `isotropy_delta_pct<20%` and both fit_r²≥0.90; report G and E as-is, noting "G<0 — small-cell anisotropy; K robust."

**Report:** `fit_r2_C11`, `fit_r2_C12_yy`, `isotropy_delta_pct`, `avg_window_frames`, and (if present) `rate_sensitivity.verdict`. If `isotropy_delta_pct` ≥ 20%, add WARNING "K BORDERLINE — anisotropy exceeds 20%; Murnaghan should have been primary".

### `extract_bulk_modulus_murnaghan`

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
- **B0′ out of [4, 20] with `fit_converged=True` is WARNING, not FAIL** (the ±1000 atm span under-constrains curvature): high B0′≥13 with r²<0.999 = EOS-nonlinearity artifact (K still correct); low B0′<4 with r²≥0.999 = under-constrained curvature (K robust). Note the artifact in `notes`.
- **Rubbery:** flag any Murnaghan-vs-fluctuation divergence >15% prominently; fluctuation is often more reliable for low-K rubber at ±1000 atm.

**Report:** `bulk_modulus_sem_GPa`, `r_squared`, `B0_prime`.

### `extract_bulk_modulus` (fluctuation)

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

- `volume_equilibrated=false` → flag WARNING.
- `B_def R² < 0.1` → cross-check unusable; report K_dyn only.

**Report:** `bulk_modulus_sem_GPa`, `n_effective_samples`, `tau_eff_frames`, `tau_eff_fraction`.
