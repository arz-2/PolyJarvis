# Stage 3: Tg Measurement
**Read when:** You have a converged equilibrated cell and need to run a Tg sweep
**Previous stage:** `STAGE_2_EQUILIBRATION.md`
**Next stage:** `STAGE_4_ANALYSIS.md` — once the sweep log is complete
**Revision parameters:** `REVISION_PARAMS.md` — T_START, T_END, T_STEP, steps/T for all 8 revision polymers

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

### Rule E: Tg Sweep via MCP Tool — No Hand-Written Scripts, No Direct Python Imports

Always use `generate_script` via the lammps-engine MCP tool with the `npt_tg_step` template. Do not import `ScriptGenerator` directly — the MCP tool is the only supported path for agent runs. Pass `use_pcff` and `params_file` from the EMC job output for PCFF systems.

---

## Temperature Range Selection

The sweep must bracket the transition. Too narrow = bilinear fit fails to capture both glassy and rubbery slopes.

| Polymer | Class | Exp Tg | Suggested Range | Notes |
|---|---|---|---|---|
| PE | PHYC | ~195 K | 450K → 100K | Wide range needed |
| PS | PSTR | ~373 K | 550K → 250K | Standard |
| PMMA | PACR | ~378 K | 550K → 250K | Standard |
| PEO/PEG | POXI | ~206 K | 450K → 100K | Similar to PE |
| BPA-PC | PCBN | ~422 K | 700K → 200K | PCFF; MD Tg ~500–540K |
| Nylon-6 | PAMD | ~323 K | 650K → 150K | PCFF; MD Tg ~400–440K |
| PEEK | PKTN | ~418 K | 800K → 300K | PCFF; MD Tg ~500–540K; start >Tm=616K |
| PSU (Udel) | PSFO | ~463 K | 800K → 300K | PCFF; MD Tg ~540–580K |
| Kapton | PIMD | ~633 K | 900K → 350K | PCFF; MD Tg ~730–810K; must sweep very high |

**Rule of thumb:**
- Start: ~1.5× expected Tg (or 600K, whichever is lower)
- End: ~0.75× expected Tg
- Total span: at least 300–350 K
- Step size: 10–20 K (smaller = better fit, more compute)

---

## Cooling Rate & Expected Tg Offset

```
cooling_rate (K/ns) = T_STEP / (N_STEPS_PER_T × TIMESTEP_fs × 1e-6)
```

| Protocol | T_STEP | N_STEPS_PER_T | Cooling rate | Expected MD overestimation |
|----------|--------|---------------|--------------|---------------------------|
| Screening | 20 K | 500 k (500 ps) | ~40 K/ns | 80–120 K |
| Production (Webb 2024) | 20 K | 4 M (4 ns) | ~5 K/ns | ~50–80 K |

MD always overestimates experimental Tg due to fast cooling. The per-class offsets in `polymer_rules.json` assume screening-rate runs (~40 K/ns). Slower runs reduce the gap but do not eliminate it — WLF correction (if needed) is deferred to Track G4.

---

## Workflow

### Step 1: Look up N_STEPS_PER_T for your polymer

Search literature (arXiv, ACS, etc.) for MD Tg studies on your specific polymer before proceeding. Record what you find in your simulation log.

### Step 2: Check GPU availability

```bash
nvidia-smi --query-gpu=index,memory.used,utilization.gpu --format=csv,noheader
```

### Step 3: Generate Tg sweep script

`generate_script` is a **synchronous** lammps-engine MCP tool — it returns immediately with the script path.

```python
# lammps_flags = {"use_pcff": True, "use_opls": False}  ← from get_emc_job_output for EMC builds
#                {"use_pcff": False, "use_opls": True}   ← GAFF2/OPLS-AA (RadonPy path)

equil_data = "/home/arz2/simulations/<run_dir>/06_nvt_production/06_nvt_production_out.data"
params_file = "/home/arz2/polyjarvis_emc_jobs/<job_id>/emc_build.params"  # EMC builds only; omit for RadonPy

result = generate_script(
    template="npt_tg_step",
    output_path="/home/arz2/simulations/<run_dir>/tg_sweep/tg_sweep.in",
    data_file=equil_data,
    params={
        "LOG_FILE":       "tg_sweep.log",
        "DUMP_FILE":      "",              # No dump — thermo only (Rule D)
        "T_START":        600,             # K — see temperature range table above
        "T_END":          200,             # K
        "T_STEP":         20,              # K (10 for production; 20 for screening)
        "N_STEPS_PER_T":  500000,          # 500 ps screening; 2000000 for production
        "P_START":        1.0,
        "P_FINAL":        1.0,
        "T_DAMP":         100.0,
        "TIMESTEP":       1.0,
        "use_pppm":       True,            # from lammps_flags; False for TraPPE-UA (lj/cut)
        "use_gpu":        True,
        "use_pcff":       True,            # from lammps_flags; False for OPLS-AA/TraPPE
        "use_shake":      False,           # False for PCFF/TraPPE-UA; True for GAFF2
        "params_file":    params_file,     # EMC only; omit key for RadonPy builds
        "write_restart":  False,
    },
)
script_path = result["script_path"]
```

### Step 4: Submit sweep

`run_lammps_script` is an **async** lammps-engine MCP tool — returns a `run_id` immediately.

```python
run = run_lammps_script(
    script_path=script_path,
    gpu_ids=[0, 1, 2, 3],   # all GPUs; adjust if other jobs are running (Rule A)
    mpi=4,
    run_name="tg_sweep_<run_dir>",
)
run_id = run["run_id"]
```

### Step 5: Monitor until completion

Follow the same auto-continuation pattern as Stage 2 (per CLAUDE.md):

```python
w = watch_run(run_id=run_id)
Monitor(command=w["monitor_command"])
# Claude is re-invoked automatically when the run completes or errors
```

### Step 6: Verify log integrity before proceeding to Stage 4

```bash
# Count should equal (T_START - T_END) / T_STEP + 1
grep -c "Loop time" /home/arz2/simulations/<run_dir>/tg_sweep/tg_sweep.log
```

---

## Timeline Estimation

Always use measured throughput from your equilibration logs — do not guess.

```
Total steps = (T_START - T_END) / T_STEP × N_STEPS_PER_T
Runtime (hrs) = Total steps / measured_steps_per_sec / 3600
```

**Example:** 20 temperatures × 500,000 steps/T = 10M steps
- PCFF GPU (~600 steps/s): 10M / 600 / 3600 ≈ **4.6 hrs** (screening)
- PCFF GPU × 2M steps/T: ~18 hrs (production)

Measure actual throughput from stage 02 log before estimating — don't guess.

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
