# Bulk Modulus Analysis Guide
**Read when:** You are `bulk-modulus-extractor` and need to extract bulk modulus from simulation output.
**Scope:** Extraction only — 4 routing paths. No simulation submission, no Monitor calls, no `generate_run_summary`.

---

## Routing

Inspect which inputs are non-null in your prompt:

| Condition | Tool | Method | JSON written |
|-----------|------|--------|-------------|
| `born_matrix_file` non-null | `extract_bulk_modulus_born` | `born_nvt` | `bulk_modulus_born.json` |
| `deform_log_path` non-null | `extract_bulk_modulus_deform` | `deformation` | `deform_analysis.json` |
| `murnaghan_log_files` non-null | `extract_bulk_modulus_murnaghan` + `extract_bulk_modulus` (diagnostic) | `murnaghan` | `bulk_modulus_murnaghan.json` |
| all null | `extract_bulk_modulus` | `fluctuation` | `bulk_modulus.json` |

Only one path runs per invocation. The `murnaghan` path additionally calls `extract_bulk_modulus(npt_prod_log)` in parallel for a diagnostic B_dyn cross-check (write to same `output_dir`; not the reported K).

---

## Rule: Always Pass `output_dir` and `graphs_dir`

Always pass both to every extraction call:

```python
output_dir = "/home/arz2/PolyJarvis/data/<run_name>/raw/"
graphs_dir = "/home/arz2/PolyJarvis/data/<run_name>/graphs/"
```

Tools that produce PNG figures:
- `extract_bulk_modulus_born` → `born_timeseries.png` (Born element convergence)
- `extract_bulk_modulus_deform` → `stress_strain.png`
- `extract_bulk_modulus_murnaghan` → `murnaghan_eos.png`
- `extract_bulk_modulus` → `volume_fluctuations.png`

Omitting `output_dir` means JSON files land next to the input log — `generate_run_summary` won't find them.

---

## Tool: `extract_bulk_modulus_born`

Use for glassy polymers — Born + NVT stress-fluctuation method.

**Call signature:**
```python
extract_bulk_modulus_born(
    born_matrix_file=born_matrix_file,   # fix ave/time output from nvt_born
    log_file=born_log_path,              # NVT thermo log (pxx, pyy, pzz, vol, temp)
    n_atoms=born_n_atoms,                # from born-worker RESULT
    eq_fraction=0.5,                     # discard first 50% as burn-in
    output_dir=output_dir,
    graphs_dir=graphs_dir,
)
```

**Result fields:**
- `bulk_modulus_GPa` — K_T (the reported value)
- `K_Born_GPa` — Born elastic contribution
- `kinetic_term_GPa` — NkT/V correction
- `fluctuation_correction_GPa` — (V/kT)·Var(P) correction (subtracted)
- `bulk_modulus_sem_GPa` — uncertainty via block averaging (None if insufficient data)
- `V_mean_A3`, `T_mean_K` — thermodynamic state
- `Var_P_atm2` — pressure variance
- `n_effective_samples`, `warnings`, `diagnostics`

**Acceptance:**
- `K_T > 0` — negative K_T means the fluctuation correction dominates; run is too short or system is not glassy
- `K_Born_GPa > 0.5` — very low Born term is unusual for a glassy polymer; check log convergence
- `fluctuation_correction_GPa < 0.5 × K_Born_GPa` — if fluctuation dominates, K_T is unreliable

**Reporting (R1M9 — include in RESULT block):**
- `bulk_modulus_sem_GPa`, `n_effective_samples`
- Derived: `tau_ac_ps = (born_run_ns × 1e3 × (1 − eq_fraction)) / (2 × n_effective_samples)`
- Gate: N_eff < 20 → add WARNING "born run too short for reliable block averaging; consider extending"

---

## Tool: `extract_bulk_modulus_deform`

Use for glassy polymers (recovery fallback after born-worker failure) — stress-strain fit from `npt_deform` log.

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
- `isotropy_delta_pct` < 20%

**Result fields:**
- `C11_GPa`, `C12_GPa`, `K_GPa`, `G_GPa`, `E_GPa`, `nu_Poisson`
- `fit_r2_C11`, `fit_r2_C12_yy`, `isotropy_delta_pct`
- `stress_strain_csv`, `summary_json`

**Reporting (R1M9):** Deterministic stress-strain fit — no autocorrelation concern. Report `fit_r2_C11` and `fit_r2_C12_yy` as the reliability indicators.

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

**Reporting (R1M9 — include in RESULT block):** `bulk_modulus_sem_GPa`, `r_squared`, `B0_prime`

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

**Reporting (R1M9 — include in RESULT block):** `bulk_modulus_sem_GPa`, `n_effective_samples`, `tau_eff_frames`, `tau_eff_fraction`

---

## Common Failures

**`extract_bulk_modulus` gives unreasonable K (< 0.1 GPa or > 20 GPa):** Not fully equilibrated — `diagnostics.drift_check` will warn. Increase `eq_fraction` to 0.7.

**`extract_bulk_modulus_born` returns K_T < 0:** Fluctuation correction dominates K_Born — run is too short or system is partially glassy (T too close to Tg). Check `n_effective_samples`; if low, the Born NVT run needs extending.

**`extract_bulk_modulus_murnaghan` method = "linear_fallback":** EOS nonlinearity not resolved — add more pressure points or increase `npt_steps` per point so each V_i is better converged. The linear fallback underestimates K for soft rubbery systems.

**`extract_bulk_modulus_deform` fit_r2 < 0.90:** Stress-strain data is noisy. Check THERMO_FREQ in the deform log (should be ≤ 100 for dense output). May also indicate strain rate too high — try the slow-rate comparison if `K_deform_rate_slow_inv_s` is non-null in prompt.
