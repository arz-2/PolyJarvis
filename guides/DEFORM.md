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

Without these, `generate_script` defaults to AMBER/CHARMM styles, which **crash on PCFF/TraPPE-UA .data files**. Do not omit or guess the FF.

---

## 3-Direction Deformation Workflow (glassy fallback)

Run x, y, z deformations sequentially. Average K across all three directions for a reliable isotropic estimate. Total cost: ~3× a single-direction run (~1 ns at standard strain rates), comparable to Murnaghan.

```python
run_ids = {}
for deform_dir in ["x", "y", "z"]:
    generate_script("npt_deform", data_file=equil_data_path,
        output_script=f"{work_dir}/mechanical/deform/deform_{deform_dir}.in",
        params={
            "DEFORM_DIR":  deform_dir,                 # x, y, or z
            "STRAIN_RATE": strain_rate_per_fs,         # Rule C
            "N_STEPS":     n_steps_deform,             # Rule D
            "N_EQ_STEPS":  200000,
            "THERMO_FREQ": 100,
            "DUMP_FILE":   "",
            "engine":      engine,                     # from prompt — kokkos omits `package gpu`
            "use_pcff":    lammps_flags["use_pcff"],   # Rule F
            "use_trappe":  lammps_flags["use_trappe"],
            "use_opls":    lammps_flags["use_opls"],
        })
    run_ids[deform_dir] = run_lammps_script(
        script=f"{work_dir}/mechanical/deform/deform_{deform_dir}.in",
        work_dir=f"{work_dir}/mechanical/deform_{deform_dir}",
        gpu_ids=gpu_ids, mpi=mpi_ranks, engine=engine)  # engine MUST match generate_script
# Submit all 3 runs; return run_ids dict and a combined monitor_command to the orchestrator.
# Use watch_run on the last run_id to get a monitor_command that fires after all finish
# (or sequentially via BACKGROUND-WAIT: submit x, wait on its waiter, then y, then z).
w = watch_run(run_ids["z"])  # return run_ids and w["monitor_command"] to orchestrator
```

**Acceptance (3-direction):** Run `extract_bulk_modulus_deform` separately on each log. Report K_x, K_y, K_z, and K_mean = (K_x + K_y + K_z)/3 in the RESULT block. Gate: if K_std/K_mean > 20% across directions, flag BORDERLINE (isotropy still poor despite averaging — system too small or poorly equilibrated).

> **G<0 in y/z is NOT a hard failure.** On small amorphous cells C11<C12 can occur in some directions → negative shear G (e.g. PLA2: G_y=-0.60, G_z=-0.65 GPa), but K=(C11+2C12)/3 averages the transverse stresses and stays robust. Report K_mean as bulk_modulus_GPa if the **cross-direction** K_std/K_mean<20% and all fit_r²≥0.90; report G and E from the x-direction (best-behaved) only, and note "G<0 y/z — small-cell anisotropy; K_mean robust." The per-direction `isotropy_delta_pct` from `extract_bulk_modulus_deform` (C12_yy vs C12_zz, within one direction) is a DIFFERENT metric from the cross-direction K spread used in this gate — check the cross-direction spread manually.

**Acceptance (single-direction, x-only):** If running x-only as a quick check, `isotropy_delta_pct ≥ 20%` → FAIL; this run is informational only. The Murnaghan path should have been primary and should be the reported value.

---

## Recovery Notes

**Deformation crashes:** Check `dt_fs = 1.0` (SHAKE + deform requires 1 fs, not 2 fs). Reduce STRAIN_RATE by 10×: use 1e-8 /fs instead of 1e-7 /fs.
