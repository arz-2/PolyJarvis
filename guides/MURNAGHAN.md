# Murnaghan EOS Guide
**Read when:** You are `murnaghan-worker` and need to submit the bulk modulus pressure series.
**Scope:** Job submission only. Property extraction from the Murnaghan output is handled by `bulk-modulus-extractor` (`extract_bulk_modulus_murnaghan`).

---

## Rules

### Rule A: Starting Structure Depends on Phase

- **Glassy path (`is_glassy=True`):** input is `npt_prod300_out.data` — the 300 K equilibrated structure. This is the primary glassy bulk modulus method (replaces Born+NVT, which is removed). Pressure range: ±1000 atm symmetric (e.g. `[-1000, -500, 0, 500, 1000]`). Each pressure point: 0.3–0.5 ns NPT at 300 K.
- **Rubbery path (`is_glassy=False`):** input is `npt_production_out.data` — the melt NPT output at T_equil_K. Pressure range and npt_steps from `bm_pressures_atm` and `npt_steps` in your prompt.

Do NOT swap these: the glassy path needs the 300 K cell (chains in glassy state); the rubbery path needs the melt cell (volume larger, compressible).

### Rule B: This Path Now Runs for Both Glassy and Rubbery Polymers

- **Glassy (`is_glassy=True`):** always run this path. Born+NVT has been removed.
- **Rubbery (`is_glassy=False`) with `bm_pressures_atm` set:** run this path (unchanged).
- **Rubbery with `bm_pressures_atm` null:** return immediately with all-null RESULT — fluctuation path, no job needed.

### Rule B1: Glassy Acceptance Gate

For glassy polymers, gate on `volume_equilibrated=True` at **each** pressure point after extraction. To first order ΔV/V ≈ ΔP/K, so 1000 atm (0.1013 GPa) gives ΔV/V ≈ **1.3–2.5%** for a glass with K ≈ 4–8 GPa (≈2.0% at K=5 GPa). If any point shows `volume_equilibrated=False`, report RESULT with `fit_quality: BORDERLINE` and note "pressure point N not equilibrated — consider narrowing pressure range to ±500 atm". Accept if B0_prime ∈ [4, 20]; flag BORDERLINE if outside.

For very stiff polymers (K > 8 GPa, e.g. PEEK), ΔV per 1000 atm step is smaller (~1.0–1.3%) and EOS curvature may be insufficient. Widen to ±2000 atm if `fit_converged=False` at ±1000 atm. For typical glassy polymers (K ≈ 3–6 GPa, PVC/PMMA/PSU-class), ±1000 atm gives ΔV/V ≈ 1.7–3.4% — adequate curvature (r² ≥ 0.999 expected).

### Rule C: `watch_run` Must Be Called as a Tool — Not the Placeholder String

`run_bulk_modulus_series` returns a placeholder string like `"watch_run('chain_id')"` — **this is NOT the sentinel**. You must call `watch_run(chain_id)` as a real MCP tool call, then return its `monitor_command` to the orchestrator.

### Rule D: Pass Explicit `gpu_ids`, `mpi`, and `engine`

Do not accept `run_bulk_modulus_series` defaults. Always pass the values from your prompt:
```python
run_bulk_modulus_series(
    ...
    gpu_ids=gpu_ids,
    mpi=mpi_ranks,
    engine=engine,        # from prompt — "kokkos" for PCFF/OPLS, "gpu" for TraPPE
)
```
**`engine` is mandatory.** PCFF/OPLS cells must run on `engine="kokkos"` (full GPU
offload). If you omit it the tool defaults to the GPU package, which leaves the
class2 bonded terms + PPPM on the CPU and runs ~7.9× slower (the PSU1 failure mode).

### Rule E: `npt_steps` Per Pressure Point

Default: 500,000 steps (0.5 ns at 1 fs) at `temp_K=300.0 K`.

### Rule F: Pass the Force-Field Flags from `lammps_flags`

Pass `use_trappe` / `use_pcff` / `use_opls` from your prompt's `lammps_flags` dict into `run_bulk_modulus_series`. The tool derives `use_pppm`/`LJ_CUTOFF`/`use_shake` internally — set only the one selector that is `true`.

---

## Murnaghan Workflow

```python
# Glassy path: use npt_prod300_out.data and ±1000 atm symmetric range
# Rubbery path: use npt_production_out.data and bm_pressures_atm from prompt
pressures = bm_pressures_atm if not is_glassy else [-1000, -500, 0, 500, 1000]
temp_K_run = 300.0  # always 300 K (glassy: equilibrated at 300 K; rubbery: 300 K reference)

result = run_bulk_modulus_series(
    data_file=equil_data_path,   # npt_prod300_out.data (glassy) or npt_production_out.data (rubbery)
    work_dir=work_dir,           # .../mechanical/bm_series/
    pressures_atm=pressures,
    temp_K=temp_K_run,
    run_name=run_name,
    gpu_ids=gpu_ids,
    mpi=mpi_ranks,
    npt_steps=npt_steps,         # from prompt (default 500000 = 0.5 ns at 1 fs)
    use_trappe=lammps_flags["use_trappe"],   # Rule F — FF selector from prompt's lammps_flags
    use_pcff=lammps_flags["use_pcff"],       # tool derives pppm/cutoff/shake internally
    use_opls=lammps_flags["use_opls"],
    engine=engine,
)
chain_id = result["chain_id"]
log_files = result["log_files"]  # list of absolute paths, one per pressure

w = watch_run(chain_id)           # MCP tool call — creates sentinel
monitor_command = w["monitor_command"]

# Return chain_id, log_files, and monitor_command to orchestrator — do NOT call Monitor.
```

---

## Recovery Notes

**One pressure point fails / GPU OOM:** Reduce `npt_steps` to 200000 and re-submit.

**`run_bulk_modulus_series` returns empty `log_files`:** Check GPU memory with `nvidia-smi`. Re-submit with half `npt_steps`.

**BACKGROUND-WAIT waiter never returns after watch_run:** Sentinel was not created. Most likely `watch_run` was called with the placeholder string instead of the real `chain_id`. Re-submit: `run_bulk_modulus_series` → `watch_run(chain_id)` (tool call).
