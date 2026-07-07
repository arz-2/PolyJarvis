# Murnaghan EOS Guide
**Read when:** You are `murnaghan-worker` and need to submit the bulk modulus pressure series.
**Scope:** Job submission only. Property extraction is handled by `bulk-modulus-extractor` (`extract_bulk_modulus_murnaghan`).

---

## Rules

**Starting structure by phase** (do NOT swap):
- Glassy (`is_glassy=True`): `npt_prod300_out.data` — the 300 K equilibrated cell (primary glassy K method).
- Rubbery (`is_glassy=False`): `npt_production_out.data` — the melt NPT output at T_equil.

The orchestrator passes the correct cell as `equil_data_path`.

**When to submit:**
- Glassy → always submit (the prompt's `### ASSERTION` reinforces this even if `bm_pressures_atm` is null).
- Rubbery with `bm_pressures_atm` set → submit.
- Rubbery with `bm_pressures_atm` null → return an all-null RESULT (fluctuation path, no job).

**Pressure range** comes from the prompt's `bm_pressures_atm` (± symmetric for typical glasses;
PEST/PKTN and other stiff classes use a compression-biased range). On a `fit_converged=False`
re-submit, widen the **compression** side (e.g. `[-1000, 0, 1500, 3000, 5000]`), never
symmetrically — wide tension (< −5000 atm) cavitates the cell.

**`engine` is mandatory** — pass the prompt's value. PCFF/OPLS must run `engine="kokkos"` (full
GPU offload); the GPU-package default leaves class2 bonded + PPPM on the CPU (~7.9× slower, the
PSU1 failure mode).

**FF flags:** pass only the one true selector from `lammps_flags` (`use_pcff`/`use_opls`/`use_trappe`);
the tool derives `use_pppm`/`LJ_CUTOFF`/`use_shake` internally.

**`watch_run` is a tool call.** `run_bulk_modulus_series` returns a placeholder string like
`"watch_run('chain_id')"` — that is NOT the sentinel. Call `watch_run(chain_id)` as a real MCP
tool, then return its `monitor_command`.

---

## Workflow

```python
pressures = bm_pressures_atm if bm_pressures_atm else [-1000, -500, 0, 500, 1000]

result = run_bulk_modulus_series(
    data_file=equil_data_path,   # npt_prod300_out.data (glassy) or npt_production_out.data (rubbery)
    work_dir=work_dir,           # .../mechanical/bm_series/
    pressures_atm=pressures,
    temp_K=temp_K,               # from prompt (300 K)
    run_name=run_name,
    gpu_ids=gpu_ids,
    mpi=mpi_ranks,
    npt_steps=npt_steps,         # from prompt (default 500000 = 0.5 ns at 1 fs)
    use_trappe=lammps_flags["use_trappe"],
    use_pcff=lammps_flags["use_pcff"],
    use_opls=lammps_flags["use_opls"],
    engine=engine,
)
chain_id  = result["chain_id"]
log_files = result["log_files"]  # absolute paths, one per pressure

w = watch_run(chain_id)          # MCP tool call — creates sentinel
# Return chain_id, log_files, w["monitor_command"] to the orchestrator — do NOT call Monitor.
```

---

## Recovery Notes

**One pressure point fails / GPU OOM / empty `log_files`:** reduce `npt_steps` to 200000 and re-submit (check `nvidia-smi`).

**BACKGROUND-WAIT never returns after watch_run:** sentinel not created — `watch_run` was likely
called with the placeholder string, not the real `chain_id`. Re-run `watch_run(chain_id)` as a tool call.
