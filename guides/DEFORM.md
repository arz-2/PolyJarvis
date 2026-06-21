# Uniaxial Deformation Guide
**Read when:** You are the deform-worker and need to run the uniaxial deformation simulation.
**Scope:** Script generation and job submission only. Property extraction from the deform log is handled by `bulk-modulus-extractor` (`extract_bulk_modulus_deform`).

---

## Rules

### Rule A: Starting Structure is the NPT 300 K Production Output (`npt_prod300`)

The input `.data` file is `npt_prod300_out.data`. Pass directly as `data_file` — no additional cooling needed.


### Rule B: Only Runs for Glassy Polymers

If `is_glassy=False` (Tg < 300 K), return a RESULT block immediately — no simulation needed.

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

Use `npt_deform` template for this stage.
Call `list_templates("npt_deform")` for the full parameter list.

### Rule F: Parse and Pass `lammps_flags` from the Prompt

Parse `lammps_flags` from the prompt header (it is a JSON dict). Pass `use_pcff`, `use_trappe`,
and `use_opls` **explicitly** into the params dict:

```python
lammps_flags = <parse from prompt header>

params_deform = {
    ...,
    "use_pcff":   lammps_flags["use_pcff"],    # REQUIRED — do not omit
    "use_trappe": lammps_flags["use_trappe"],  # REQUIRED — do not omit
    "use_opls":   lammps_flags["use_opls"],    # REQUIRED — do not omit
}
```

Without these, `generate_script` defaults to AMBER/CHARMM styles, which **crash on PCFF/TraPPE-UA
.data files** with a `bond style harmonic mismatch` error (PMMA1 R-05: both deform runs died at
read_data before taking a single step). Do not omit or guess the FF.

---

## Uniaxial Deformation Workflow (glassy only)

```python
lammps_flags = <parse from prompt header>   # {"use_pcff": True/False, "use_trappe": ..., "use_opls": ...}
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
    "use_pcff":         lammps_flags["use_pcff"],    # Rule F — explicit FF selector
    "use_trappe":       lammps_flags["use_trappe"],  # Rule F — explicit FF selector
    "use_opls":         lammps_flags["use_opls"],    # Rule F — explicit FF selector
}
# data_file = npt_prod300_out.data (passed as equil_data_path)
generate_script(template_name="npt_deform",
                data_file=equil_data_path,
                output_script=f"{work_dir}/mechanical/deform/deform.in",
                params=params_deform)
```

---

## Script Submission

```python
run_id = run_lammps_script(
    script=f"{work_dir}/mechanical/deform/deform.in",
    work_dir=f"{work_dir}/mechanical/deform",
    log_file="deform_run.log",
    gpu_ids=gpu_ids,
    mpi=mpi_ranks,
)
w = watch_run(run_id)
# Return run_id and w["monitor_command"] to the orchestrator — do not call Monitor.
```

---

## Recovery Notes

**Deformation crashes:** Check `dt_fs = 1.0` (SHAKE + deform requires 1 fs, not 2 fs). Reduce STRAIN_RATE by 10×: use 1e-8 /fs instead of 1e-7 /fs.
