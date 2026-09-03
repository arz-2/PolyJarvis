# PolyJarvis — Supported Properties

PolyJarvis reports three properties — **density**, **Tg**, and **bulk modulus** — each validated against experimental ranges from `guides/polymer_rules.json`.

To request a subset, pass `--properties density,tg` to `run_campaign.py`. Omitting the field uses the properties recorded in `run_plan.json`.

---

## 1. Density

| Field | Value |
|-------|-------|
| Units | g/cm³ at 300 K |
| Source log | `cool/npt_final/npt_final.log` (the assessment cell at `final_T_K`, default 300 K). The melt density at `T_melt_hold_K` is a separate observable, read from `equil/npt_melt_hold/npt_melt_hold.log` — the two are reported under different names and are not interchangeable. |
| Tool | `extract_equilibrated_density` |
| Method | Discard first 50 % of log as burn-in; mean ± SEM over production window; linear drift check |
| Validation | `experimental_density_gcm3` from polymer_rules.json; OK if within ±5 % |
| Outputs | `density.json`, `density_timeseries.csv` |

---

## 2. Glass Transition Temperature (Tg)

Tg is measured **single-rate-primary**: one stepped cooling sweep runs at the class's primary
configured rate (the highest entry in `tg_rates_K_per_ns` by default; a class carrying
`tg_slope_gate_fallback: "slowest_rate"` — one whose highest-rate fit is documented as
degenerate/inverted — runs `tg_rates_K_per_ns[0]` instead).

No class carries that fallback as of 2026-09-01. PKTN and PSFO did: their staircase reheated
the finished 300 K cell, so the top plateaus under-equilibrated and a faster sweep, spending
less time contaminated there, read a *lower* Tg — an inverted rate dependence. The sweep now
starts from the gated melt hold and runs the whole descent to `tg_t_low_K`, so both returned to
the highest rate. There is no reheat probe and no mid-ramp waypoint to select between: the
staircase's first point is the cell the melt gate certified.

### Sweep

| Field | Value |
|-------|-------|
| Units | K (MD value) |
| Source log | `thermal/tg_sweep/tg_sweep.log` |
| Tool | `extract_thermal` |
| Method | Stepped cooling sweep from high T to ≤200 K; bilinear fit of density vs T; breakpoint = Tg_MD. CTE (α_g, α_r) and ΔCp come from the same fit's branch slopes |
| Fit quality | PASS / WARN / ABORT; R² and segment slopes reported |
| Outputs | `thermal.json`, `tg_density_vs_T.png` |
| Validation | `experimental_tg_K` from polymer_rules.json, graded strictly (no offset in the band); MD Tg overestimates experiment by ~80–120 K (fast cooling rate artifact — Patrone 2016, Webb 2024), reported as an annotation only (`tg_offset_corrected_K`), never folded into PASS/FAIL |
| Side effect | `is_glassy` is decided from this sweep's MD Tg (`is_glassy = Tg_MD > 300`) when it ran at the class's highest configured rate; a degenerate fit or a deliberately slowest-rate sweep (PKTN, PSFO) falls back to `experimental_tg_K > 300` |

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
| Worker | murnaghan-worker: `run_bulk_modulus_series` submits N NPT runs at each pressure from `cool/npt_final/npt_final_out.data` (the assessment cell), then fits |
| Tool | `extract_bulk_modulus_murnaghan` |
| Acceptance | `fit_converged=True`; otherwise fall back to Path C (deformation). `B0_prime` outside [4, 20] is a WARNING annotation only, not a fallback trigger |
| Cross-check | Volume-fluctuation K, computed inside the same `extract_bulk_modulus_murnaghan` call via its `npt_prod_log` argument — a diagnostic, not the reported value |
| Method label | `murnaghan` |
| Outputs | `mechanical.json`, `murnaghan_eos.png` |

---

### Path B — Murnaghan EOS, rubbery  *(rubbery polymers with pressure series)*

`is_glassy=False` and `bm_pressures_atm` set in polymer_rules.json

Same Murnaghan EOS fit as Path A, run at T>Tg from the melt production cell over the per-class pressure list.

| Field | Value |
|-------|-------|
| Worker | murnaghan-worker: `run_bulk_modulus_series` over `bm_pressures_atm` (e.g. [1, 100, 300, 600, 1000] atm) from `cool/npt_final/npt_final_out.data` |
| Tool | `extract_bulk_modulus_murnaghan` |
| Advantage over fluctuation | Barostat-independent (uses mean V per pressure, not variance); captures EOS nonlinearity |
| Convergence fallback | If curve_fit fails → linear regression of P vs ln V (method label: `linear_fallback`) |
| Method label | `murnaghan` |
| Outputs | `mechanical.json`, `murnaghan_eos.png` |

---

### Path C — 3-direction deformation  *(Murnaghan fallback)*

Invoked when a Murnaghan fit fails acceptance (`fit_converged=False`).

`extract_bulk_modulus_deform` reads three uniaxial-deformation logs (DEFORM_DIR x/y/z, run sequentially from `cool/npt_final/npt_final_out.data`) and derives the bulk modulus from the stress–strain response.

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
| Source log | `cool/npt_final/npt_final.log` (no new simulations needed) |
| Tool | `extract_bulk_modulus` |
| Caveat | Sensitive to barostat P_DAMP. Cross-checked against `B_def = −dP/d(ln V)` from P vs ln V regression; disagreement >20 % emits a warning |
| Method label | `fluctuation` |
| Outputs | `bulk_modulus.json`, `volume_fluctuations.png` |

---

---

## Future Tracks (Taxonomy — No Workers Implemented)

These tracks are named for future deterministic workflow development and are not implemented yet.

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
