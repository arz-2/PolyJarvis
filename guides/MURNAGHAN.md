# Murnaghan EOS Guide
**Read when:** You are `murnaghan-worker` and need to submit the bulk modulus pressure series.
**Scope:** Job submission only. Property extraction from the Murnaghan output is handled by `bulk-modulus-extractor` (`extract_bulk_modulus_murnaghan`).

---

## Rules

### Rule A: Starting Structure is the Rubbery Equil Output

The input `.data` file is the melt NPT production output for rubbery polymers (`npt_production_out.data`). Do NOT use a glassy-path file.

### Rule B: Rubbery Polymers Only

Only classes with `bm_pressures_atm` set in `polymer_rules.json` run this path (currently PHYC, PDIE). If `is_glassy=True` OR `bm_pressures_atm` is null, return immediately with all-null RESULT — do not submit any jobs.

### Rule C: `watch_run` Must Be Called as a Tool — Not the Placeholder String

`run_bulk_modulus_series` returns a `monitor_command` field in its result, but this is a placeholder string of the form `"watch_run('chain_id')"`. **This is NOT the sentinel.** You must call `watch_run(chain_id)` as a real MCP tool call. The sentinel file is created by the tool call, not by the string. Pattern (pipeline rule 6):

```
run_bulk_modulus_series(...)  → chain_id, log_files
watch_run(chain_id)           → real monitor_command  ← use this value
```

Return the tool's `monitor_command` to the orchestrator. Never pass the placeholder string.

### Rule D: Pass Explicit `gpu_ids` and `mpi`

Do not accept `run_bulk_modulus_series` defaults. Always pass the values from your prompt:
```python
run_bulk_modulus_series(
    ...
    gpu_ids=gpu_ids,
    mpi=mpi_ranks,
)
```

### Rule E: `npt_steps` Per Pressure Point

Default: 500,000 steps (0.5 ns at 1 fs) at `temp_K=300.0 K`.

### Rule F: Pass the Force-Field Flags from `lammps_flags`

Pass `use_trappe` / `use_pcff` / `use_opls` from your prompt's `lammps_flags` dict into
`run_bulk_modulus_series`. **The tool defaults to the AMBER/CHARMM npt template** (`lj/charmm/coul/long`
+ `pppm` + `dihedral fourier`), which mismatches TraPPE-UA/PCFF `.data` coeffs and **silently corrupts
K** (PE1 R-03). The tool derives `use_pppm`/`LJ_CUTOFF`/`use_shake` internally from the FF selector — you
only set the one selector that is `true`.

---

## Murnaghan Workflow

```python
result = run_bulk_modulus_series(
    data_file=equil_data_path,
    work_dir=work_dir,          # .../prop/bm_series/
    pressures_atm=bm_pressures_atm,  # e.g. [1, 100, 300, 600, 1000]
    temp_K=300.0,
    run_name=run_name,
    gpu_ids=gpu_ids,
    mpi=mpi_ranks,
    npt_steps=npt_steps,        # from prompt (default 500000)
    use_trappe=lammps_flags["use_trappe"],   # Rule F — FF selector from prompt's lammps_flags
    use_pcff=lammps_flags["use_pcff"],       # tool derives pppm/cutoff/shake internally
    use_opls=lammps_flags["use_opls"],
)
chain_id = result["chain_id"]
log_files = result["log_files"]  # list of absolute paths, one per pressure

w = watch_run(chain_id)           # MCP tool call — creates sentinel
monitor_command = w["monitor_command"]

# Return chain_id, log_files, and monitor_command to orchestrator — do NOT call Monitor.
```

---

## Defaults Reference

| Parameter | Default | Notes |
|-----------|---------|-------|
| `temp_K` | 300.0 | Fixed — isothermal |
| `npt_steps` | 500000 | 0.5 ns at 1 fs; reduce to 200000 if GPU OOMs |
| `pressures_atm` | from `polymer_rules.json` | [1, 100, 300, 600, 1000] for PHYC/PDIE |

---

## Recovery Notes

**One pressure point fails / GPU OOM:** Reduce `npt_steps` to 200000 and re-submit.

**`run_bulk_modulus_series` returns empty `log_files`:** Check GPU memory with `nvidia-smi`. Re-submit with half `npt_steps`.

**Monitor hangs after watch_run returns:** Sentinel was not created. Most likely `watch_run` was called with the placeholder string instead of the real `chain_id`. Re-submit: `run_bulk_modulus_series` → `watch_run(chain_id)` (tool call).
