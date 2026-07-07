# PolyJarvis — Supported Properties

PolyJarvis reports three properties — **density**, **Tg**, and **bulk modulus** — each validated against experimental ranges from `guides/polymer_rules.json`.

To request a subset, pass `--properties density,tg` (or `all`) to `gen_prompt.py`, or set `TARGET_PROPERTIES` in the task. Omitting the field runs all three.

---

## 1. Density

| Field | Value |
|-------|-------|
| Units | g/cm³ at 300 K |
| Source log | Rubbery: `npt_production.log` (melt NPT production); Glassy: `npt_prod300.log` (NPT 300 K production) |
| Tool | `extract_equilibrated_density` |
| Method | Discard first 50 % of log as burn-in; mean ± SEM over production window; linear drift check |
| Validation | `experimental_density_gcm3` from polymer_rules.json; OK if within ±5 % |
| Outputs | `density.json`, `density_timeseries.csv` |

---

## 2. Glass Transition Temperature (Tg)

Tg is measured **multirate**: one stepped cooling sweep is run per cooling rate, each sweep yields a per-rate Tg, and the per-rate Tg values are extrapolated to the experimental (DSC-equivalent) rate.

### Per-rate sweep

| Field | Value |
|-------|-------|
| Units | K (MD value) |
| Source log | `thermal/tg_sweep_r<rate>/tg_sweep.log` (one per rate in `tg_rates_K_per_ns`, e.g. [25, 50, 100]) |
| Tool | `extract_thermal` |
| Method | Stepped cooling sweep from high T to ≤200 K; bilinear fit of density vs T; breakpoint = Tg_MD at that rate. CTE (α_g, α_r) and ΔCp come from the same fit's branch slopes |
| Fit quality | PASS / WARN / ABORT; R² and segment slopes reported |
| Outputs | per-rate `tg_summary.json`, `tg_density_vs_T.png` |

### Multirate aggregation → DSC-equivalent Tg

| Field | Value |
|-------|-------|
| Tool | `extract_tg_multirate` |
| Method | Fit Tg vs ln(cooling rate); extrapolate to `dsc_equiv_rate_K_per_ns` (~1.67e-10 K/ns) → headline DSC-equivalent Tg |
| Inputs | This run's three per-rate (rate, Tg) pairs, filtered to fit_quality ≥ ACCEPTABLE (single-run protocol — no cross-run pooling) |
| Slope gate (glassy) | Tg must rise with rate (slope > 0); a non-positive slope marks the per-rate data contaminated → re-run with a new seed |
| Rubbery regime | When T_workflow ≫ Tg the rate-dependence is ~flat: `is_flat_rate_regime=True`, `tg_method=flat_rate_mean` reports the mean across rates (not an extrapolation), slope gate exempted |
| Validation | `experimental_tg_K` from polymer_rules.json; MD Tg overestimates experiment by ~80–120 K (fast cooling rate artifact — Patrone 2016, Webb 2024) |
| Outputs | `tg_multirate_result.json` |
| Side effect | `is_glassy` selects the bulk modulus path — decided from the **highest-rate** MD Tg (`is_glassy = Tg_highest_rate > 300`); on a degenerate highest-rate fit it falls back to `experimental_tg_K > 300` |

**If Tg is not requested:** `is_glassy` is inferred from `experimental_tg_K` in polymer_rules.json (glassy_hint). Tg_K is reported as N/A.

---

## 3. Bulk Modulus (K_T)

Path is selected automatically from `is_glassy` and `bm_pressures_atm` (from polymer_rules.json). Every path reports the isothermal bulk modulus K_T in GPa. Murnaghan is the primary method for both phases; deformation is its fallback.

### Path A — Murnaghan EOS, glassy  *(glassy polymers, primary)*

`is_glassy=True`

An NPT pressure series around 1 atm (e.g. ±1000 atm) is run from the 300 K production cell; the mean volume at each pressure is fit to the Murnaghan equation of state.

**Formula:**
```
P = (B0/B0') × [(V0/V)^B0' − 1]
```
Fit parameters: B0 (GPa) = K_T, B0' (pressure derivative), V0 (reference volume Å³).

