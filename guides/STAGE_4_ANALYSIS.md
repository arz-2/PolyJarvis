# Stage 4: Analysis & Validation
**Read when:** You have simulation output and need to extract and validate properties
**Previous stage:** `STAGE_3_TG_MEASUREMENT.md`

---

## Critical Rules for This Stage

### Rule A: Never Report Tg Without Checking Fit Quality

```python
result = get_run_output(tg_run["run_id"])["result"]

# Overall fit_quality is the stricter of R² and F-stat checks
if result["fit_quality"] in ("EXCELLENT", "GOOD"):
    agreement = abs(result["Tg_K"] - result["Tg_alternative_K"])
    if agreement < 15:
        print(f"Tg = {result['Tg_K']:.1f} K  (R²={result['r_squared']:.4f}, F-stat p={result['f_statistic_pvalue']:.2e})")
    else:
        print(f"WARNING: Tg_K={result['Tg_K']:.1f} vs alt={result['Tg_alternative_K']:.1f} — large disagreement")
elif result["fit_quality"] == "ACCEPTABLE":
    print(f"Tg ≈ {result['Tg_K']:.1f} K — low confidence, report with caveat")
else:
    print("POOR fit — do NOT report. Extend simulation or fix sweep.")
```

**Fit quality tiers** *(rated independently on R² and F-stat; overall is the stricter of the two)*:

| R² | F-stat p-value | Quality | Action |
|---|---|---|---|
| ≥ 0.99 | < 0.001 | EXCELLENT | Report with confidence |
| ≥ 0.97 | < 0.01 | GOOD | Report with confidence |
| ≥ 0.90 | < 0.05 | ACCEPTABLE | Report with caveat |
| < 0.90 | ≥ 0.05 | POOR | Do not report — investigate |

**`Tg_K` vs `Tg_alternative_K`:** Both are computed independently (F-stat split vs scipy bilinear). Disagreement >20 K means the transition region is noisy or the sweep range is too narrow. Investigate before reporting.

---

### Rule B: Check Convergence Before Extracting Any Property

Before running any analysis tool, verify the equilibration log shows a converged density plateau.

---

### Rule C: All Analysis Runs on Lambda — No Large Downloads

`extract_tg`, `extract_end_to_end_vectors`, `calculate_rdf`, `extract_equilibrated_density`, `extract_bulk_modulus`, and `unwrap_coordinates` all run as background jobs on Lambda. Download only the small CSV/JSON result files. Never download full dump files unless absolutely necessary.

---

### Rule D: Always Specify `atom_type_pairs` in `calculate_rdf`

`atom_type_pairs=None` computes all pairs and can exceed 2 GB RAM per frame for 10k-atom systems. Always pass explicit pairs.

---

## Universal Job Pattern (All Analysis Tools)

All analysis tools are async — they return a `run_id` immediately and execute in the background.

```python
# 1. Submit (returns immediately with run_id)
run = extract_tg(log_file="...")    # or extract_end_to_end_vectors, calculate_rdf, etc.

# 2. Poll
while True:
    s = get_run_status(run["run_id"])
    if s["status"] in ("completed", "failed"):
        break
    time.sleep(15)

# 3. Retrieve
result = get_run_output(run["run_id"])["result"]
```

---

## Tool: `extract_tg`

Extracts Tg from LAMMPS Tg-sweep log. Uses plateau detection + F-stat exhaustive split (v3, March 2026). Works directly from the log file — no dump needed.

```python
run = extract_tg(
    log_file="/home/arz2/simulations/<run_dir>/tg_sweep/tg_sweep.log",
    output_dir=None,               # Defaults to <log_dir>/tg_analysis/
    initial_tg_guess=200,          # K — hint for secondary curve_fit; primary F-stat method is guess-free
    equilibration_fraction=0.5,    # Fraction of steps per plateau used for density averaging
    temp_col="Temp",
    density_col="Density"
)
```

**Result fields:**
- `Tg_K` — primary Tg from F-stat exhaustive split (guess-free)
- `Tg_alternative_K` — cross-check via scipy curve_fit bilinear
- `r_squared` — goodness of fit (R²)
- `f_statistic` — F-statistic of two-line vs single-line model
- `f_statistic_pvalue` — p-value for F-stat test (< 0.01 = reliable split)
- `fit_quality` — EXCELLENT / GOOD / ACCEPTABLE / POOR (stricter of R² and F-stat checks)
- `fit_quality_r2` — quality rating from R² alone
- `fit_quality_fstat` — quality rating from F-stat alone
- `fit_method` — fit method used (`"fstat_split"`)
- `binning_method` — plateau detection method used
- `n_plateaus_skipped_drift` — plateaus excluded for excessive density drift (> 1%)
- `n_temperature_bins` — number of clean plateaus used for fitting
- `temp_range_K` — `[T_min, T_max]` of data used
- `bins_csv` — path to `tg_density_bins.csv` on Lambda (download for publication plots)
- `summary_json` — path to full analysis JSON on Lambda

