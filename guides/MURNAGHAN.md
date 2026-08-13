# Murnaghan EOS Guide
**Read when:** You are `murnaghan-worker` and need to submit the bulk modulus pressure series.
**Scope:** Job submission only. Property extraction is handled by `bulk-modulus-extractor` (`extract_bulk_modulus_murnaghan`).

---

## Rules

**Starting structure by phase** (do NOT swap):
- Glassy (`is_glassy=True`): `npt_prod300_out.data` — the 300 K equilibrated cell (primary glassy K method).
- Rubbery (`is_glassy=False`): `npt_production_out.data` — the melt NPT output at T_equil.

The orchestrator passes the correct cell as `equil_data_path`.

**Always submit** — glassy and rubbery both, regardless of whether `bm_pressures_atm` is set.

**Pressure range** comes from the prompt's `bm_pressures_atm`. If null:
- Glassy: `[-1000, 0, 3000, 7000, 15000]`. Never apply this array to a rubbery class.
- Rubbery: the **PROBE ladder** `[-200, 0, 3000, 7000, 15000]` — compression is validated
  safe at any cohesion level; the shallow tension point is a conservative probe, not a
  proven-safe depth. The orchestrator (`MECHANICAL_TRACK.md`) drives a two-leg protocol
  around this: if the probe point survives clean, it re-spawns this worker with
  `bm_pressures_atm=[-1000]` alone (Leg 2, single-point, merged with Leg 1's compression
  logs). This worker just submits whatever `bm_pressures_atm` it's given each call — it
  does not decide the legs.

**`engine` is mandatory** — pass the prompt's value.

**FF flags:** pass only the one true selector from `lammps_flags` (`use_pcff`/`use_opls`/`use_trappe`).

**`watch_run` is a tool call.** `run_bulk_modulus_series` returns a placeholder string like
`"watch_run('chain_id')"` — that is NOT the sentinel. Call `watch_run(chain_id)` as a real MCP
tool, then return its `monitor_command`.

---

## Workflow

```python
if bm_pressures_atm:
    pressures = bm_pressures_atm          # class-tuned ladder, or Leg 2's [-1000]
elif is_glassy:
    pressures = [-1000, 0, 3000, 7000, 15000]   # glassy universal fallback
else:
    pressures = [-200, 0, 3000, 7000, 15000]    # rubbery PROBE ladder (Leg 1)

# Pass every argument below on every call, including the ones whose value is null. Omitting one
# is a schema error, not a default.
result = run_bulk_modulus_series(
    data_file=equil_data_path,   # npt_prod300_out.data (glassy) or npt_production_out.data (rubbery)
    work_dir=work_dir,           # .../mechanical/bm_series/
    pressures_atm=pressures,
    temp_K=temp_K,               # from prompt (300 K)
    run_name=run_name,
    gpu_ids=gpu_ids,
    mpi=mpi_ranks,
    velocity_seed=velocity_seed,   # from prompt — required, never null
    npt_steps=npt_steps,         # from prompt (default 500000 = 0.5 ns at 1 fs)
    dt_fs=dt_fs,                 # from prompt — the 1.0 default silently halves a TraPPE-UA deck
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
