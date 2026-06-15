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
| PS | PSTR | ~373 K | 550K → 250K | Standard; **if primary Tg < exp_Tg + 50 K, use `Tg_alternative_K`** (expected MD offset +70–120 K; false F-stat split) |
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

| Protocol | T_STEP | N_STEPS_PER_T | dt_fs | Cooling rate | MD overestimation |
|----------|--------|---------------|-------|--------------|-------------------|
| Screening (1 fs) | 20 K | 500 k | 1.0 | ~40 K/ns | 80–120 K |
| Screening (2 fs, TraPPE-UA) | 20 K | 250 k | 2.0 | ~40 K/ns | 80–120 K |
| Production (1 fs) | 20 K | 4 M | 1.0 | ~5 K/ns | ~50–80 K |

The per-class offsets in `polymer_rules.json` assume screening-rate runs. Slower runs reduce the gap but don't eliminate it.
TraPPE-UA classes (PHYC, PDIE) use dt_fs=2.0 (no SHAKE — UA eliminates C-H fast modes; LAMMPS SHAKE cannot constrain a continuous backbone) — halving N_STEPS_PER_T maintains the same cooling rate.

---

## Workflow

### Step 1: Generate Tg sweep script

`generate_script` is synchronous — returns the script path immediately.

For TraPPE-UA systems (use_trappe=True), detect the number of bond types before generating the script:
```bash
n_bond_types=$(grep -m1 "bond types" <equil_data_path> | awk '{print $1}')
# shake_bond_type_ids = list(range(1, n_bond_types + 1)), e.g. [1] for PE, [1, 2] for PBD
```

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
        "TIMESTEP":      <dt_fs from prompt>,   # 2.0 for TraPPE-UA, 1.0 otherwise
        "use_pppm":      <True unless TraPPE-UA>,  # from lammps_flags
        "use_gpu":       True,
        "use_pcff":      <from lammps_flags>,
        "use_trappe":    <from lammps_flags>,
        "use_shake":     <False for TraPPE-UA (UA removes C-H modes; continuous backbone incompatible with SHAKE); False for PCFF; True for GAFF2>,
        "shake_bond_type_ids": <omit for TraPPE-UA and PCFF; only relevant for GAFF2>,
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

**Log file has fewer blocks than expected / extract_tg returns unphysical Tg:** The chain script (pre-2026-06-09) used `>` instead of `>>` for the log redirect, so each stage overwrote the previous. Only the last stage's thermo data survives in `tg_sweep.log`. Recovery: all 21 `tg_X_out.data` final-snapshot files are preserved — extract (T, ρ) by reading box dimensions from each, compute density, and do a bilinear fit manually. Script: `/home/arz2/PolyJarvis/data/PS4/tg_density_from_data.py` (see PS4 run for reference). This bug is fixed in server.py as of 2026-06-09.

**Tg wildly off (>80K from expected):** Wrong force field, insufficient time per T, or temperature range missed the transition entirely.

**Tg sweep killed mid-run:**
- *User action (intentional kill):* Stop immediately; do not re-queue or continue — wait for user instruction.
- *System failure (GPU/LAMMPS error):* Attempt to restart from the last completed temperature (max 2 recovery attempts). If still failing, return the error to the user.
- *Partial completion (OOM kill / GPU preemption, no error in log):* Attempt `extract_tg` on available data if (a) ≥ 60% of planned temperature points completed AND (b) both the glassy and rubbery slopes are present in the log. If `extract_tg` returns ≥ 4 valid bins and `fit_quality` ≥ ACCEPTABLE, accept the result and proceed. Restart the full sweep only if < 60% complete or `extract_tg` returns < 4 bins. Observed: PDMS1 (18/31 temps, R²=0.9975 ✓).

**Intermediate / non-protocol NPT runs:** Do not submit these automatically. Only run if the user explicitly requests it; they do not have Monitor integration by design.

---

## Multi-Rate Tg Protocol (Screening-Robust — All Classes)

Every class in `polymer_rules.json` has `tg_rates_K_per_ns: [40, 160, 640]` (3 rates, 1.2 decades).
PHYC also has `tg_rates_validation_K_per_ns: [10, 40, 160, 640]` (4 rates, 1.8 decades) for Ramos comparison.

### Rate tiers

| Tier | Rates (K/ns) | GPUs | Max wall time | Use |
|------|-------------|------|---------------|-----|
| **Screening-robust** | [40, 160, 640] | 3 | <9h all classes (dominated by 40 K/ns run) | Standard multi-rate — rank-ordering + log-linear slope |
| **Validation** | [10, 40, 160, 640] | 4 | ~14h PHYC (2 fs); >24h PCFF 1 fs classes | PHYC/Ramos 2015 comparison only — do not use for PCFF classes |
| **Single-rate** | 40 | 1 | <9h | Fastest screening; apply per-class static offset |

### Orchestrator Pattern (3-rate screening-robust)

