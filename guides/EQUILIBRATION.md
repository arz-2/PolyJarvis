# Equilibration Guide
**Read when:** You have a `.data` file and need to submit the equilibration chain.
**Worker:** equilibration-worker — return RESULT block to orchestrator when done.

---

## Rules

`temp` (= `T_workflow_K` from the prompt, already resolved upstream from `exp_Tg_K` — pass it
through as-is, don't re-derive it) selects the chain: `≤ 300.0` (rubbery) → 7-run chain ending
at `npt_production` (this stage is the density/bulk-modulus source); `> 300.0` (glassy) → 9-run
chain (`npt_cool300` + `npt_prod300` auto-appended, with `npt_prod300` as the density/deformation
source — no separate cooling phase needed). Use the return dict keys (`npt_production_dir`,
`npt_prod300_data`, …) as downstream paths — never construct paths manually. Stage directories
are NOT numbered on disk — every stage's path is `{work_dir_base}/{name}` (e.g.
`<work_dir>/npt_production/`, not `<work_dir>/07_npt_production/`).

When `add_melt_npt=True` (rubbery), the return dict also has `npt_tg_prep_data` (path to
`npt_melt_out.data`, isothermal NPT at `T_equil_K`) — the Tg-sweep starting cell. Do NOT use
`npt_production_out.data` for rubbery Tg sweeps (too close to Tg, biases the density slope).
Include `npt_tg_prep_data` in RESULT so the orchestrator threads it to the thermal track.

Extend mode's `temp` param must be `npt_prod_temp_K` (production temp of the cell being
extended = 300 K for BOTH regimes: glassy cooled to 300, rubbery produced at 300) — NOT
`T_equil_K`/`T_workflow_K`, which would re-melt the cooled cell.

`info.validation.errors` must be empty before proceeding past the initial inspect.

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

### Extend mode (`mode: extend`)

Triggered when the prompt sets `mode: extend` (with `extend_from_data: <last NPT _out.data>` and
optional `extend_ns: <1-2>`). Do NOT hand-write a continuation `.in` — generate it
deterministically with the same tool, `extend_only=True`:

```python
info = inspect_data_file(data_file=extend_from_data)   # sanity-check the equilibrated cell
workflow = generate_equilibration_workflow(
    data_file=extend_from_data,
    work_dir_base=work_dir,
    use_pcff=..., use_opls=..., use_trappe=...,
    temp=npt_prod_temp_K,   # see Rules above — NOT T_equil_K/T_workflow_K
    press=<same as original run>,
    engine=<same as original run>,
    extend_only=True,
    extend_steps=int(extend_ns * 1e6 / dt_fs),
)   # → a single `npt_extend` stage
result = run_lammps_chain(stages=workflow["stages"], gpu_ids=gpu_ids, mpi=mpi_ranks, engine=engine)
w = watch_run(result["chain_id"])
```

Return the standard RESULT block with `npt_prod_data_path` =
`workflow["npt_production_dir"]/npt_extend_out.data` (the orchestrator re-runs equil-check on it).
