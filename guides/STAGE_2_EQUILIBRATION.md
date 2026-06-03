# Stage 2: Equilibration
**Read when:** You have a `.data` file and need to equilibrate it
**Previous stage:** `STAGE_1_MOLECULAR_CONSTRUCTION.md`
**Next stage:** `STAGE_3_TG_MEASUREMENT.md` — once you have a converged equilibrated cell
**Revision parameters:** `REVISION_PARAMS.md` — per-polymer dp, nchain, density_initial, T_equil for all 8 revision polymers

---

## Critical Rules for This Stage

### Rule A: All Scripts Through lammps-engine — No Exceptions
```python
# ❌ WRONG — hand-written .in file
with open("npt.in", "w") as f:
    f.write("fix 1 all npt ...")

# ✅ CORRECT — always use generate_equilibration_workflow
workflow = lammps_engine.generate_equilibration_workflow(
    data_file="/home/arz2/simulations/<run_dir>/cell.data",
    work_dir_base="/home/arz2/simulations/<run_dir>",
    use_pcff=True,   # or use_opls=True / neither for TraPPE-UA
    params_file="/home/arz2/polyjarvis_emc_jobs/<job_id>/emc_build.params",  # EMC only
)
```

**Why:** Templates are validated, version-controlled, and contain correct GPU package settings, pair styles, and restart logic. Hand-written scripts introduce silent errors. SHAKE is automatically disabled for PCFF (`bond_style class2` is incompatible with `fix shake`).

---

### Rule B: Check nvidia-smi Before Every Submission

**Always do this before running any simulation.** The GPU node is shared — another user's job can silently saturate a GPU.

```bash
nvidia-smi --query-gpu=index,memory.used,utilization.gpu --format=csv,noheader
ps aux | grep lmp | grep -v grep
```

**What to check:**
- Memory used per GPU (should be near 0 if free)
- Utilization % (should be 0% if free)
- Other users' PIDs holding GPU memory

**If a GPU is occupied:** Pin your job to the free ones via `gpu_ids` (e.g., `gpu_ids="1,2,3"` if GPU 0 is taken).

---

### Rule C: GPU is Used for ALL Stages — Always Specify gpu_ids and mpi Explicitly

GPU is used for every simulation stage including NPT. Before every submission, check `nvidia-smi` to identify free GPUs, then pass those IDs explicitly. Never leave `gpu_ids` unset — the default behavior pins to GPU 0 regardless of what is free.

```bash
# ❌ WRONG — omitting -pk gpu means CPU fallback
mpirun -np 4 lmp -in stage.in

# ✅ CORRECT — always explicit GPU flags
mpirun -np 4 lmp -pk gpu 4 -sf gpu -in stage.in
```

Check `nvidia-smi` first and confirm which GPU IDs are free. Pass only free IDs. Do not assume all 4 are available.

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
```bash
nvidia-smi --query-gpu=index,memory.used,memory.free,utilization.gpu --format=csv,noheader
```

### Step 2: Confirm .data file path
```python
# The .data file is already local — no upload needed.
# EMC jobs write to:  /home/arz2/polyjarvis_emc_jobs/<job_id>/emc_build.data
# RadonPy jobs write to wherever save_lammps_data() was called.
# Copy or symlink to a clean sim directory:
import shutil
shutil.copy("/home/arz2/polyjarvis_emc_jobs/<job_id>/emc_build.data",
            "/home/arz2/simulations/<run_dir>/cell.data")
```

### Step 3: Parse data file
```python
info = lammps_engine.parse_data_file(
    data_file="/home/arz2/simulations/<run_dir>/cell.data"
)
# Check: n_atoms, atom_types, h_type_ids (for SHAKE), density_g_cm3
```

### Step 4: Generate and run the full equilibration workflow

Use `generate_equilibration_workflow` — it generates all stages and chains them. All paths are local.

