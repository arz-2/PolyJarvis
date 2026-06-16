# PolyJarvis — Supported Properties

PolyJarvis reports three properties — **density**, **Tg**, and **bulk modulus** — each validated against experimental ranges from `guides/polymer_rules.json`.

To request a subset, pass `--properties density,tg` (or `all`) to `gen_prompt.py`, or set `TARGET_PROPERTIES` in the task. Omitting the field runs all three.

---

## 1. Density

| Field | Value |
|-------|-------|
| Units | g/cm³ at 300 K |
| Source log | `07_npt_production.log` (Stage 7 NPT production) |
| Tool | `extract_equilibrated_density` |
| Method | Discard first 50 % of log as burn-in; mean ± SEM over production window; linear drift check |
| Validation | `experimental_density_gcm3` from polymer_rules.json; OK if within ±5 % |
| Outputs | `density.json`, `density_timeseries.csv` |

---

## 2. Glass Transition Temperature (Tg)

| Field | Value |
|-------|-------|
| Units | K (MD value) |
| Source log | `tg/tg_sweep/tg_sweep.log` |
| Tool | `extract_tg` |
| Method | Stepped cooling sweep from high T to ≤200 K; bilinear fit of density vs T; breakpoint = Tg_MD |
| Fit quality | PASS / WARN / ABORT; R² and segment slopes reported |
| Validation | `experimental_tg_K` from polymer_rules.json; MD Tg overestimates experiment by ~80–120 K (fast cooling rate artifact — Patrone 2016, Webb 2024) |
| Outputs | `tg_fit.json`, `tg_density_vs_T.png` |
| Side effect | `is_glassy = (Tg_K > 300)` — this flag selects the bulk modulus path |

**If Tg is not requested:** `is_glassy` is inferred from `experimental_tg_K` in polymer_rules.json (glassy_hint). Tg_K is reported as N/A.

---

## 3. Bulk Modulus (K_T)

Path is selected automatically from `is_glassy` and `bm_pressures_atm` (from polymer_rules.json).

### Path A — Born NVT  *(glassy polymers, default)*

`is_glassy=True`

**Formula:**
```
K_T = K_Born + NkT/V − (V/kT)·Var(P)_NVT
```
- `K_Born` — Born elastic tensor from `compute born/matrix numdiff` (LAMMPS EXTRA-COMPUTE)
- `NkT/V` — ideal-gas kinetic correction at finite N
- `(V/kT)·Var(P)` — stress-fluctuation correction from NVT pressure variance

| Field | Value |
|-------|-------|
| Stage | born-worker: `nvt_born` template, 4 ns NVT at 300 K |
| CPU-only | Yes — `compute born/matrix numdiff` displaces atoms in CPU arrays; GPU pair styles incompatible |
| Tool | `extract_bulk_modulus_born` |
| Fallback | If `born_log_path=null`, falls back to Path C (deformation) |
| Method label | `born_nvt` |
| Outputs | `bulk_modulus_born.json` |

---

### Path B — Murnaghan EOS  *(rubbery polymers with pressure series)*

`is_glassy=False` and `bm_pressures_atm` set in polymer_rules.json

**Formula:**
```
P = (B0/B0') × [(V0/V)^B0' - 1]
```
Fit parameters: B0 (GPa), B0' (pressure derivative, typically 7–11 for polymer melts), V0 (reference volume Å³).

| Field | Value |
|-------|-------|
| Stage | property-analysis-worker: `run_bulk_modulus_series` submits N NPT runs at each pressure in `bm_pressures_atm` (e.g. [1, 100, 300, 600, 1000] atm), then fits |
| Tool | `extract_bulk_modulus_murnaghan` |
| Advantage over fluctuation | Barostat-independent (uses mean V per pressure, not variance); captures EOS nonlinearity |
| Convergence fallback | If curve_fit fails → linear regression of P vs ln V (method label: `linear_fallback`) |
| Diagnostic | `extract_bulk_modulus` also runs in parallel to report B_dyn; not the reported value |
| Method label | `murnaghan` |
| Outputs | `bulk_modulus_murnaghan.json`, `murnaghan_eos.png` |

---

### Path C — Volume Fluctuation fallback  *(rubbery polymers, no pressure series)*

`is_glassy=False` and `bm_pressures_atm` not set in polymer_rules.json

**Formula:**
```
K_T = kB·T·<V> / Var(V)
```

| Field | Value |
|-------|-------|
| Source log | `07_npt_production.log` (no new simulations needed) |
| Tool | `extract_bulk_modulus` |
| Caveat | Sensitive to barostat P_DAMP. Cross-checked against `B_def = −dP/d(ln V)` from P vs ln V regression; disagreement >20 % emits a warning |
| Method label | `fluctuation` |
| Outputs | `bulk_modulus.json`, `volume_fluctuations.png` |

---

### Deformation — optional cross-check only

`extract_bulk_modulus_deform` reads a `npt_deform` log (uniaxial deformation, deform-worker) and derives Young's modulus and bulk modulus from the stress-strain curve. Not called in the default pipeline. Use manually for rate-sensitivity diagnostics or when EXTRA-COMPUTE is unavailable.

Method label: `deformation`

---

## Validation

All experimental ranges are per-class fields in `guides/polymer_rules.json`:

| Property | Field | Status thresholds |
|----------|-------|------------------|
| Density | `experimental_density_gcm3` | OK: within ±5 % |
| Tg | `experimental_tg_K` | OK: MD value within expected 80–120 K overestimate |
| Bulk modulus | `exp_K_GPa` | OK / WARNING per property-analysis-worker comparison |

Status values in the RESULT block: `OK` | `WARNING` | `N/A`
