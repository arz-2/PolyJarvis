# Equilibration Guide
**Read when:** You have a `.data` file and need to submit the equilibration chain.
**Worker:** equilibration-worker — return RESULT block to orchestrator when done.

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
    npt_prod_steps=npt_prod_steps,
    engine=engine,                               # selects deck (kokkos: no `package gpu` line)
    velocity_seed=velocity_seed,
    add_melt_npt=add_melt_npt,                   # True for rubbery (auto-set when T_workflow_K ≤ 300)
    t_equil_K=T_equil_K,                         # required when add_melt_npt=True
)
```

`temp` selects the chain: `≤ 300.0` (rubbery) → 7-run chain ending at `npt_production`;
`> 300.0` (glassy) → 9-run chain (`npt_cool300` + `npt_prod300` auto-appended). Use the
return dict keys (`npt_production_dir`, `npt_prod300_data`, …) as downstream paths — never
construct paths manually.

When `add_melt_npt=True` (rubbery), the return dict also has `npt_tg_prep_data` (path to
`npt_melt_out.data`, isothermal NPT at `T_equil_K`) — the Tg-sweep starting cell. Do NOT use
`npt_production_out.data` for rubbery Tg sweeps (too close to Tg, biases the density slope).
Include `npt_tg_prep_data` in RESULT so the orchestrator threads it to the thermal track.

### Step 3: Submit chain and watch

```python
result = run_lammps_chain(
    stages=workflow["stages"],
    gpu_ids=gpu_ids,
    mpi=mpi,
    data_file="{work_dir}/cell.data",
    params_file="{work_dir}/emc_build.params",  # EMC only
    engine=engine,                              # MUST match the workflow's engine
)
w = watch_run(result["chain_id"])
# Return chain_id and w["monitor_command"] to orchestrator — do not call Monitor.
```

---

## Common Failures

**GPU crash during NPT:** Check the log; do NOT switch to CPU. Causes: OOM (reduce system
size/GPUs), bad geometry (more minimize steps), pair-style mismatch (check params file).

**Density not converging:** Add annealing cycles (3–5).

**Chain droplets / vacuum voids:** Initial density too high — rebuild at `density=0.05`.

**"Out of range atoms — cannot compute PPPM" in npt_compress:** Switch `npt_compress`
pair_style to `lj/cut/coul/cut`, increase neighbor skin 2.0 → 3.0 Å, drop dt to 0.5 fs for
that run only. Restore `lj/cut/coul/long` + kspace_style from `npt_pppm` onward.

**Same PPPM error at `nvt_softheat` step 0→1 (minimize completed):** localized EMC pack
overlap for that seed. Rebuild the cell with a fresh EMC seed. If a second seed also fails,
drop `density_initial` 0.6 → 0.5 before any deck edits.

**Extend mode returns 7 stages instead of 1:** `generate_equilibration_workflow(extend_only=True)`
must yield `n_stages==1`, `run_order==["npt_extend"]` — verify before submitting. A full chain
means stale MCP server code; request an orchestrator server restart. Do NOT submit (its
`nvt_softheat` re-melts the cooled glassy cell) and do NOT hand-write a `.in`.

**RE-ANNEAL (equil-checker verdict `UNDER_ANNEALED_COOLING`):** melt density right but cooling
froze in free volume. Do NOT `EXTEND` at 300 K (a glass can't densify below Tg). Re-melt from
the converged **melt** cell (`npt_production_out.data` at T_equil, NOT the 300 K cell) via
`generate_equilibration_workflow` with more annealing cycles and a slower cool (rate at/below
the class default). Max 2 attempts; if still under-band, re-classify as `MELT_STAGE_DEFICIT`
and record the evidence rather than looping.

**Disk-full mid-chain:** completed stages' `_out.data` stay intact. Free disk, delete only the
failed stage's partial outputs, regenerate the workflow with identical params, slice the stage
list to resume at the failed stage, resubmit. Do NOT restart from stage 0. Prevention: when
free disk <60 GB, strip `dump`/`undump`/`write_dump` from the production stages' `.in` (nothing
downstream reads `npt_prod300.dump`).
