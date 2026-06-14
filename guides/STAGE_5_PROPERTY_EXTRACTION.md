# Stage 5: Property Extraction
**Read when:** You are the deform-worker and need to run the uniaxial deformation simulation

---

## Rules

### Rule A: Starting Structure is Stage 7 Output (300 K, NPT)

The input `.data` file is `07_npt_production_out.data` — already NPT-equilibrated at 300 K, 1 atm.
No cooling run is needed. Pass this file directly as `data_file` for Stage 5.

### Rule B: Stage 5 Only Runs for Glassy Polymers

If `is_glassy=False` (Tg < 300 K), return a RESULT block immediately — no simulation needed.
Density and bulk modulus for rubbery systems come from Stage 7 directly.

### Rule C: STRAIN_RATE Conversion

`K_deform_rate_inv_s` from polymer_rules.json is in s⁻¹. Convert to LAMMPS real units (1/fs):

```
STRAIN_RATE [1/fs] = K_deform_rate_inv_s [s⁻¹] × 1e-15 [s/fs]
e.g. 1e8 s⁻¹ × 1e-15 = 1e-7 /fs
```

### Rule D: N_STEPS for Deformation

```
N_STEPS = int(K_strain_max / (STRAIN_RATE [1/fs] × dt_fs [fs]))
e.g. 0.03 / (1e-7 × 1.0) = 300,000 steps
```

Verify: STRAIN_RATE × N_STEPS × dt_fs should equal K_strain_max ± 0.001.

### Rule E: All Scripts via generate_script — No Hand-Written .in Files

Use `npt_deform` template for Stage 5.
Call `list_templates("npt_deform")` for the full parameter list.

---

## Stage 5: Uniaxial Deformation (glassy only)

```python
strain_rate_per_fs = K_deform_rate_inv_s * 1e-15
n_steps_deform = int(K_strain_max / (strain_rate_per_fs * dt_fs))

params_deform = {
    "LOG_FILE":         "05_deform.log",
    "WRITE_DATA_FILE":  "05_deform_out.data",
    "DUMP_FILE":        "",               # no dump — log only
    "T_TARGET":         T_prop_K,         # 300
    "T_DAMP":           100.0,
    "STRAIN_RATE":      strain_rate_per_fs,
    "N_STEPS":          n_steps_deform,
    "N_EQ_STEPS":       200000,           # 0.2 ns NVT pre-equilibration
    "TIMESTEP":         dt_fs,
    "THERMO_FREQ":      100,              # dense output for stress-strain fit
    "use_gpu":          True,
    "use_pppm":         True,
    **lammps_flags,
}
# data_file = 07_npt_production_out.data (passed as equil_data_path)
generate_script(template_name="npt_deform",
                data_file=equil_data_path,
                output_script=f"{work_dir}/05_deform/05_deform.in",
                params=params_deform)
```

---

## Script Submission

```python
run_id = run_lammps_script(
    script=f"{work_dir}/05_deform/05_deform.in",
    work_dir=f"{work_dir}/05_deform",
    log_file="05_deform_run.log",
    gpu_ids=gpu_ids,
    mpi=mpi_ranks,
)
w = watch_run(run_id)
# Return run_id and w["monitor_command"] to the orchestrator — do not call Monitor.
```

---

## Defaults Reference

| Parameter | Default | Source |
|-----------|---------|--------|
| T_prop_K | 300 | Fixed; standard comparison temperature |
| K_deform_rate_inv_s | 1e7 | polymer_rules.json |
| K_strain_max | 0.03 | polymer_rules.json |
| N_EQ_STEPS (deform) | 200000 | 0.2 ns NVT pre-equil |

**K quality gate:** K is the primary output. C11 R² < 0.90 after `avg_window=200` is a noise issue (see Failure 1 below). C12_zz R² < 0.90 despite large avg_window is a small-system anisotropy effect — flag K as ⚠ but do not re-run. G/E/ν should not be reported when `isotropy_delta_pct` > 20%. Do not substitute `extract_bulk_modulus` (NPT fluctuation) for glassy systems — suppressed δV inflates K.

---

## Recovery Notes

**Stage 5 deformation crashes:** Check `dt_fs = 1.0` (SHAKE + deform requires 1 fs, not 2 fs). Reduce STRAIN_RATE by 10×: use 1e-8 /fs instead of 1e-7 /fs.

**Low R² on C11 (< 0.90):** Thermal stress fluctuations (~0.2 GPa) swamp the elastic signal (~0.09 GPa at 3% strain) when individual thermo rows are fit. Fix: set `avg_window=200` (or higher) in `extract_bulk_modulus_deform`. Default is now 200 (= 20 ps at THERMO_FREQ=100). The underlying C11 value is unchanged — averaging only improves R².

**Low R² on C12_zz despite large avg_window:** This indicates real anisotropy in the simulated system — C12_yy ≠ C12_zz by >20%. Root cause: insufficient chain count (< 20 chains); only 10-chain systems routinely show 25–30% anisotropy. G, E, ν cannot be reliably reported. K is still valid (it uses both C12 directions averaged). To fix anisotropy: increase chains to 20–30 (double N_CHAINS in polymer_rules.json).