**Tuning `equilibration_fraction`:**
- 0.5 (default): standard for 2 ns/T runs
- 0.7: for large/slow systems
- Minimum 4 clean temperature bins required for fit

---

## Tool: `extract_end_to_end_vectors`

Computes per-chain end-to-end distance R and vector for every trajectory frame. Uses `sort_backbone()` for backbone-aware terminal atom identification via bond graph from the topology file. Auto-unwraps coordinates via MDAnalysis transformations.

```python
run = extract_end_to_end_vectors(
    dump_file="/home/arz2/simulations/<run_dir>/eq/nvt_prod.dump",
    data_file="/home/arz2/simulations/<run_dir>/cell.data",  # Required for bond topology
    backbone_types=[2],    # REQUIRED — LAMMPS atom type IDs for backbone atoms
                           # Get these from parse_data_file(); e.g. for PE (GAFF: hc=1, c3=2) → [2]
                           # For PEO (hc=1, c3=2, os=3) → [2, 3]
    skip_frames=0,         # Initial frames to skip (burn-in)
    max_frames=None,       # Cap on frames after skip
    num_chains=None,       # Auto-detected from resids if None
    chain_ids=None,        # Analyse subset of chains if needed
    output_dir=None        # Defaults to <dump_dir>/analysis/
)
```

**Result fields:**
- `overall_mean_R` — mean end-to-end distance (Å) across all chains and frames
- `overall_mean_R2` — mean ⟨R²⟩ (Å²) — connects to characteristic ratio C∞
- `per_chain` — list of per-chain stats: `mean_R`, `std_R`, `mean_R2`, `n_frames`
- `csv_file` — path to `end_to_end_vectors.csv` on Lambda

**`backbone_types` is required.** Always determine these from `parse_data_file()` output — do not assume. The tool traces the backbone bond graph to find true chain termini; incorrect backbone_types will return wrong terminal atoms.

**Diagnostic:** Large per-chain variance in R suggests poor equilibration.

---

## Tool: `calculate_rdf`

Computes g(r) radial distribution functions for specified atom-type pairs using MDAnalysis InterRDF.

```python
run = calculate_rdf(
    dump_file="/home/arz2/simulations/<run_dir>/eq/nvt_prod.dump",
    data_file="/home/arz2/simulations/<run_dir>/cell.data",  # REQUIRED — topology for MDAnalysis
    atom_type_pairs=[[2,2], [1,1], [1,2]],  # C-C, H-H, C-H for PE (types from parse_data_file)
    rmax=15.0,       # Å — covers 4-5 coordination shells
    nbins=150,
    skip_frames=0,
    max_frames=None,   # Cap on frames after skip; useful for quick checks
    output_dir=None,
    atom_style="id resid type charge x y z"  # Match your dump format
)
```

**Result fields:**
- `rdf_files` — dict of pair → CSV path on Lambda, e.g., `{"2-2": "/path/rdf_t2-t2.csv"}`
- `pairs_computed` — list of computed pair strings

**`data_file` is required.** MDAnalysis needs the topology to parse atom types correctly from the dump.

**Atom type IDs:** Get these from `parse_data_file()` output — do not assume. For PE: C=2, H=1. For other polymers, check the data file output.

**Expected peaks for PE:**
- C-C first peak: ~1.54 Å (bonded)
- C-C second peak: ~2.54 Å
- Convergence to g(r)=1 beyond ~10 Å confirms amorphous bulk behavior

**Memory note:** For a 10k-atom system, each pair requires O(N1 × N2 × 24 bytes) RAM per frame. Specify only the pairs you need.

---

## Tool: `extract_equilibrated_density`

Extracts the stable density plateau from an NPT equilibration log using reverse-cumulative-mean detection (more robust than a fixed burn-in fraction).

```python
run = extract_equilibrated_density(
    log_file="/home/arz2/simulations/<run_dir>/eq/final_eq.log",
    output_dir=None,
    eq_fraction=0.5,           # Discard first 50% as initial burn-in
    target_temp=None,          # Filter to a specific temperature (K) if log is multi-T
    temp_tolerance=50,         # ±50 K window around target_temp
    plateau_shift_sigma=1.0,   # Sensitivity of plateau edge detection
    density_col="Density",
    temp_col="Temp"
)
```

