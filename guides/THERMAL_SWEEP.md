# Tg Sweep Guide
**Read when:** You have a converged equilibrated cell and need to run a Tg sweep  
**Worker:** tg-sweep-worker — generate sweep script, submit run, return RESULT block to orchestrator

---

## Rules

### Rule A: No Velocity Re-initialization Between Temperature Steps

Only initialize velocities once at the very first temperature step. Every subsequent step inherits momenta from the previous one.

### Rule B: No Dump Files During Tg Sweep

Set `"DUMP_FILE": ""` in the `generate_script` params — no full trajectory during the sweep (large I/O).

**Opt-in per-T structural snapshot:** keep `DUMP_FILE=""`, but if per-T Rg/P2/nematic order is wanted,
additionally pass `"WRITE_PER_T_DUMP": True` (optionally `"PER_T_DUMP_FILE": "per_t_structs.dump"`).
This writes ONE single-frame snapshot per temperature step (a `dump … 1 … ; run 0 ; undump` block),
not a trajectory, so the I/O cost is negligible while still enabling per-T structural analysis. Default
off; only enable when the run explicitly requests per-T structural metrics. (Previously these metrics
silently failed because the flag was never set — PVC2 2026-06-23.)

### Rule C: Simulation Time Per T is System-Dependent

**Absolute floor: 500 ps.** For most common polymers (PE, PS, PMMA, PEO): 1–4 ns per temperature.

TraPPE-UA classes (PHYC, PDIE) use `dt_fs=2.0` (no SHAKE — UA eliminates C-H fast modes). Halve `N_STEPS_PER_T` relative to PCFF to maintain the same cooling rate.

---

## Temperature Range Selection

The sweep must bracket the transition — too narrow and the bilinear fit fails to capture both slopes.

Rule of thumb: start ~1.5× Tg, end ~0.75× Tg, span ≥300 K, step 10–20 K.

---

## Starting Cell

The `equil_data_path` in the prompt differs by polymer regime — never substitute one for the other:

- **Rubbery** (Tg_exp < 300 K, T_workflow_K = 300): use `npt_tg_prep_data` from the equil RESULT — the `npt_melt` output at `T_equil_K` (e.g., 400 K for PDIE). The 300 K production cell is only ~Tg_exp + 20 K; the chains are poorly relaxed at that temperature and bias the rubbery density slope in the sweep.
- **Glassy** (Tg_exp > 300 K): use `npt_prod300_out.data` (300 K cell, well-quenched from T_equil_K). This is below Tg so the sweep re-melts it cleanly before detecting the transition.

The orchestrator passes the correct path as `equil_data_path` via `--tg_start_data` (rubbery) or `--data_path` (glassy).

---

## Workflow

### Step 1: Generate Tg sweep script

`generate_script` is synchronous — returns the script path immediately.

Choose a `progress_file` path before calling `generate_script`; pass it as `PROGRESS_FILE`
in params so the generated script writes a JSON event after each temperature step completes.

For TraPPE-UA systems (`use_trappe=True`), detect the number of bond types before generating the script:
```bash
n_bond_types=$(grep -m1 "bond types" <equil_data_path> | awk '{print $1}')
# shake_bond_type_ids = list(range(1, n_bond_types + 1)), e.g. [1] for PE, [1, 2] for PBD
```

**Use `tg_sweep_dir` from the prompt** — for a multi-rate sweep it is the per-rate dir
(`.../thermal/tg_sweep_r40`), and analyze-tg reads `tg_sweep_dir/tg_sweep.log`. Do NOT
hardcode `.../thermal/tg_sweep/`; that collides across rates and mismatches the analysis path.

