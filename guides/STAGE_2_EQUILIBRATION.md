# Stage 2: Equilibration
**Read when:** You have a `.data` file and need to equilibrate it on Lambda
**Previous stage:** `STAGE_1_MOLECULAR_CONSTRUCTION.md`
**Next stage:** `STAGE_3_TG_MEASUREMENT.md` — once you have a converged equilibrated cell

---

## Critical Rules for This Stage

### Rule A: All Scripts Through lammps-engine — No Exceptions
```python
# ❌ WRONG — hand-written .in file
with open("npt.in", "w") as f:
    f.write("fix 1 all npt ...")

# ✅ CORRECT — always use generate_script()
script = lammps_engine.generate_script(
    template_name="npt",
    data_file=remote_data_path,
    output_script="./npt_eq.in",
    params={...},
    upload_to_lambda=True
)
```

**Why:** Templates are validated, version-controlled, and contain correct SHAKE constraints, GPU package settings, and restart logic. Hand-written scripts introduce silent errors.

---

### Rule B: Check nvidia-smi Before Every Submission

**Always do this before running any simulation.** Lambda machines are shared — another user's job can silently saturate a GPU.

```bash
# Run via execute_remote_shell_command before every submission:
nvidia-smi
ps aux | grep python | grep -v grep | awk '{print $1, $2, substr($0, index($0,$11), 80)}'
```

**What to check:**
- Memory used per GPU (should be near 0 if free)
- Utilization % (should be 0% if free)
- Other users' PIDs holding GPU memory

**If a GPU is occupied:** Pin your job to the free ones via `gpu_ids` (e.g., `gpu_ids="1,2,3"` if GPU 0 is taken).

---

### Rule C: GPU is Used for ALL Stages — Always Specify gpu_ids and mpi Explicitly

GPU is used for every simulation stage including NPT. Before every submission, check `nvidia-smi` to identify free GPUs, then pass those IDs explicitly. Never leave `gpu_ids` unset — the default behavior pins to GPU 0 regardless of what is free.

```python
# ❌ WRONG — defaults to GPU 0, contends with other jobs
run_lammps_script(script, mpi=4, gpu_ids="")

# ✅ CORRECT — user confirms free GPUs first, then assigns explicitly
run_lammps_script(script, mpi=4, gpu_ids="1,2,3")  # example: GPU 0 is occupied
```

**Always ask the user (or check nvidia-smi) for:**
- Which GPU IDs are free
- How many MPI processes to use

Do not assume. Do not default.

---

### Rule D: Never Skip Annealing Cycles

Minimum 3 cycles (5 for publication). Skipping leads to incorrect density, chain droplets, and unreliable Tg.

---

## Standard Equilibration Protocol

### Minimum Acceptable (screening)
```
1. Minimize         (10,000 steps)                 [GPU]
2. NPT Compress     (600K, 1→50,000 atm, 1 ns)    [GPU]
3. Anneal ×3        (300K↔600K, 500 ps each)       [GPU]
4. NPT Final eq     (300K, 1 atm, 2 ns)            [GPU]
Total: ~4 ns
```

### Standard Production
```
1. Minimize         (10,000 steps)                 [GPU]
2. NVT Soft heat    (optional, 300K, 500 ps)       [GPU] 
3. NPT Compress     (600K, 1→50,000 atm, 1 ns)    [GPU]
4. Anneal ×3-5      (300K↔600K, 500 ps each)       [GPU]
5. NPT Final eq     (300K, 1 atm, 2 ns)            [GPU]
6. NVT Production   (300K, 2 ns)                   [GPU]
Total: ~7-9 ns
```

---

## Workflow

### Step 1: Check GPU availability
```python
execute_remote_shell_command("nvidia-smi")
```

### Step 2: Upload `.data` file to Lambda
```python
# Use upload_file_to_remote or execute_remote_shell_command with scp
# Target: /home/arz2/simulations/<run_dir>/cell.data
```

### Step 3: Parse data file
```python
info = lammps_engine.parse_data_file(
    data_file="/home/arz2/simulations/<run_dir>/cell.data",
    remote=True
)
# Check: n_atoms, atom_types, h_type_ids (for SHAKE), estimated_memory
```

### Step 4: Generate and chain scripts

