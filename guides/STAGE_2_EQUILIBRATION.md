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
    use_pcff=True,   # or use_opls=True for PHAL/PSIL; use_trappe=True for PHYC/PDIE
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
    use_pcff=<from lammps_flags>,
    use_trappe=<from lammps_flags>,  # now populated by EMC server for PHYC/PDIE
    params_file="<work_dir>/emc_build.params",  # EMC only — omit for RadonPy
    # Optional — gen_prompt.py passes these when set in polymer_rules.json or CLI:
    npt_prod_steps=<int or None>,   # Stage 07 length; PHYC default=2.5M (5 ns at 2 fs)
    add_melt_npt=False,             # set True for FF validation runs (see below)
)
```

#### Optional: `npt_prod_steps`

Controls the length of Stage 07 (NPT production). Pass directly from `gen_prompt.py` output.
For PHYC (TraPPE-UA, PE), `polymer_rules.json` sets `npt_prod_ns: 5.0`, which `gen_prompt.py` converts
to 2,500,000 steps at `dt_prod=2.0 fs`. Other classes inherit the default (half of the Stage 05 length).

#### Optional: Melt-NPT (`add_melt_npt=True`)

For FF validation runs only (not default). When `add_melt_npt=True` and `temp < t_equil_K`, Stage 05
is split into three sub-stages to capture an isothermal NPT run at the melt temperature:

```python
workflow = generate_equilibration_workflow(
    ...
    temp=300.0,             # final production temperature (rubbery condition: temp < t_equil_K)
    add_melt_npt=True,      # inject 05a/05b/05c instead of single 05
    t_equil_K=550.0,        # melt temperature — required when add_melt_npt=True
    melt_npt_steps=500000,  # stage 05b length; defaults to int(1e6/dt_prod) ≈ 1 ns
)
```

This produces a 9-stage workflow:
- **05a** (`npt_cool_melt`): NPT cool `max_temp → t_equil_K`
- **05b** (`npt_melt`): NPT isothermal at `t_equil_K` — **extract melt density from this log**
- **05c** (`npt_cool`): NPT cool `t_equil_K → temp`
- 06, 07: unchanged (NVT production, NPT production at `temp`)

Melt density is extracted from `05b_npt_melt.log` using `extract_equilibrated_density`. This path
is returned in `workflow["melt_npt_log"]` and `workflow["melt_npt_dir"]` when the flag is set.

### Step 5: Run the chain

```python
result = run_lammps_chain(
    stages=workflow["stages"],
    gpu_ids="<from task.txt or nvidia-smi>",
    mpi=<n>,
    data_file="<work_dir>/cell.data",         # enables pre-flight check
    params_file="<work_dir>/emc_build.params", # EMC only — suppresses Coeffs false-positive
)
w = watch_run(result["chain_id"])
# Return chain_id and w["monitor_command"] to the orchestrator — do not call Monitor.
```

`generate_equilibration_workflow` produces **7 stages** (rubbery, `temp ≤ 300 K`) or **9 stages** (glassy, `temp > 300 K`, default `add_300k_production=True`).

- **Stage 6 — NVT production** (`06_nvt_production`): runs at T_equil_K (melt); source for `check_equilibration_comprehensive` and Tg sweep input
- **Stage 7 — NPT production** (`07_npt_production`): NPT at T_equil_K (melt); intermediate only — not used as downstream density/deform source for glassy polymers
- **Stage 8 — NPT cool** (`08_npt_cool300`, glassy only): NPT ramp T_equil_K → 300 K, ~1 ns
- **Stage 9 — NPT production 300 K** (`09_npt_prod300`, glassy only): NPT constant-T at 300 K, ~2 ns — **primary source for density, deformation, and property analysis**

Stages 08/09 are auto-appended by `generate_equilibration_workflow` whenever `temp > 300.0`. Pass `add_300k_production=False` only if running a rubbery polymer incorrectly at high T (rare). `npt_production_log` and `npt_production_dir` in the return dict always point to the last NPT stage (09 when present, else 07).

Downstream inputs (from stage 09 for glassy, stage 07 for rubbery):
- `property-analysis-worker` `npt_prod_log_path` → `09_npt_prod300/09_npt_prod300.log`
- `property-analysis-worker` `npt_prod_dump_path` → `09_npt_prod300/09_npt_prod300.dump`
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
