# Stage 3: Tg Measurement
**Read when:** You have a converged equilibrated cell and need to run a Tg sweep
**Previous stage:** `STAGE_2_EQUILIBRATION.md`
**Next stage:** `STAGE_4_ANALYSIS.md` — once the sweep log is complete

---

## Critical Rules for This Stage

### Rule A: Check nvidia-smi Before Submitting

```bash
nvidia-smi
ps aux | grep python | grep -v grep | awk '{print $1, $2, substr($0, index($0,$11), 80)}'
```

If a GPU is occupied by another user, pin to the free ones via `gpu_ids`.

---

### Rule B: Simulation Time Per Temperature is System-Dependent — Verify from Literature

Do not use a fixed value. Look up the published MD protocol for your specific polymer before setting `N_STEPS_PER_T`.

**Published benchmarks:**

| Study | Time/T | System |
|---|---|---|
| Webb et al. (2024) | 4 ns burn-in + 2 ns production | General polymers |
| Afzal et al. (2021) | 4–7 ns | High-throughput polymer library |
| Klajmon et al. (2024) | Continuous cooling 1–10 K/ns | Various |

**Absolute floor:** 500 ps. 50 ps is always wrong. For most common polymers (PE, PS, PMMA, PEO) the practical range is 1–4 ns per temperature.

---

### Rule C: No Velocity Re-initialization Between Temperature Steps

Only initialize velocities **once** at the very first temperature step. Every subsequent step must inherit momenta from the previous one.

```lammps
# ❌ WRONG — re-initializing at each T discards chain relaxation state
velocity all create ${T} 12345 mom yes rot yes dist gaussian
fix 1 all nvt temp ${T} ${T} ${T_DAMP}
run ${N_STEPS_PER_T}

# ✅ CORRECT — inherit momenta (template handles this correctly)
fix 1 all nvt temp ${T} ${T} ${T_DAMP}
run ${N_STEPS_PER_T}
```

The `npt_tg_step` template handles this correctly. If you write custom scripts, verify this.

---

### Rule D: No Dump Files During Tg Sweep

`extract_tg` only needs the thermo log. Dump files during a 35-point sweep generate tens of GB of useless trajectory data and slow the simulation significantly.

```python
# In generate_script params — explicitly disable dump
params = {
    ...
    "DUMP_FILE": "",    # or set dump frequency to 0 if template supports it
}
```

---

### Rule E: Tg Sweep via lammps-engine — No Hand-Written Scripts

```python
script = lammps_engine.generate_script(
    template_name="npt_tg_step",
    ...
)
```

---

## Temperature Range Selection

The sweep must bracket the transition. Too narrow = bilinear fit fails to capture both glassy and rubbery slopes.

| Polymer | Exp Tg | Suggested Range | Notes |
|---|---|---|---|
| PE | ~195 K | 600K → 150K | Wide range needed |
| PS | ~373 K | 550K → 250K | Standard |
| PMMA | ~378 K | 550K → 250K | Standard |
| PEO/PEG | ~206 K | 450K → 150K | Similar to PE |

**Rule of thumb:**
- Start: ~1.5× expected Tg (or 600K, whichever is lower)
- End: ~0.75× expected Tg
- Total span: at least 300–350 K
- Step size: 10–20 K (smaller = better fit, more compute)

---

## Workflow

### Step 1: Look up N_STEPS_PER_T for your polymer

Search literature (arXiv, ACS, etc.) for MD Tg studies on your specific polymer before proceeding. Record what you find in your simulation log.

### Step 2: Check GPU availability

```python
execute_remote_shell_command("nvidia-smi")
```

### Step 3: Generate Tg sweep script

```python
tg_dir = "/home/arz2/simulations/<run_dir>/tg_sweep"

script = lammps_engine.generate_script(
    template_name="npt_tg_step",
    data_file="/home/arz2/simulations/<run_dir>/eq/restart_final_eq.data",
    output_script="./tg_sweep.in",
    params={
        "T_START": 600,                  # K — high temperature
        "T_END": 250,                    # K — low temperature
        "T_STEP": 10,                    # K per step
        "N_STEPS_PER_T": 2000000,        # ← verify this from literature first
        "P_START": 1,
        "P_FINAL": 1,
        "LOG_FILE": "tg_sweep.log",
        "DUMP_FILE": "",                 # No dump — thermo only
        "use_gpu": 1
    },
    upload_to_lambda=True,
    remote_output_dir=tg_dir
)
```

### Step 4: Submit sweep

```python
# Confirm free GPUs via nvidia-smi first, then assign explicitly
# Tg sweeps benefit from the most GPUs available
GPU_IDS = "0,1,2,3"  # ← replace with free GPU IDs confirmed from nvidia-smi
MPI     = 4           # ← confirm with user; match number of GPU IDs

run = lammps_engine.run_lammps_script(
    remote_script=script["remote_path"],
    remote_work_dir=tg_dir,
    log_file="tg_sweep_stdout.log",
    mpi=MPI, gpu_ids=GPU_IDS
)
print(f"Submitted: {run['run_id']}")
```

### Step 5: Monitor periodically

```python
# Check every 30 min during a long sweep — don't poll constantly
status = lammps_engine.get_run_status(run["run_id"])
log = lammps_engine.read_remote_log(run_id=run["run_id"], n_lines=30)
```

### Step 6: Verify log integrity before proceeding to Stage 4

```python
# Quick sanity check: count temperature blocks in log
execute_remote_shell_command(
    f"grep -c 'Loop time' {tg_dir}/tg_sweep.log"
)
# Should equal number of temperature steps in your sweep
```

---

## Timeline Estimation

Always use measured throughput from your equilibration logs — do not guess.

```
Total steps = (T_START - T_END) / T_STEP × N_STEPS_PER_T
Runtime (hrs) = Total steps / measured_steps_per_sec / 3600
```

**Example:** 35 temperatures × 2,000,000 steps/T = 70M steps
- lj/cut system (~183 steps/sec): 70M / 183 / 3600 ≈ **106 hrs** — but 4 GPUs parallelize, so ~26 hrs
- PPPM system (~148 steps/sec): 70M / 148 / 3600 ≈ **131 hrs** — so ~33 hrs with 4 GPUs

Adjust your Lambda session reservation accordingly before submitting.

---

## Common Failures at This Stage

**Poor bilinear fit R² (< 0.90):**
- Temperature range too narrow — extend to bracket Tg ±100K
- Insufficient time per T — increase N_STEPS_PER_T
- Velocity re-initialized at each T step (see Rule C)

**Density-temperature curve shows sharp discontinuities between T windows:**
- Velocity re-initialization (Rule C violated)
- System not equilibrated before sweep — check Stage 2 convergence

**Sweep runtime far exceeds estimate:**
- Measured throughput (PPPM vs lj/cut): check your stage 2 logs
- GPU contention from other users — check nvidia-smi

**Log file has fewer blocks than expected:**
- Simulation crashed mid-sweep. Check stdout log for LAMMPS error.
- Resume from the last valid restart file if available.

**Tg wildly off (>80K from expected):**
- Wrong force field (e.g., GAFF2_mod for pure hydrocarbons)
- Insufficient simulation time per temperature
- Temperature range missed the transition — check density vs T plot

---

**→ When sweep log is complete and has the expected number of temperature blocks, proceed to `STAGE_4_ANALYSIS.md`**
