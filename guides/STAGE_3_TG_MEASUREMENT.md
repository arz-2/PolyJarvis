# Stage 3: Tg Measurement
**Read when:** You have a converged equilibrated cell and need to run a Tg sweep  
**Worker:** tg-sweep-worker — generate sweep script, submit run, return RESULT block to orchestrator

---

## Rules

### Rule A: No Velocity Re-initialization Between Temperature Steps

Only initialize velocities once at the very first temperature step. Every subsequent step inherits momenta from the previous one.

```lammps
# ❌ WRONG — re-initializing at each T discards chain relaxation state
velocity all create ${T} 12345 mom yes rot yes dist gaussian
fix 1 all nvt temp ${T} ${T} ${T_DAMP}
run ${N_STEPS_PER_T}

# ✅ CORRECT — inherit momenta (npt_tg_step template handles this correctly)
fix 1 all nvt temp ${T} ${T} ${T_DAMP}
run ${N_STEPS_PER_T}
```

### Rule B: No Dump Files During Tg Sweep

Set `"DUMP_FILE": ""` in the `generate_script` params. Dump files across a 35-point sweep generate tens of GB of useless data and slow the run.

### Rule C: Simulation Time Per T is System-Dependent

**Absolute floor: 500 ps.** For most common polymers (PE, PS, PMMA, PEO): 1–4 ns per temperature.

| Study | Time/T | System |
|---|---|---|
| Webb et al. (2024) | 4 ns burn-in + 2 ns production | General polymers |
| Afzal et al. (2021) | 4–7 ns | High-throughput library |
| Klajmon et al. (2024) | Continuous cooling 1–10 K/ns | Various |

---

## Temperature Range Selection

The sweep must bracket the transition — too narrow and the bilinear fit fails to capture both slopes.

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

Rule of thumb: start ~1.5× Tg, end ~0.75× Tg, span ≥300 K, step 10–20 K.

---

## Cooling Rate & Expected Tg Offset

```
cooling_rate (K/ns) = T_STEP / (N_STEPS_PER_T × TIMESTEP_fs × 1e-6)
```

| Protocol | T_STEP | N_STEPS_PER_T | Cooling rate | MD overestimation |
|----------|--------|---------------|--------------|-------------------|
| Screening | 20 K | 500 k (500 ps) | ~40 K/ns | 80–120 K |
| Production | 20 K | 4 M (4 ns) | ~5 K/ns | ~50–80 K |

The per-class offsets in `polymer_rules.json` assume screening-rate runs. Slower runs reduce the gap but don't eliminate it.

---

## Workflow

### Step 1: Generate Tg sweep script

`generate_script` is synchronous — returns the script path immediately.

```python
result = generate_script(
    template_name="npt_tg_step",
    output_script="<work_dir>/tg_sweep/tg_sweep.in",
    data_file=equil_data_path,
    params={
        "LOG_FILE":      "tg_sweep.log",
        "DUMP_FILE":     "",            # Rule B — no dump
        "T_START":       <T_start>,
        "T_END":         <T_end>,
        "T_STEP":        <T_step>,
        "N_STEPS_PER_T": <n_steps_per_t>,
        "P_START":       1.0,
        "P_FINAL":       1.0,
        "T_DAMP":        100.0,
        "TIMESTEP":      1.0,
        "use_pppm":      <True unless TraPPE-UA>,  # from lammps_flags
        "use_gpu":       True,
        "use_pcff":      <from lammps_flags>,
        "use_trappe":    <True for PHYC/PDIE/PSTR>,  # infer from polymer_class; lammps_flags has no use_trappe key
        "use_shake":     <False for PCFF/TraPPE-UA; True for GAFF2>,
        "params_file":   "<work_dir>/emc_build.params",  # EMC only; omit for RadonPy
        "write_restart": False,
    }
)
```

### Step 2: Submit sweep

`run_lammps_script` is async — returns `run_id` immediately.

```python
run = run_lammps_script(
    script=result["output_script"],
    work_dir="<work_dir>/tg_sweep",
    log_file="tg_sweep_run.log",
    gpu_ids="<from orchestrator>",
    mpi=<n>,
)
w = watch_run(run["run_id"])
# Return run_id and w["monitor_command"] to the orchestrator — do not call Monitor.
```

---

## Common Failures

**Poor bilinear fit R² (< 0.90):** Temperature range too narrow, insufficient time per T, or velocity re-initialized at each step (Rule A violated).

**Sharp discontinuities between T windows:** Velocity re-initialization (Rule A) or cell not equilibrated before sweep — check Stage 2 convergence.

**Log file has fewer blocks than expected:** Simulation crashed mid-sweep. Check stdout log for LAMMPS error; resume from last restart file if available.

**Tg wildly off (>80K from expected):** Wrong force field, insufficient time per T, or temperature range missed the transition entirely.
