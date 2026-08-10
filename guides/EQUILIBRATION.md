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

Extend mode's `temp` param is the temperature of whichever stage is being extended, not
necessarily 300 K: `npt_prod_temp_K` (300 K) when extending the final production stage — NOT
`T_equil_K`/`T_workflow_K`, which would re-melt the cooled cell — but `T_workflow_K` when
extending the pre-cool melt checkpoint (`phase=melt`'s `npt_production`, per `/recover`'s
MELT-MIXING procedure). The rule is: match `temp` to the state you're actually dwelling longer
at, never the workflow's other temperature.

`info.validation.errors` must be empty before proceeding past the initial inspect.

`phase` (glassy runs only — `T_workflow_K > 300`; rubbery is always `full`, see FOUNDATION.md):
`melt` submits only through `npt_production` and defers the `npt_cool300`/`npt_prod300` tail
until the melt-mixing gate passes; `cooldown` submits that saved tail. `full` (default) is
today's single-submission behavior. See Step 3 below.

---

## Workflow

### Step 1: Copy and inspect the .data file

Copy the `.data` file from `data_path` to `{work_dir}/cell.data` **AND**, for EMC builds,
copy `emc_params_path` to `{work_dir}/emc_build.params` — this AND is load-bearing, not
optional: EMC `.data` files carry no `Coeffs` sections at all, every pair/bond/angle
coefficient lives in `emc_build.params`, and Steps 2/3 below already assume it's sitting
next to `cell.data`. `ls -la {work_dir}` to positively confirm both files landed before
proceeding — `inspect_data_file` does not itself verify the params file exists. Then:

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

`phase=full` (rubbery, or glassy default) — submit everything, unchanged:

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

`phase=melt` (glassy — gate before cooling): `workflow["stages"]` already has each stage's input
data path baked in at generation time (`generate_equilibration_workflow` resolves the whole chain
in one call, regardless of how much of it you submit), so submitting a prefix is safe — the tail
you don't submit yet stays valid to submit later unmodified.

```python
idx = workflow["run_order"].index("npt_production") + 1   # never hand-count — glassy adds
                                                            # npt_cool300/npt_prod300 after this
melt_stages, cooldown_stages = workflow["stages"][:idx], workflow["stages"][idx:]
Write(f"{work_dir}/_pending_cooldown_stages.json", json.dumps(cooldown_stages))
result = run_lammps_chain(stages=melt_stages, gpu_ids=gpu_ids, mpi=mpi,
                           data_file="{work_dir}/cell.data",
                           params_file="{work_dir}/emc_build.params", engine=engine)
w = watch_run(result["chain_id"])
```

Slice `workflow["stages"]` programmatically as shown above (`json.dumps`/`Write` on the
in-context `workflow` dict) rather than hand-copying stage dicts into the `Write` call —
transcription of a growing stage list risks silent field drift.

Return RESULT with `chain_id`, `monitor_command`, `npt_production_log_path`,
`npt_production_data_path`, `nvt_production_dump_path`, and
`pending_cooldown_path={work_dir}/_pending_cooldown_stages.json` — the orchestrator gates on these
via the melt-mixing equil-check (`phase=melt`) before ever spawning `phase=cooldown`.
The `RESULT:` block must be the entire final message — no leading status sentence, no
prose recap in place of it — for `phase=full`, `melt`, and `cooldown` alike; the
orchestrator parses it verbatim and a byte-for-byte `monitor_command` is required to
proceed with BACKGROUND-WAIT.

`phase=cooldown` (second spawn, only after the melt gate passes) — read the saved tail back and
submit it directly; **do not call `generate_equilibration_workflow` again**, it would regenerate
`minimize`/`nvt_softheat`/etc. from scratch instead of continuing from the melt state:

```python
cooldown_stages = json.loads(Read(pending_cooldown_path))
result = run_lammps_chain(stages=cooldown_stages, gpu_ids=gpu_ids, mpi=mpi, engine=engine)
w = watch_run(result["chain_id"])
```

Return the standard RESULT block (`npt_prod300_data`/`npt_prod300_log`/`npt_prod300_dump`, etc.)
exactly as `phase=full` does — downstream (thermal/mechanical tracks) never needs to know the
chain was submitted in two pieces.

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