```python
work_dir = "/home/arz2/simulations/<run_dir>/eq"
data_file = "/home/arz2/simulations/<run_dir>/cell.data"

# Stage 1: Minimize
s_min = lammps_engine.generate_script(
    template_name="minimize",
    data_file=data_file,
    output_script="./01_minimize.in",
    params={"N_STEPS": 10000, "LOG_FILE": "01_minimize.log"},
    upload_to_lambda=True, remote_output_dir=work_dir
)

# Stage 2: NPT Compress (CPU — no gpu_ids)
s_compress = lammps_engine.generate_script(
    template_name="npt_compress",
    data_file=f"{work_dir}/restart_minimize.data",
    output_script="./02_compress.in",
    params={
        "T_START": 300, "T_FINAL": 600,
        "P_START": 1, "P_FINAL": 50000,
        "N_STEPS": 1000000,
        "LOG_FILE": "02_compress.log"
    },
    upload_to_lambda=True, remote_output_dir=work_dir
)

# Stages 3-N: Annealing cycles (generate in loop, each takes restart from previous)
anneal_scripts = []
for i in range(3):
    prev_restart = f"{work_dir}/restart_compress.data" if i == 0 else f"{work_dir}/restart_cool{i}.data"
    s_heat = lammps_engine.generate_script(
        template_name="npt",
        data_file=prev_restart,
        output_script=f"./0{3+i*2}_heat{i+1}.in",
        params={"T_START": 300, "T_FINAL": 600, "P_START": 1, "P_FINAL": 1,
                "N_STEPS": 500000, "LOG_FILE": f"heat{i+1}.log"},
        upload_to_lambda=True, remote_output_dir=work_dir
    )
    s_cool = lammps_engine.generate_script(
        template_name="npt",
        data_file=f"{work_dir}/restart_heat{i+1}.data",
        output_script=f"./0{4+i*2}_cool{i+1}.in",
        params={"T_START": 600, "T_FINAL": 300, "P_START": 1, "P_FINAL": 1,
                "N_STEPS": 500000, "LOG_FILE": f"cool{i+1}.log"},
        upload_to_lambda=True, remote_output_dir=work_dir
    )
    anneal_scripts.extend([s_heat, s_cool])

# Final equilibration
s_final = lammps_engine.generate_script(
    template_name="npt",
    data_file=f"{work_dir}/restart_cool3.data",
    output_script="./final_eq.in",
    params={"T_START": 300, "T_FINAL": 300, "P_START": 1, "P_FINAL": 1,
            "N_STEPS": 2000000, "LOG_FILE": "final_eq.log"},
    upload_to_lambda=True, remote_output_dir=work_dir
)
```

### Step 5: Execute sequence (each waits for previous to complete)

```python
def run_and_wait(script_remote_path, work_dir, log_file, mpi, gpu_ids, poll_sec=60):
    run = lammps_engine.run_lammps_script(
        remote_script=script_remote_path,
        remote_work_dir=work_dir,
        log_file=log_file,
        mpi=mpi, gpu_ids=gpu_ids
    )
    while lammps_engine.get_run_status(run["run_id"])["status"] not in ("completed", "failed"):
        time.sleep(poll_sec)
    result = lammps_engine.get_run_output(run["run_id"])
    if result["status"] != "completed":
        raise RuntimeError(f"Stage failed: {log_file}")
    return result

# Replace gpu_ids and mpi with values confirmed free via nvidia-smi
# Example assumes GPUs 1,2,3 are free and user has confirmed mpi=4
GPU_IDS = "1,2,3"   # ← set from nvidia-smi check
MPI     = 4         # ← confirm with user

run_and_wait(s_min["remote_path"],      work_dir, "01_minimize.log",  mpi=MPI, gpu_ids=GPU_IDS)
run_and_wait(s_compress["remote_path"], work_dir, "02_compress.log",  mpi=MPI, gpu_ids=GPU_IDS)
for s in anneal_scripts:
    run_and_wait(s["remote_path"],      work_dir, s["log_file"],       mpi=MPI, gpu_ids=GPU_IDS)
run_and_wait(s_final["remote_path"],   work_dir, "final_eq.log",      mpi=MPI, gpu_ids=GPU_IDS)
```

---

## GPU Selection Reference

GPU is used for all stages. `gpu_ids` and `mpi` must always be set explicitly based on what is free.

| System Size | Recommended MPI | Notes |
|---|---|---|
| <10k atoms | 2 | 2 GPUs sufficient |
| 10-20k atoms | 2-4 | 2 GPUs standard, 4 for faster throughput |
| 20-40k atoms | 4 | Use all available free GPUs |

**Always confirm with nvidia-smi before assigning.** Pass only the IDs of GPUs confirmed to be free.

```python
# Example: all 4 GPUs free
mpi=4, gpu_ids="0,1,2,3"

# Example: GPU 0 occupied by another user
mpi=3, gpu_ids="1,2,3"

# Example: GPUs 0 and 2 occupied
mpi=2, gpu_ids="1,3"
```

---

## Convergence Check (Before Marking Stage Complete)

Check the final equilibration log before moving to Stage 3. Do not skip.

```python
log = lammps_engine.read_remote_log(
    remote_log_path=f"{work_dir}/final_eq.log",
    n_lines=500
)
# Look for: density_stable=True, temperature_stable=True in convergence_hints
```

**Convergence criteria:**
- Density fluctuation < 2% over last 50% of trajectory
- Temperature stable within ±5 K
- No monotonic drift in energy

**If not converged:** Extend final equilibration by 1-2 ns before proceeding.

---

## Benchmark Throughput After First Stage

After the minimize or compress stage completes, grep the performance line to get actual steps/sec. Do not estimate — charged systems (PEG, PS, PMMA) run ~20% slower than hydrocarbons due to PPPM.

```bash
grep "Performance" /path/to/stage.log | tail -1
# Output: Performance: 148.3 ns/day, 0.162 hours/ns, 148.3 timesteps/s
```

Use this measured rate for all subsequent timeline estimates.

---

## Common Failures at This Stage

**GPU crash during NPT:** Restart file writing conflict. Switch to CPU for all NPT stages.

**Density not converging:** Add more annealing cycles. Minimum 3, up to 5.

**Chain droplets / vacuum voids visible:** Initial density too high. Rebuild cell at `density=0.05`. Add more annealing.

**Timeline wildly off from estimate:** Measure actual throughput from first log (see above). Charged systems with PPPM are slower.

**Another user is on the GPU:** Always check `nvidia-smi` first. Pin to free GPUs via `gpu_ids`.

---

**→ When final_eq.data is saved and density has converged, proceed to `STAGE_3_TG_MEASUREMENT.md`**
