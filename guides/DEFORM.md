# Uniaxial Deformation Guide
**Read when:** You are the deform-worker and need to run the uniaxial deformation simulation.
**Scope:** Script generation and job submission only. Property extraction/acceptance is handled by `bulk-modulus-extractor` (`extract_bulk_modulus_deform`).

---

## Rules

- **Input cell:** `npt_prod300_out.data` (the 300 K production cell) — passed as `equil_data_path`. No extra cooling.
- **Glassy only:** if `is_glassy=False`, return a RESULT block immediately — no simulation.
- **No hand-written `.in`** — generate via the `npt_deform` template.
- **STRAIN_RATE** = `K_deform_rate_inv_s` [s⁻¹] × 1e-15 → 1/fs (e.g. 1e8 × 1e-15 = 1e-7 /fs).
- **N_STEPS** = `int(K_strain_max / (STRAIN_RATE[1/fs] × dt_fs))` (e.g. 0.03 / (1e-7 × 1.0) = 300000). Verify STRAIN_RATE × N_STEPS × dt_fs ≈ K_strain_max ± 0.001.
- **FF flags:** pass `use_pcff`/`use_trappe`/`use_opls` from `lammps_flags` explicitly — without them `generate_script` defaults to AMBER/CHARMM styles and crashes on PCFF/TraPPE-UA `.data` files.

---

## 3-Direction Deformation Workflow (glassy fallback)

Run x, y, z sequentially (the extractor averages K across directions for isotropy). Total ~3× a single-direction run (~1 ns), comparable to Murnaghan.

```python
run_ids = {}
for deform_dir in ["x", "y", "z"]:
    generate_script("npt_deform", data_file=equil_data_path,
        output_script=f"{work_dir}/mechanical/deform/deform_{deform_dir}.in",
        params={
            "DEFORM_DIR":  deform_dir,
            "STRAIN_RATE": strain_rate_per_fs,
            "N_STEPS":     n_steps_deform,
            "N_EQ_STEPS":  200000,
            "THERMO_FREQ": 100,
            "DUMP_FILE":   "",
            "engine":      engine,                     # from prompt — kokkos omits `package gpu`
            "use_pcff":    lammps_flags["use_pcff"],
            "use_trappe":  lammps_flags["use_trappe"],
            "use_opls":    lammps_flags["use_opls"],
        })
    run_ids[deform_dir] = run_lammps_script(
        script=f"{work_dir}/mechanical/deform/deform_{deform_dir}.in",
        work_dir=f"{work_dir}/mechanical/deform_{deform_dir}",
        gpu_ids=gpu_ids, mpi=mpi_ranks, engine=engine)  # engine MUST match generate_script
w = watch_run(run_ids["z"])  # fires after all finish; return run_ids + w["monitor_command"] to orchestrator
# (or run each sequentially via BACKGROUND-WAIT). Do NOT call Monitor.
```

---

## Recovery Notes

**Deformation crashes:** ensure `dt_fs=1.0` (SHAKE + deform needs 1 fs). Reduce STRAIN_RATE 10× (1e-8 instead of 1e-7 /fs).