**Result fields:**
- `plateau_density_mean` — equilibrated density (g/cm³)
- `plateau_density_std` — standard deviation within the plateau
- `plateau_density_sem` — standard error of the mean
- `plateau_n_points` — number of thermo rows in the identified plateau
- `plateau_fraction` — fraction of the production window identified as plateau
- `naive_mean` / `naive_std` — simple average of full production window (compare to plateau for sanity)
- `plateau_step_range` — `[start_step, end_step]` of the identified plateau
- `summary_json` — path to JSON on Lambda

**Use for:** Getting a clean density value from equilibration logs before comparing to experiment. Better than manual inspection of the log.

---

## Tool: `extract_bulk_modulus`

Extracts isothermal bulk modulus from an NPT log via volume fluctuations: K_T = k_B T ⟨V⟩ / Var(V).

```python
run = extract_bulk_modulus(
    log_file="/home/arz2/simulations/<run_dir>/eq/final_eq.log",
    output_dir=None,
    eq_fraction=0.5,    # Use last 50% as production window
    block_count=5,      # Blocks for uncertainty estimation
    vol_col="Volume",   # Column name — tries Volume, Vol, vol
    temp_col="Temp",
    press_col="Press",
    density_col="Density"
)
```

**Result fields:**
- `bulk_modulus_GPa` — isothermal bulk modulus K in GPa
- `bulk_modulus_atm` — K in atm
- `bulk_modulus_sem_GPa` — block-average SEM (uncertainty estimate)
- `isothermal_compressibility_per_Pa` — β_T = 1/K
- `V_mean_A3`, `V_std_A3` — volume statistics
- `block_averaging` — per-block K values
- `diagnostics` — T, P, density means + volume drift check
- `summary_json` — path to JSON on Lambda

**Requirements:** Must be an NPT run that is well-equilibrated. Check `check_equilibration` first. If the diagnostics show volume drift > 1% (p < 0.01), a warning is issued — extend equilibration before trusting K.

---

## Tool: `check_equilibration`

Checks whether a simulation is equilibrated based on density and energy convergence. Applies both a drift test (linear regression) and a block-average test (Flyvbjerg-Petersen). Now **async** — runs in the background.

```python
run = check_equilibration(
    log_file="/home/arz2/simulations/<run_dir>/eq/final_eq.log",
    output_dir=None,             # Defaults to <log_dir>/eq_analysis/
    eq_fraction=0.5,             # Fraction of rows used as production window
    drift_threshold_pct=1.0,     # Max allowed drift as % of mean
    drift_pvalue=0.01,           # p-value threshold for drift significance
    block_count=5,               # Number of blocks for block-average test
    temp_col="Temp",
    press_col="Press",
    density_col="Density",
    energy_col="TotEng"
)
```

**Result fields:**
- `equilibrated` — overall bool (True only if density AND energy both pass both tests)
- `density_equilibrated` — bool
- `energy_equilibrated` — bool
- `density` / `energy` — sub-dicts with:
  - `drift` — `{pass: bool, slope, p_value, drift_pct}`
  - `block_avg` — `{pass: bool, sem, sem_pct}`
- `meta` — `{T_mean, P_mean, n_rows_total, n_rows_production}`
- `summary_json` — path to JSON on Lambda

**Before any property extraction:** Always run `check_equilibration` first. Do not proceed if `equilibrated=False`.

---

## Tool: `unwrap_coordinates`

Writes a new dump file with image-flag unwrapped coordinates. Usually not needed if using `extract_end_to_end_vectors` (it auto-unwraps via MDAnalysis transformations).

```python
run = unwrap_coordinates(
    dump_file="/path/to/trajectory.dump",
    output_file=None    # Defaults to <stem>_unwrapped.dump in same directory
)
```

**Result fields:** `output_file`, `frames_written`, `natoms`, `size_bytes`

**Use only when:** Feeding dump files to external tools (OVITO, VMD) that don't handle image flags. Check Lambda disk space first — output file is same size as input.

---

## Validation Against Experimental Data

After extracting properties, compare against experimental benchmarks and cite your source.

### Acceptance Criteria

| Property | Acceptable Error | Source |
|---|---|---|
| Tg | ±20 K | Afzal 2021, Webb 2024 |
| Density | ±5% | Multiple studies |
| Thermal conductivity | ±30% | High uncertainty property |

### Benchmark Targets