```python
workflow = lammps_engine.generate_equilibration_workflow(
    data_file="/home/arz2/simulations/<run_dir>/cell.data",
    work_dir_base="/home/arz2/simulations/<run_dir>",
    polymer_name="<name>",
    temp=300.0,
    max_temp=600.0,
    press=1.0,
    max_press=50000.0,
    n_atoms=<n_atoms>,
    use_pcff=<True/False>,          # True for PCBN/PAMD/PKTN/PSFO/PIMD
    params_file="<path/to/emc_build.params>",  # EMC only — omit for RadonPy
)
# → workflow["stages"] lists all generated scripts with local paths
```

### Step 5: Run the chain

```python
result = lammps_engine.run_lammps_chain(
    stages=workflow["stages"],
    gpu_ids="0,1,2,3",   # ← set from nvidia-smi check
    mpi=4,
)
# Returns immediately with chain_id. Use watch_run() to block until done:
w = lammps_engine.watch_run(result["chain_id"])
Monitor(command=w["monitor_command"])   # harness re-invokes Claude when done
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

**GPU crash during NPT:** Check the log for the actual error. Do NOT switch to CPU — GPU NPT works correctly. Common causes: out-of-memory (reduce system size or use fewer GPUs), bad initial geometry (run more minimize steps), or pair style mismatch (check params file was stripped of style lines).

**Density not converging:** Add more annealing cycles. Minimum 3, up to 5.

**Chain droplets / vacuum voids visible:** Initial density too high. Rebuild cell at `density=0.05`. Add more annealing.

**Timeline wildly off from estimate:** Measure actual throughput from first log (see above). Charged systems with PPPM are slower.

**Another user is on the GPU:** Always check `nvidia-smi` first. Pin to free GPUs via `gpu_ids`.

---

## Comprehensive Equilibration Check (Required Before Stage 3)

Thermo convergence alone is necessary but not sufficient. Call `check_equilibration_comprehensive` — it runs all thermo and structural checks in one job and returns a single `overall_pass` verdict plus a ready-to-paste D-05 markdown block.

```python
result = check_equilibration_comprehensive(
    log_file="<work_dir>/06_nvt_production/06_nvt_production.log",
    dump_file="<work_dir>/06_nvt_production/06_nvt_production.dump",
    data_file="<path/to/cell.data>",
    backbone_types=[2, 3],      # REQUIRED — get from parse_data_file(); do not guess
    skip_frames=50,
    timestep_fs=1.0,
    dump_every=1000,            # auto-detected from dump header if possible
    n_backbone_bonds=119,       # DP-1; enables C∞ and MSID
)
# result["run_id"] — poll with get_run_status(run_id)
# When completed: result["overall_pass"], result["d05_markdown"]
```

**Hard gates** — block `overall_pass=True` if any fail:

| Check | Threshold | Action if failed |
|-------|-----------|-----------------|
| Density drift | < 1% (p < 0.01) | Extend final NPT by 1–2 ns |
| Energy drift | < 1% (p < 0.01) | Same |
| Density block-SEM | < 1% of mean | Same |
| Energy block-SEM | < 1% of mean | Same |
| Rg CV across chains | < 30% | Add annealing cycles; check initial cell quality |
| P2 nematic order | < 0.10 | Extend equilibration; raise annealing temperature |
| Density homogeneity CV | < 25% (adaptive grid) | Extend compression; rebuild at lower `density_initial` |

**Soft warnings** — reported in `result["warnings"]`, never block pass:
- `τ_eff > 10% of trajectory` — short sample; extend production if possible
- `C(t) not decayed` — expected below Tg; problematic in melt state
- `MSID slope ≠ 1.0` — possible chain collapse or extension
- `MSD kinetic trap` — chains immobile; expected below Tg

After the job completes, copy `result["d05_markdown"]` directly into run_log.md as the D-05 CONVERGENCE DETAIL section.

**→ When `overall_pass=True` (or all failures are justified for glassy regime), proceed to `STAGE_3_TG_MEASUREMENT.md`**
