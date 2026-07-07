# Equilibration Guide
**Read when:** You have a `.data` file and need to submit the equilibration chain.
**Worker:** equilibration-worker — return RESULT block to orchestrator when done.

---

## Rules

### Rule A: All Scripts Through lammps-engine — No Exceptions

### Rule B: GPU — Check task.txt First, then nvidia-smi

Check `task.txt` for a `gpu_ids` field first. Only check `nvidia-smi` when `task.txt` doesn't specify. Always pass `gpu_ids` and `mpi` explicitly — the default pins to GPU 0 regardless of what is free.

### Rule C: Never Skip Annealing Cycles

---

## Workflow

### Step 1: Copy and inspect the .data file

Copy the `.data` file from `data_path` to `{work_dir}/cell.data`, then:

```python
info = inspect_data_file(data_file="{work_dir}/cell.data")
# info.validation.errors must be empty before proceeding
# save info.n_atoms for generate_equilibration_workflow
```

### Step 2: Generate the equilibration workflow

```python
workflow = generate_equilibration_workflow(
    data_file="{work_dir}/cell.data",
    work_dir_base="{work_dir}",
    polymer_name=polymer_name,
    temp=T_workflow_K,
    max_temp=T_anneal_high_K,
    press=1.0,
    max_press=50000.0,
    n_atoms=n_atoms,
    use_pcff=lammps_flags["use_pcff"],
    use_trappe=lammps_flags["use_trappe"],
    params_file="{work_dir}/emc_build.params",  # EMC only — omit for RadonPy
    npt_prod_steps=npt_prod_steps,               # from prompt
    engine=engine,                               # from prompt — selects deck (kokkos: no `package gpu` line)
    velocity_seed=velocity_seed,                 # from prompt — pin `velocity all create` RNG (null = random)
    add_melt_npt=add_melt_npt,                   # True for rubbery (auto-set when T_workflow_K ≤ 300)
    t_equil_K=T_equil_K,                         # required when add_melt_npt=True
)
```

`temp` determines which chain is generated:
- `temp ≤ 300.0` (rubbery): 7-run chain ending at `npt_production`
- `temp > 300.0` (glassy): 9-run chain — `npt_cool300` + `npt_prod300` auto-appended

Use the return dict keys (`npt_production_dir`, `npt_prod300_data`, etc.) as downstream paths — do not construct paths manually.

When `add_melt_npt=True` (rubbery, T_workflow_K ≤ 300), the return dict also contains:
- `npt_tg_prep_data`: path to `npt_melt_out.data` (isothermal NPT at `T_equil_K`) — this is the Tg sweep starting cell. Do NOT use `npt_production_out.data` as the starting cell for Tg sweeps on rubbery polymers; that cell is too close to Tg and biases the rubbery density slope.

Include `npt_tg_prep_data` in your RESULT block so the orchestrator can thread it to the thermal track.

### Step 3: Submit chain and watch

```python
result = run_lammps_chain(
    stages=workflow["stages"],
    gpu_ids=gpu_ids,
    mpi=mpi,
    data_file="{work_dir}/cell.data",
    params_file="{work_dir}/emc_build.params",  # EMC only
    engine=engine,                              # from prompt — MUST match the workflow's engine
)
w = watch_run(result["chain_id"])
# Return chain_id and w["monitor_command"] to orchestrator — do not call Monitor.
```

---

## Common Failures

**GPU crash during NPT:** Check the log for the error. Do NOT switch to CPU. Common causes: out-of-memory (reduce system size or GPUs), bad initial geometry (more minimize steps), pair style mismatch (check params file).

**Density not converging:** Add more annealing cycles (minimum 3, up to 5).

**RE-ANNEAL — glassy cell converged but density too low (under-annealed cooling):** When the equil-checker returns `RE-ANNEAL` (i.e. `assess_cooling_contraction` verdict `UNDER_ANNEALED_COOLING`: the melt density is right but the cell gained too little density on cooling — free volume frozen in). Do **NOT** `EXTEND` at 300 K (a vitrified glass cannot densify below Tg — that is why the original EXTEND was futile). Instead **re-melt and re-cool more slowly**, starting from the converged **melt** cell (`npt_production_out.data` at T_equil, NOT the 300 K cell):
1. `generate_equilibration_workflow(data_file=<npt_production_out.data>, max_temp=T_anneal_high_K, ...)` with **more annealing cycles** (e.g. 5 → 8–10, NkepsuMbitou-style) AND a **slower cool** — increase the cooling-stage step count / reduce the K-per-stage so the cell relaxes free volume through Tg (target a cooling rate at/below the class default, not faster).
2. Resubmit via `run_lammps_chain`, re-run BACKGROUND-WAIT, then re-run equil-check + `assess_cooling_contraction` on the new `npt_prod300_out.data`.
3. Max 2 re-anneal attempts. If density still under-band after 2, the deficit is no longer cooling-limited → re-classify as `MELT_STAGE_DEFICIT` (force-field / melt-anneal) and record the evidence rather than looping.
This is the *intended* re-melt (contrast the extend-mode warning below, where re-melting a cooled cell is an *accident*).

**Chain droplets / vacuum voids:** Initial density too high. Rebuild at `density=0.05`.

**"Out of range atoms — cannot compute PPPM" in npt_compress:** Switch `npt_compress` pair_style to `lj/cut/coul/cut`, increase neighbor skin 2.0 → 3.0 Å, reduce dt to 0.5 fs for that run only. Restore `lj/cut/coul/long` + kspace_style from `npt_pppm` onward.

**Same PPPM error at `nvt_softheat` step 0→1 with minimize completed:** a localized EMC pack overlap unique to that seed (soft class2 9-6 core lets near-coincident atoms through minimization; post-minimize Press/E_vdwl strongly positive). Rebuild the cell with a fresh EMC seed — no deck surgery, no extra minimize. If a second seed also fails at softheat, drop `density_initial` 0.6 → 0.5 before any deck edits.

**Extend run returns 7 stages instead of 1:** `generate_equilibration_workflow(extend_only=True)` must yield `n_stages==1` with `run_order==["npt_extend"]` — verify this before submitting. A full 7-stage chain means the live MCP server is running stale code (pre-`extend_only`); request an orchestrator-level server restart. Do NOT submit (the chain's `nvt_softheat` 300→600 K re-melts a cooled glassy cell) and do NOT hand-write a `.in`.

**Disk-full I/O error mid-chain (e.g. restart write fails):** completed stages' `_out.data` stay intact. Free disk, then delete only the failed stage's partial outputs, regenerate the full workflow with identical params, slice the stage list to resume at the failed stage, and resubmit via `run_lammps_chain`. Do NOT restart from stage 0 (PEEK3 2026-06-24: recovered stages 4–9 only). Prevention: when free disk is <60 GB, strip the `dump`/`undump`/`write_dump` lines from the production stages' `.in` before submitting — nothing downstream reads `npt_prod300.dump` (equil-check uses the log + `nvt_production.dump`; the mechanical track uses `_out.data`).

## Backlog

- `generate_equilibration_workflow` should accept a `disable_prod_dump` flag so production stages write only thermo + final `.data` (the manual dump-line strip above becomes unnecessary).
