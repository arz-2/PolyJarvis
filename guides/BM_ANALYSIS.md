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
| `murnaghan_log_files` non-null | `extract_bulk_modulus_murnaghan` (pass `npt_prod_log` — the fluctuation cross-check runs inside this one call) | `murnaghan` | `bulk_modulus_murnaghan.json` |
| `deform_log_path` non-null | `extract_bulk_modulus_deform` | `deformation` | `bulk_modulus_deform.json` |
| all null | `extract_bulk_modulus` | `fluctuation` | `bulk_modulus.json` |

- **Glassy (`is_glassy=True`):** Murnaghan at 300 K is primary; single-direction deform (with a paired slow-rate rate-sensitivity check, when `deform_log_path_slow` is present) is the fallback only when Murnaghan fails (`fit_converged=False`). `B0_prime` outside [4, 20] is a WARNING annotation (see Acceptance below) — it never by itself triggers the deform-worker fallback.
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
    deform_direction="x",             # the axis the deck strained — see below
    # rate-sensitivity check — only when the orchestrator ran the paired slow-rate leg:
    log_file_2=deform_log_path_slow,      # None if not present
    strain_rate_2=strain_rate_slow_per_fs,  # None if not present
)
```

**Result fields:** `C11_GPa`, `C12_GPa`, `K_GPa`, `G_GPa`, `E_GPa`, `nu_Poisson`, `fit_r2_C11`,
`isotropy_delta_pct`, `deform_direction`, `transverse_axes`, `C12_t1_GPa`, `C12_t2_GPa`,
`deform_gate_verdict`, `deform_gate_reasons`, `avg_window_frames`, `stress_strain_csv`,
`summary_json`, `rate_sensitivity` (present only when `log_file_2` was passed — see Interpretation
above).
- `avg_window_frames` (default 2000): R² is on the smoothed stress series — correct, since raw thermal noise (~0.2 GPa) swamps the elastic signal (~0.09 GPa at 3% strain). Judge quality by `isotropy_delta_pct` + physical plausibility of K/G/E, not raw R².

**Pass `deform_direction`** matching the axis the deck strained. It selects which stress component
is the loading response and which two are transverse; a y- or z-direction leg analysed as `x` puts a
loading slope into the transverse average, corrupting C11, C12, G, E, ν and `isotropy_delta_pct`.
K is invariant (it is one third of the response trace), so a wrong axis shows up in the moduli and
the isotropy delta, not in K.

**Acceptance:** use `deform_gate_verdict` directly.
- `DEFORM_INADMISSIBLE` → do not report this K; `deform_gate_reasons` says why. Triggers: K < 0, E < 0, or
  `isotropy_delta_pct` ≥ 20%. At that level a *single-direction* Voigt K is a biased estimate — only
  one of three inequivalent directions was sampled (PLA2's three legs span 8.1% in K, and its most
  anisotropic leg is also its worst K outlier; PVC1 at 24.2% gives K=1.68 vs Murnaghan 2.85, 41%
  low). Hard failure, not a BORDERLINE annotation. G/E/ν are hit ~5× harder than K (PLA2 G spans
  44.6%), so never report those from an anisotropic leg either.
- `DEFORM_REPORTABLE` → also require `fit_r2_C11` and both transverse fit r² ≥ 0.90.
- **G<0 in a y/z leg means `deform_direction` was wrong, not small-cell anisotropy.** Analysing a
  y- or z-strained leg as `x` swaps a loading slope into C12, which drives C11 below C12 and flips
  the sign of G and E. Passing the correct axis removes it (PLA2 `deform_y`: G −0.599 → +1.105 GPa,
  E −1.909 → +2.994, isotropy 56.25% → 4.62%). K is unaffected either way, being one third of the
  response trace and so independent of which axis is labelled loading. If G<0 survives a correct
  `deform_direction`, treat it as a real result and investigate.

**Report:** `fit_r2_C11`, `fit_r2_C12_t1`/`_t2`, `isotropy_delta_pct`, `deform_direction`,
`deform_gate_verdict`, `avg_window_frames`, and (if present) `rate_sensitivity.verdict`.

### `extract_bulk_modulus_murnaghan`

```python
extract_bulk_modulus_murnaghan(
    log_files=murnaghan_log_files,   # from prompt, one per pressure
    pressures_atm=bm_pressures_atm,  # from prompt, matching log_files order
    eq_fraction=0.5,
    output_dir=output_dir,
    graphs_dir=graphs_dir,
    npt_prod_log=npt_prod_log_path,  # embeds the fluctuation cross-check in this same call
)
```

**Result fields:** `bulk_modulus_GPa` (=B0, the reported K), `B0_prime` (dK/dP), `V0_A3`,
`r_squared`, `fit_converged`, `bulk_modulus_sem_GPa`, `method` ("murnaghan" | "linear_fallback"),
`volume_monotonic`, `loo_results`, `loo_n_converged`, `fluctuation_bulk_modulus_GPa`,
`fluctuation_divergence_pct`, `bm_gate_verdict`, `bm_gate_reasons`, `warnings`.

**Acceptance:** use `bm_gate_verdict` directly; `bm_gate_reasons` lists what tripped.
- `BM_INADMISSIBLE` → do not report this K. Triggers are conditions physics entails, not precision
  bars: K ≤ 0, B0′ ≤ 0, `volume_monotonic=False` (dV/dP > 0 violates mechanical stability — re-run
  the offending pressure point, don't re-fit), `V0_A3` outside the sampled volume range by >25% of
  its width (the zero-pressure reference state isn't supported by the data), or `r_squared < 0.99`
  (the Murnaghan form doesn't describe this P–V data at all).
- `BM_FALLBACK_DEFORM` → `fit_converged=False`; route to the deformation fallback.
- `BM_REPORTABLE` → report K.

Precision annotations, none of which block reporting:
- `r_squared < 0.999` → WARNING only. It does **not** predict B0 accuracy (across the 36-run
  archive, mean |ΔB0| vs the family mean is 4.39% below 0.999 and 4.37% at or above it, Welch
  p=0.990), and at that threshold it flags physically sound fits while passing real outliers.
- **B0′ out of [4, 20] with `fit_converged=True` is WARNING, not FAIL** (the ±1000 atm span under-constrains curvature): high B0′≥13 with r²<0.999 = EOS-nonlinearity artifact (K still correct); low B0′<4 with r²≥0.999 = under-constrained curvature (K robust). Note the artifact in `notes`.
- Any `loo_results` entry with a large `dB0_GPa_vs_baseline` (script warns above 10%) → the fit leans on one point; note which pressure and whether it's `is_tension_point`. Not binding: whole-replicate spread is 4.4% mean / 16.6% worst, so a >10% single-point shift is not yet known to be pathological.

**Across replicates** — `aggregate_replicates.py` flags a run whose K sits >4 leave-one-out SDs and
>10% from the other replicates' mean, and marks a property non-`reportable` below 3 replicates. This
is what catches a run that passes every per-run gate yet disagrees with its siblings; per-run fit
statistics cannot see it.
- **Fluctuation cross-check:** flag any `fluctuation_divergence_pct` >15% prominently (script already warns). Expected/benign on rubbery classes (fluctuation overestimates rubbery K, up to ~70% in the archive); unusual on glassy classes and worth investigating there.

**Report:** `bulk_modulus_sem_GPa`, `r_squared`, `B0_prime`, `volume_monotonic`, `fluctuation_divergence_pct`, and any `loo_results` warning.

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