```python
progress_file = f"{tg_sweep_dir}/tg_progress.jsonl"   # tg_sweep_dir from prompt (rate-suffixed)

result = generate_script(
    template_name="npt_tg_step",
    output_script=f"{tg_sweep_dir}/tg_sweep.in",
    data_file=equil_data_path,
    velocity_seed=<velocity_seed from prompt, or None for random>,   # pin for recovery/replication
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
        "TIMESTEP":            <dt_fs from prompt>,  # 2.0 for TraPPE-UA, 1.0 otherwise
        "use_pppm":            <True unless TraPPE-UA>,
        "use_gpu":             True,
        "engine":              <engine from prompt>,  # kokkos for PCFF/OPLS → deck omits `package gpu`
        "use_pcff":            <copy lammps_flags["use_pcff"] verbatim>,
        "use_opls":            <copy lammps_flags["use_opls"] verbatim>,
        "use_trappe":          <copy lammps_flags["use_trappe"] verbatim>,
        # ↑ ALWAYS pass all three FF booleans, copied literally from the lammps_flags
        # dict in your prompt. Do NOT omit them: on an equilibrated .data the engine
        # cannot always re-derive the FF and will silently emit a GAFF2 deck (wrong
        # pair_style/dihedral_style → corrupt Tg). Passing the wrong flag now hard-fails
        # with "FF flag mismatch" rather than running a bad deck — also do not guess.
        "use_shake":           False,    # False for TraPPE-UA and PCFF; True for GAFF2
        "shake_bond_type_ids": <omit for TraPPE-UA and PCFF; only relevant for GAFF2>,
        "params_file":         "<work_dir>/emc_build.params",  # EMC only; omit for RadonPy
        "PROGRESS_FILE":       progress_file,   # enables per-T PROGRESS lines in Monitor
    }
)
# result["n_tg_stages"] is the number of temperature steps (used by run_lammps_script)
```

**Verify the FF before submitting.** After `generate_script`, `grep` the generated `.in`
for `pair_style` and confirm it matches the planned force field — abort and re-check the
FF flags if it shows a GAFF2 deck:
```bash
grep -E 'pair_style|dihedral_style|kspace' "<tg_sweep_dir>/tg_sweep.in"
# TraPPE-UA → "pair_style lj/cut ..." + "dihedral_style multi/harmonic", NO kspace/pppm
# PCFF      → "pair_style lj/class2/coul/long ..." + "kspace_style pppm ..."
# GAFF2 leak (pair_style lj/charmm... / dihedral_style fourier) = wrong → do NOT submit
```

**GPU neighbor list optimization (small PCFF cells <5k atoms):** After `generate_script`, edit `package gpu 1 neigh no` → `package gpu 1 neigh yes` in the generated `.in` file for +30% speedup (NPT-stable; do not apply to kokkos engine — kokkos manages its own neighbor list).

### Step 2: Submit sweep

`run_lammps_script` is async — returns `run_id` immediately.

Pass `progress_file` and `n_stages` so `watch_run` can expose them to the Monitor command,
which will emit `PROGRESS [##---] 3/36 done: T560` as each temperature step completes.

```python
run = run_lammps_script(
    script=result["output_script"],
    work_dir=tg_sweep_dir,            # from prompt (rate-suffixed for multi-rate)
    log_file="tg_sweep_run.log",
    gpu_ids="<from orchestrator>",
    mpi=<n>,
    engine=<engine from prompt>,   # MUST match the generate_script engine above
    progress_file=progress_file,
    n_stages=result["n_tg_stages"],
)
w = watch_run(run["run_id"])
# Return run_id and w["monitor_command"] to the orchestrator — do not call Monitor.
```

---

### Rule D: Never Set use_gpu=False

`use_gpu: True` is mandatory for all Tg sweep runs — the generated script includes GPU package
directives (kspace/pair acceleration). Setting `use_gpu=False` strips these flags while the
script retains GPU syntax, causing a crash at runtime.

On recovery or re-submit, preserve `use_gpu: True` exactly as in the original `generate_script`
call. Do not change it to recover from a crash — the crash is never caused by GPU use itself.
The only template that legitimately uses `use_gpu=False` is `nvt_born`, which is no longer part
of the standard pipeline.

---

## Common Failures

**Tg sweep killed mid-run (system failure):** Attempt to restart from the last completed temperature (max 2 recovery attempts). If still failing, return the error to the orchestrator.