```python
# Spawn 3 tg-sweep-workers in parallel — one per rate index
for i, gpu in zip(range(3), ["0", "1", "2"]):
    Agent(subagent_type="tg-sweep-worker",
          prompt=gen_prompt("--stage tg --tg_rate_index {i} --gpu_ids {gpu} ..."))

# After all 3 Monitor() calls complete:
# Collect Tg_MD from each extract_tg result → [Tg_40, Tg_160, Tg_640]
result = extract_tg_multirate(
    rates_K_per_ns=[40, 160, 640],
    tg_values_K=[Tg_40, Tg_160, Tg_640],
    output_dir=f"data/{run_name}/raw/",
    polymer_name=run_name,
)
```

For PHYC validation: use `tg_rates_validation_K_per_ns=[10, 40, 160, 640]` (4 workers, 4 GPUs).

### What to report in D-06

| Field | Value |
|-------|-------|
| Tg_MD at 40 K/ns | [X] K (standard comparison point) |
| Log-linear slope | [X] K/ln(K/ns) (primary metric) |
| Tg at 5 K/ns (slow ref) | [X] K |
| VF Tg⁰ (if reliable) | [X] ± [Y] K (EXCELLENT/ACCEPTABLE/POOR) |

**Note:** With 3 rates spanning 1.2 decades (40–640 K/ns), VF extrapolation is poorly constrained
(CI typically > 100 K). The log-linear slope and Tg@5K/ns are the actionable outputs.
VF Tg⁰ is only well-constrained with ≥3 decades; the PHYC 4-rate set (1.8 decades) also yields
poorly constrained VF — log-linear remains the primary metric in all cases.

---

## Structural Relaxation Diagnostics

`extract_tg` produces two tiers of relaxation diagnostics alongside the density-kink Tg.

### Tier 1 — Log-based (always present)

Per-plateau effective independent sample count, computed via integrated density autocorrelation time:

```
tau_int = 0.5 + Σ_k ρ̃(k)   [truncated at first non-positive lag — Sokal window]
n_eff   = N_plateau / (2 × tau_int)
```

Output: `relaxation_metrics` array in result JSON — one entry per plateau:
```json
{"temperature": 480, "n_eff": 12.3, "tau_int_steps": 40.6, "relax_warning": false}
```

`relax_warning: true` when `n_eff < 5` (soft flag — the density mean is statistically unreliable for that plateau). Count of flagged plateaus in `n_plateaus_low_n_eff`.

**Interpretation:** Above Tg, `n_eff < 5` on multiple rubbery plateaus indicates the step count is too short for the density to properly average — consider increasing `tg_steps_per_t`. Below Tg, slow ACF decay is expected (the glass is non-ergodic) and does not indicate a problem.

### Tier 2 — Dump-based structural (requires `per_t_dump_file` + `tg_data_file`)

Enable in the Tg sweep by setting `WRITE_PER_T_DUMP=True` and `PER_T_DUMP_FILE=per_t_structs.dump` in `generate_script` params. This writes one final-frame snapshot after each temperature step (~25 frames, ~100–300 MB total). **Rule B is not violated** — this is one frame per T step, not a continuous trajectory.

The dump file path is `<work_dir>/tg_sweep/per_t_structs.dump`.

Pass to `extract_tg`:
```python
extract_tg(
    log_file       = "<tg_sweep_dir>/tg_sweep.log",
    per_t_dump_file = "<tg_sweep_dir>/per_t_structs.dump",
    tg_data_file   = "<equil_data_path>",   # .data file input to the Tg sweep
    backbone_types = ["2", "3"],            # backbone atom type IDs
    ...
)
```

**Per-T metrics computed:**

| Metric | Flag condition | Applies to |
|--------|---------------|------------|
| `mean_rg_A` | — | All T |
| `rg_cv` | > 0.30 → `rg_cv_flag` | T > Tg only |
| `p2` (nematic order) | > 0.10 → `p2_flag` | T > Tg only |
| `structural_regime` | `"rubbery"` / `"glassy"` | Classified by density-kink Tg |

Flags **only fire above the density-kink Tg**. Below Tg, chains are frozen (non-ergodic glass) — structural arrest is the expected, correct signal and is never flagged.

**Dynamic Tg — Rg-kink method:**

A bilinear fit to the Rg(T) curve yields `Tg_dynamic_K` (the temperature where the Rg contraction rate changes slope). This is an independent structural Tg estimator:

- Agreement within ~20–30 K with density-kink `Tg_K`: normal (thermal history and fit window effects)
- Disagreement > 50 K: investigate. Either the bilinear density fit caught a noise feature (check R² and slope ordering), or the rubbery branch density data was poorly equilibrated (check `n_eff` of rubbery plateaus)

**Why not inline adaptive step counts?**

The Tg sweep is a continuous constant-rate quench with momenta inherited across all temperature steps (Rule A). Extending the run at any temperature step before proceeding to the next would change the effective cooling rate through the transition window — the kinetic Tg shifts, silently, with no change in bilinear R². The cooling rate must be constant throughout the transition window for the multi-rate protocol and rate-extrapolation to be valid. Structural diagnostics are always post-hoc.
