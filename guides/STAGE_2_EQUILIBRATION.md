# Stage 2: Equilibration
**Read when:** You have a `.data` file and need to equilibrate it

---

## Rules

### Rule A: All Scripts Through lammps-engine — No Exceptions

```python
# ❌ WRONG — hand-written .in file
with open("npt.in", "w") as f:
    f.write("fix 1 all npt ...")

# ✅ CORRECT — always use generate_equilibration_workflow
workflow = generate_equilibration_workflow(
    data_file="<work_dir>/cell.data",
    work_dir_base="<work_dir>",
    use_pcff=True,   # or use_opls=True / use_trappe=True for PHYC/PDIE/PSTR
    params_file="<work_dir>/emc_build.params",  # EMC only
)
```

### Rule B: GPU — Check task.txt First, then nvidia-smi

Check `task.txt` for a `gpu_ids` field first. If specified, use it directly. Only check `nvidia-smi` to assign free GPUs when `task.txt` doesn't specify.

```bash
nvidia-smi --query-gpu=index,memory.used,utilization.gpu --format=csv,noheader
```

If a GPU is occupied, pass only the free IDs via `gpu_ids` (e.g., `gpu_ids="1,2,3"` if GPU 0 is taken). `gpu_ids` and `mpi` must always be set explicitly — the default pins to GPU 0 regardless of what is free.

### Rule C: Never Skip Annealing Cycles

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

### Step 2: Copy .data file to work_dir

Copy the `.data` file from `data_path` (Stage 1 output) to `{work_dir}/cell.data`. All output for this run must stay within `work_dir`.

### Step 3: Inspect data file

```python
info = inspect_data_file(data_file="<work_dir>/cell.data")
# info.info: n_atoms, backbone_types (required for check_equilibration_comprehensive)
# info.validation.errors: must be empty before proceeding
```

### Step 4: Generate the equilibration workflow

```python
workflow = generate_equilibration_workflow(
    data_file="<work_dir>/cell.data",
    work_dir_base="<work_dir>",          # all stage outputs written here
    polymer_name="<name>",
    temp=300.0 if exp_Tg_K < 300 else T_equil_K,
    # rubbery (exp_Tg_K<300): 300 K direct — stage 07 NPT feeds density + fluctuation K directly
    # glassy  (exp_Tg_K≥300): T_equil_K melt — Phase 2 cool→300 K mandatory after chain
    max_temp=T_anneal_high_K,  # annealing ceiling; always from polymer_rules.json
    press=1.0,
    max_press=50000.0,
    n_atoms=<from inspect_data_file>,
    use_pcff=<True/False>,
    params_file="<work_dir>/emc_build.params",  # EMC only — omit for RadonPy
)
```

### Step 5: Run the chain

```python
result = run_lammps_chain(
    stages=workflow["stages"],
    gpu_ids="<from task.txt or nvidia-smi>",
    mpi=<n>,
)
w = watch_run(result["chain_id"])
# Return chain_id and w["monitor_command"] to the orchestrator — do not call Monitor.
```

`generate_equilibration_workflow` produces **7 stages** (01_minimize → 07_npt_production). The last two are:
- **Stage 6 — NVT production** (`06_nvt_production`): runs at T_equil_K (melt); source of `equil_data_path` → Tg sweep and convergence check
- **Stage 7 — NPT production** (`07_npt_production`): NPT at T_equil_K (melt); feeds nothing downstream directly — Phase 2 takes over

**Phase 2 — Cool and Measure at 300 K (launch in parallel with Tg sweep):**
Use `generate_script` for two stages starting from `07_npt_production_out.data`:
1. NPT cool: T_equil_K → 300 K, ~1 ns → `08_npt_cool300/`
2. NPT production: 300 K / 1 atm, ~2 ns → `09_npt_prod300/`

Downstream inputs from Phase 2 (not stage 07):
- `analysis-worker` `npt_prod_log_path` → `09_npt_prod300/09_npt_prod300.log`
- `analysis-worker` `npt_prod_dump_path` → `09_npt_prod300/09_npt_prod300.dump`
- `deform-worker` `equil_data_path` → `09_npt_prod300/09_npt_prod300_out.data`

---

## GPU Selection Reference

| System Size | Recommended MPI | Notes |
|---|---|---|
| <10k atoms | 1 | 2 GPUs sufficient |
| 10-20k atoms | 2-4 | 2 GPUs standard, 4 for faster throughput |
| 20-40k atoms | 4 | Use all available free GPUs |

Pass only the IDs of GPUs confirmed free by nvidia-smi (or specified in task.txt).

---

## Comprehensive Equilibration Check (Required Before Stage 3)

Call `check_equilibration_comprehensive` — returns `overall_pass` verdict and a ready-to-paste D-05 markdown block.

```python
result = check_equilibration_comprehensive(
    log_file="<work_dir>/06_nvt_production/06_nvt_production.log",
    dump_file="<work_dir>/06_nvt_production/06_nvt_production.dump",
    data_file="<work_dir>/cell.data",
    backbone_types=[...],    # REQUIRED — from inspect_data_file(); do not guess
    skip_frames=50,
    timestep_fs=1.0,
    dump_every=1000,
    n_backbone_bonds=<DP-1>,
)
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

Copy `result["d05_markdown"]` directly into run_log.md as the D-05 CONVERGENCE DETAIL section.

---

## Common Failures

**GPU crash during NPT:** Check the log for the actual error. Do NOT switch to CPU — GPU NPT works correctly. Common causes: out-of-memory (reduce system size or use fewer GPUs), bad initial geometry (run more minimize steps), or pair style mismatch (check params file was stripped of style lines).

**Density not converging:** Add more annealing cycles. Minimum 3, up to 5.

**Chain droplets / vacuum voids visible:** Initial density too high. Rebuild cell at `density=0.05`. Add more annealing.

**Another user is on the GPU:** Always check `nvidia-smi` first. Pin to free GPUs via `gpu_ids`.

**TraPPE-UA `validate_data_file` returns `valid: false` (4 "missing Coeffs" errors):** EMC `.data` files for PHYC/PDIE/PSTR contain topology only — no Pair/Bond/Angle/Dihedral Coeffs sections. This is by design; coefficients are in `emc_build.params`. Confirm `emc_build.params` contains the expected Coeffs (type counts must match the data file header), then proceed. This is a false-positive, not a real blocker.

**TraPPE-UA `generate_equilibration_workflow` produces wrong force-field styles:** `lammps_flags` from Stage 1 carries only `use_pcff` and `use_opls` — there is no `use_trappe` key. Infer from `polymer_class`: if class is PHYC, PDIE, or PSTR, set `use_trappe=True`. Without it the generator defaults to GAFF2-style `lj/charmm/coul/long` + PPPM, which runs but applies wrong physics to a united-atom system.