| Polymer | Exp Tg | Exp Density (300K) |
|---|---|---|
| PE | ~195 K | ~0.85 g/cm³ |
| PS | ~373 K | ~1.05 g/cm³ |
| PMMA | ~378 K | ~1.18 g/cm³ |
| PEO/PEG | ~206 K | ~1.12 g/cm³ |

### Red Flags (Investigate Before Reporting)

- Density outside ±10% of experimental
- Tg outside ±50 K of experimental
- R² < 0.90 on bilinear fit
- `Tg_K` and `Tg_alternative_K` disagree by >20 K
- RDF shows no clear peaks or does not converge to 1.0 at large r
- Per-chain variance in end-to-end R is very large (poor equilibration)

---

## Recommended Analysis Sequence

### Step 0: Check equilibration first

```python
eq_run = check_equilibration(log_file=nvt_prod_log)
while get_run_status(eq_run["run_id"])["status"] not in ("completed", "failed"):
    time.sleep(15)
eq_result = get_run_output(eq_run["run_id"])["result"]
assert eq_result["equilibrated"], f"Not equilibrated: {eq_result}"
```

### Step 1: Submit all analysis jobs in parallel (independent)

```python
# Get backbone atom types from data file first
info = parse_data_file(data_file=data_file, remote=True)
# Identify backbone type IDs from info["atom_types"] — e.g. [2] for PE

tg_run  = extract_tg(log_file=tg_log_path, initial_tg_guess=200)
ree_run = extract_end_to_end_vectors(
    dump_file=nvt_dump, data_file=data_file,
    backbone_types=[2]   # ← REQUIRED; replace with your backbone type IDs
)
rdf_run = calculate_rdf(
    dump_file=nvt_dump, data_file=data_file,
    atom_type_pairs=[[2,2],[1,1],[1,2]]
)
den_run = extract_equilibrated_density(log_file=nvt_prod_log)

# Poll all
for run in [tg_run, ree_run, rdf_run, den_run]:
    while get_run_status(run["run_id"])["status"] not in ("completed", "failed"):
        time.sleep(15)

# Retrieve
tg_result  = get_run_output(tg_run["run_id"])["result"]
ree_result = get_run_output(ree_run["run_id"])["result"]
rdf_result = get_run_output(rdf_run["run_id"])["result"]
den_result = get_run_output(den_run["run_id"])["result"]
```

### Step 2: Download CSV files for plotting

```python
download_file_from_remote(tg_result["bins_csv"],   local_path="./results/tg_density_bins.csv")
download_file_from_remote(ree_result["csv_file"],  local_path="./results/end_to_end_vectors.csv")
for pair, path in rdf_result["rdf_files"].items():
    download_file_from_remote(path, local_path=f"./results/rdf_{pair}.csv")
```

---

## Common Failures at This Stage

**`extract_tg` fails with "fewer than 4 temperature bins":**
- Sweep range too narrow or T_STEP too large
- Log file incomplete (simulation crashed) — check stdout log
- Plateaus with excessive density drift are excluded; if `n_plateaus_skipped_drift` is high, the simulation needs more time per T

**`Tg_K` and `Tg_alternative_K` disagree by >20 K:**
- Noisy density data — increase N_STEPS_PER_T and re-run sweep
- Temperature range doesn't bracket the transition — extend range

**`fit_quality` is POOR despite a seemingly clean log:**
- Download `tg_density_bins.csv` and plot ρ(T) manually
- Look for discontinuities from velocity re-initialization (Rule C in Stage 3)
- Check `n_plateaus_skipped_drift` — if many were skipped, data quality is the problem

**`calculate_rdf` runs out of memory / crashes:**
- `atom_type_pairs=None` was used — always specify explicit pairs (Rule D)
- `data_file` not passed — now required for MDAnalysis topology

**`extract_end_to_end_vectors` returns unreasonably large R:**
- `backbone_types` not set correctly — confirm type IDs from `parse_data_file()`
- Image flags (ix, iy, iz) missing from the dump — MDAnalysis can't unwrap without them

**`check_equilibration` returns `equilibrated=False`:**
- Extend the final NPT run by 1–2 ns and re-run the check
- Check `density.drift` and `energy.drift` sub-dicts to identify which property is drifting

**`extract_bulk_modulus` gives unreasonable K:**
- Simulation not fully equilibrated — `diagnostics.drift_check` will warn if volume is drifting
- Increase `eq_fraction` to use only the most stable portion of the trajectory

---

**→ Stage 4 complete. Summarize results, compare to experimental benchmarks, and document findings in SUMMARY_LOG.md.**
