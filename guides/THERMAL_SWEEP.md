# Tg Sweep Guide
**Read when:** You have a converged equilibrated cell and need to run a Tg sweep  
**Worker:** tg-sweep-worker — generate sweep script, submit run, return RESULT block to orchestrator

---

## Rules

### Rule A: No Velocity Re-initialization Between Temperature Steps

Only initialize velocities once at the very first temperature step. Every subsequent step inherits momenta from the previous one.

### Rule B: No Dump Files During Tg Sweep

Set `"DUMP_FILE": ""` in the `generate_script` params. Dump files across a 35-point sweep generate tens of GB of useless data and slow the run.

### Rule C: Simulation Time Per T is System-Dependent

**Absolute floor: 500 ps.** For most common polymers (PE, PS, PMMA, PEO): 1–4 ns per temperature.

TraPPE-UA classes (PHYC, PDIE) use `dt_fs=2.0` (no SHAKE — UA eliminates C-H fast modes). Halve `N_STEPS_PER_T` relative to PCFF to maintain the same cooling rate.

---

## Temperature Range Selection

The sweep must bracket the transition — too narrow and the bilinear fit fails to capture both slopes.

Rule of thumb: start ~1.5× Tg, end ~0.75× Tg, span ≥300 K, step 10–20 K.

---

## Workflow

### Step 1: Generate Tg sweep script

`generate_script` is synchronous — returns the script path immediately.

For TraPPE-UA systems (`use_trappe=True`), detect the number of bond types before generating the script:
```bash
n_bond_types=$(grep -m1 "bond types" <equil_data_path> | awk '{print $1}')
# shake_bond_type_ids = list(range(1, n_bond_types + 1)), e.g. [1] for PE, [1, 2] for PBD
```

```python
result = generate_script(
    template_name="npt_tg_step",
    output_script="<work_dir>/thermal/tg_sweep/tg_sweep.in",
    data_file=equil_data_path,
    params={
        "LOG_FILE":            "tg_sweep.log",
        "DUMP_FILE":           "",       # Rule B — no dump
        "T_START":             <T_start>,
        "T_END":               <T_end>,
        "T_STEP":              <T_step>,
        "N_STEPS_PER_T":       <n_steps_per_t>,
        "P_START":             1.0,
        "P_FINAL":             1.0,
        "T_DAMP":              100.0,
        "TIMESTEP":            <dt_fs from prompt>,  # 2.0 for TraPPE-UA, 1.0 otherwise
        "use_pppm":            <True unless TraPPE-UA>,
        "use_gpu":             True,
        "use_pcff":            <from lammps_flags>,
        "use_trappe":          <from lammps_flags>,
        "use_shake":           False,    # False for TraPPE-UA and PCFF; True for GAFF2
        "shake_bond_type_ids": <omit for TraPPE-UA and PCFF; only relevant for GAFF2>,
        "params_file":         "<work_dir>/emc_build.params",  # EMC only; omit for RadonPy
        "write_restart":       False,
    }
)
```

### Step 2: Submit sweep

`run_lammps_script` is async — returns `run_id` immediately.

```python
run = run_lammps_script(
    script=result["output_script"],
    work_dir="<work_dir>/thermal/tg_sweep",
    log_file="tg_sweep_run.log",
    gpu_ids="<from orchestrator>",
    mpi=<n>,
)
w = watch_run(run["run_id"])
# Return run_id and w["monitor_command"] to the orchestrator — do not call Monitor.
```

---

## Common Failures

**Tg sweep killed mid-run:**
- *User action (intentional kill):* Stop immediately; do not re-queue — wait for user instruction.
- *System failure (GPU/LAMMPS error):* Attempt to restart from the last completed temperature (max 2 recovery attempts). If still failing, return the error to the orchestrator.
