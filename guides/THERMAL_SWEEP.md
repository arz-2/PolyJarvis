# Tg Sweep Guide
**Read when:** You have a converged equilibrated cell and need to run a Tg sweep
**Worker:** tg-sweep-worker — generate sweep script, submit run, return RESULT block to orchestrator

---

## Rules

- **No velocity re-init between temperature steps** — the `npt_tg_step` template initializes velocities once at the first step; every later step inherits momenta.
- **No trajectory dump** — set `DUMP_FILE=""`. For per-T structural snapshots, pass the prompt's `per_t_dump` params (`WRITE_PER_T_DUMP=True`, `PER_T_DUMP_FILE`) — one single-frame snapshot per T step, negligible I/O.
- **`use_gpu=True` always** — the generated deck includes GPU package directives; `use_gpu=False` strips them while leaving GPU syntax → runtime crash. Preserve it exactly on any resubmit; the crash is never caused by GPU use itself.

---

## Workflow

### Step 1: Generate Tg sweep script

`generate_script` is synchronous — returns the script path immediately. Use `tg_sweep_dir` from
the prompt (rate-suffixed for multi-rate, e.g. `.../tg_sweep_r40`); analyze-tg reads
`tg_sweep_dir/tg_sweep.log`. Never hardcode `.../thermal/tg_sweep/` — it collides across rates.

For TraPPE-UA systems (`use_trappe=True`), detect bond types before generating:
```bash
n_bond_types=$(grep -m1 "bond types" <equil_data_path> | awk '{print $1}')
# shake_bond_type_ids = list(range(1, n_bond_types + 1)), e.g. [1] for PE, [1, 2] for PBD
```

```python
progress_file = f"{tg_sweep_dir}/tg_progress.jsonl"

result = generate_script(
    template_name="npt_tg_step",
    output_script=f"{tg_sweep_dir}/tg_sweep.in",
    data_file=equil_data_path,        # MUST be absolute — see caveat below
    velocity_seed=<velocity_seed from prompt, or None>,
    params={
        "LOG_FILE":            "tg_sweep.log",
        "DUMP_FILE":           "",
        "T_START":             <T_start>,
        "T_END":               <T_end>,
        "T_STEP":              <T_step>,
        "N_STEPS_PER_T":       <n_steps_per_t>,
        "P_START":             1.0,
        "P_FINAL":             1.0,
        "T_DAMP":              100.0,
        "TIMESTEP":            <dt_fs from prompt>,
        "use_pppm":            <True unless TraPPE-UA>,
        "use_gpu":             True,
        "engine":              <engine from prompt>,
        "use_pcff":            <lammps_flags["use_pcff"]>,
        "use_opls":            <lammps_flags["use_opls"]>,
        "use_trappe":          <lammps_flags["use_trappe"]>,
        # ↑ ALWAYS pass all three FF booleans verbatim from lammps_flags — on an equilibrated
        # .data the engine cannot always re-derive the FF; a wrong/missing flag now hard-fails
        # with "FF flag mismatch" rather than silently emitting a corrupt GAFF2 deck.
        "use_shake":           False,    # False for TraPPE-UA and PCFF; True for GAFF2
        "shake_bond_type_ids": <omit for TraPPE-UA and PCFF; only for GAFF2>,
        "params_file":         "<work_dir>/emc_build.params",  # EMC only; omit for RadonPy
        "PROGRESS_FILE":       progress_file,   # per-T PROGRESS lines in the watch_run monitor_command
    }
)
# result["n_tg_stages"] = number of temperature steps (for run_lammps_script)
```

**Velocity seed caveat:** the `npt_tg_step` template emits `velocity all create T <fresh random>`
and does NOT honor the `velocity_seed` arg — to record the actual seed, grep the generated `.in`
for the `velocity all create` line and log field **$5** (the integer after T_START), not the passed value.

**Absolute `data_file`.** The sweep `work_dir` is a sibling of the equil cell, so a relative
`data_file` hits a silent `read_data` failure. Resolve against `REPO_ROOT`, and `grep read_data`
the generated `.in` to confirm the absolute path before submitting.

**Verify the FF before submitting** — `grep` the generated `.in`; abort if it shows a GAFF2 deck:
```bash
grep -E 'pair_style|dihedral_style|kspace' "<tg_sweep_dir>/tg_sweep.in"
# TraPPE-UA → "pair_style lj/cut ..." + "dihedral_style multi/harmonic", NO kspace/pppm
# PCFF      → "pair_style lj/class2/coul/long ..." + "kspace_style pppm ..."
# GAFF2 leak (lj/charmm... / dihedral_style fourier) = wrong → do NOT submit
```

**GPU neighbor list (small PCFF cells <5k atoms):** edit `package gpu 1 neigh no` → `neigh yes`
for +30% (NPT-stable; not for kokkos — it manages its own neighbor list).

### Step 2: Submit sweep

`run_lammps_script` is async — returns `run_id` immediately.
```python
run = run_lammps_script(
    script=result["output_script"],
    work_dir=tg_sweep_dir,
    log_file="tg_sweep_run.log",
    gpu_ids="<from prompt>",
    mpi=<n>,
    engine=<engine from prompt>,   # MUST match the generate_script engine
    progress_file=progress_file,
    n_stages=result["n_tg_stages"],
)
w = watch_run(run["run_id"])
# Return run_id and w["monitor_command"] to the orchestrator — do not call Monitor.
```

---

## Common Failures

**Tg sweep killed mid-run:** restart from the last completed temperature (max 2 attempts); if still failing, return the error to the orchestrator.