| Field | Value |
|-------|-------|
| Worker | murnaghan-worker: `run_bulk_modulus_series` submits N NPT runs at each pressure from `npt_prod300_out.data` (the 300 K cell), then fits |
| Tool | `extract_bulk_modulus_murnaghan` |
| Acceptance | `fit_converged=True` and `B0_prime ∈ [4, 20]`; otherwise fall back to Path C (deformation) |
| Cross-check | `extract_bulk_modulus` (volume fluctuation) runs in parallel as a diagnostic, not the reported value |
| Method label | `murnaghan` |
| Outputs | `bulk_modulus_murnaghan.json`, `murnaghan_eos.png` |

---

### Path B — Murnaghan EOS, rubbery  *(rubbery polymers with pressure series)*

`is_glassy=False` and `bm_pressures_atm` set in polymer_rules.json

Same Murnaghan EOS fit as Path A, run at T>Tg from the melt production cell over the per-class pressure list.

| Field | Value |
|-------|-------|
| Worker | murnaghan-worker: `run_bulk_modulus_series` over `bm_pressures_atm` (e.g. [1, 100, 300, 600, 1000] atm) from `npt_production_out.data` |
| Tool | `extract_bulk_modulus_murnaghan` |
| Advantage over fluctuation | Barostat-independent (uses mean V per pressure, not variance); captures EOS nonlinearity |
| Convergence fallback | If curve_fit fails → linear regression of P vs ln V (method label: `linear_fallback`) |
| Method label | `murnaghan` |
| Outputs | `bulk_modulus_murnaghan.json`, `murnaghan_eos.png` |

---

### Path C — 3-direction deformation  *(Murnaghan fallback)*

Invoked when a Murnaghan fit fails acceptance (`fit_converged=False`, or `B0_prime` outside [4, 20]).

`extract_bulk_modulus_deform` reads three uniaxial-deformation logs (DEFORM_DIR x/y/z, run sequentially by deform-worker from `npt_prod300_out.data`) and derives the bulk modulus from the stress–strain response.

| Field | Value |
|-------|-------|
| Worker | deform-worker: `npt_deform` template, x/y/z directions |
| Tool | `extract_bulk_modulus_deform` |
| Caveat | `isotropy_delta_pct ≥ 20 %` across the three directions flags a hard FAIL (cell not isotropic) |
| Method label | `deformation` |
| Outputs | `bulk_modulus_deform.json`, `stress_strain.csv` |

---

### Path D — Volume Fluctuation  *(rubbery polymers, no pressure series)*

`is_glassy=False` and `bm_pressures_atm` not set in polymer_rules.json

**Formula:**
```
K_T = kB·T·<V> / Var(V)
```

| Field | Value |
|-------|-------|
| Source log | `npt_production.log` (no new simulations needed) |
| Tool | `extract_bulk_modulus` |
| Caveat | Sensitive to barostat P_DAMP. Cross-checked against `B_def = −dP/d(ln V)` from P vs ln V regression; disagreement >20 % emits a warning |
| Method label | `fluctuation` |
| Outputs | `bulk_modulus.json`, `volume_fluctuations.png` |

---

---

## Future Tracks (Taxonomy — No Workers Implemented)

These tracks are named for future development. No simulation workers or gen_prompt stages exist yet.

| Track | Properties | Simulation type |
|-------|-----------|----------------|
| **Electrical** | Dielectric constant (ε), dipole moment, polarizability | Polarizability simulations, LAMMPS kspace |
| **Viscoelastic** | Storage modulus (E'), loss modulus (E''), tan δ | Oscillatory (DMA-type) deformation |
| **Transport** | Self-diffusivity (D), permeability (P) | MSD from NVT run, dual-control volume GCMD |

---

## Validation

All experimental ranges are per-class fields in `guides/polymer_rules.json`:

| Property | Field | Status thresholds |
|----------|-------|------------------|
| Density | `experimental_density_gcm3` | OK: within ±5 % |
| Tg | `experimental_tg_K` | OK: MD value within expected 80–120 K overestimate |
| Bulk modulus | `exp_K_GPa` | OK / WARNING per bulk-modulus-extractor comparison |

Status values in the RESULT block: `OK` | `WARNING` | `N/A`
