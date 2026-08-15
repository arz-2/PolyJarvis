# Uniaxial Deformation Guide
**Read when:** You are the deform-worker and need to run the uniaxial deformation simulation.
**Scope:** Script generation and job submission only. Property extraction/acceptance is handled by `bulk-modulus-extractor` (`extract_bulk_modulus_deform`).

---

## Rules

- **Input cell:** `npt_prod300_out.data` (the 300 K production cell) — passed as `equil_data_path`. No extra cooling.
- **Glassy only:** if `is_glassy=False`, return a RESULT block immediately — no simulation.
- **No hand-written `.in`** — generate via the `npt_deform` template (`list_templates(template_name="npt_deform")` for the full param list). Single direction (`DEFORM_DIR="x"`, the template default) — the extractor derives isotropy from the *same run's* Pyy/Pzz, not from separate y/z direction runs.
- **`deform_rate_mode: primary` (default) | `slow`** — the orchestrator spawns you twice sequentially for the rate-sensitivity check, waiting for `primary` to finish before submitting `slow`. `slow` requires `K_deform_rate_slow_inv_s` non-null — if it's null, return the null-RESULT guard immediately instead (safe no-op for classes with no slow rate defined; the orchestrator always spawns the slow leg after a successful primary run).
- **STRAIN_RATE** = rate[s⁻¹] × 1e-15 → 1/fs, where rate = `K_deform_rate_inv_s` (primary) or `K_deform_rate_slow_inv_s` (slow) — same conversion either way (e.g. 1e8 × 1e-15 = 1e-7 /fs).
- **Pass `STRAIN_MAX` and `TIMESTEP`, never a hand-computed `N_STEPS`.** The template has no `STRAIN_MAX` placeholder — it renders `run {N_STEPS}` — so `generate_script` derives `N_STEPS = STRAIN_MAX / (STRAIN_RATE × TIMESTEP)` and raises on an inconsistent explicit pair. Omitting `TIMESTEP` leaves the deck's default 1.0 fs against an `N_STEPS` computed at the class `dt_fs`, and omitting `STRAIN_MAX` leaves the 300000-step default — the slow leg then reaches a tenth of its strain.
- **FF flags:** pass `use_pcff`/`use_trappe`/`use_opls` from `lammps_flags` explicitly — without them `generate_script` defaults to AMBER/CHARMM styles and crashes on PCFF/TraPPE-UA `.data` files.
- **T_TARGET** = 300 K (template default, no need to pass explicitly); **N_EQ_STEPS** = 200000 (0.2 ns NVT pre-equilibration); **THERMO_FREQ** = 100 (dense output for the stress-strain fit); **DUMP_FILE** = "" (disabled).
- **File naming:** `primary` → `05_deform.in` / `05_deform.log` / `05_deform_out.data` (submit log `05_deform_run.log`); `slow` → `05_deform_slow.in` / `05_deform_slow.log` / `05_deform_slow_out.data` (submit log `05_deform_slow_run.log`).

---

## Workflow

Same single-direction submission for both modes — only the rate and file suffix change:

```python
mode = deform_rate_mode  # "primary" or "slow"
rate_s  = K_deform_rate_inv_s if mode == "primary" else K_deform_rate_slow_inv_s
suffix  = "" if mode == "primary" else "_slow"
strain_rate_per_fs = rate_s * 1e-15

generate_script("npt_deform", data_file=equil_data_path,
    output_script=f"{work_dir}/mechanical/05_deform{suffix}.in",
    velocity_seed=<velocity_seed from prompt>,     # required, never null
    params={
        "STRAIN_RATE": strain_rate_per_fs,
        "STRAIN_MAX":  K_strain_max,               # derives N_STEPS; do not pass N_STEPS
        "TIMESTEP":    dt_fs,                      # the 1.0 default breaks that derivation
        "N_EQ_STEPS":  200000,
        "THERMO_FREQ": 100,
        "DUMP_FILE":   "",
        "engine":      engine,                     # from prompt — kokkos omits `package gpu`
        "use_pcff":    lammps_flags["use_pcff"],
        "use_trappe":  lammps_flags["use_trappe"],
        "use_opls":    lammps_flags["use_opls"],
    })
run_id = run_lammps_script(
    script=f"{work_dir}/mechanical/05_deform{suffix}.in",
    work_dir=f"{work_dir}/mechanical",
    log_file=f"05_deform{suffix}_run.log",
    gpu_ids=gpu_ids, mpi=mpi_ranks, engine=engine)  # engine MUST match generate_script
w = watch_run(run_id)  # return run_id + w["monitor_command"] to orchestrator. Do NOT call Monitor.
```
