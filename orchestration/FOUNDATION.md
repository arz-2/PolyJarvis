# FOUNDATION track guide (Phase A) — orchestrator-read

Read this at **Phase A entry**, before spawning the build/equil workers. Foundation always runs
and feeds every downstream track; density comes from the equil-check gate. All worker prompts are
generated with `gen_prompt.py --stage <STAGE> --plan PLAN_PATH [--data_path ...]` — never read
`polymer_rules.json` manually; the plan's `decided_params` drive the prompts. `BACKGROUND-WAIT` is
the canonical wait pattern defined in `CLAUDE.md` — launch the detached waiter, then end your turn.

## [Build]

```
Agent(subagent_type="molecule-builder", description="🔵 Build {polymer_name} cell",
      prompt=<gen_prompt.py --stage build --plan PLAN_PATH>)
  → RESULT → data_path, lammps_flags, emc_seed (integer or null)
  → immediately write emc_seed to run_log.md header Seeds line (never log -1; log null if RadonPy path)
```

## [Equilibration]

```
Agent(subagent_type="equilibration-worker", description="🟠 Equilibrate {polymer_name}",
      prompt=<gen_prompt.py --stage equil --plan PLAN_PATH --data_path ...>)
  → RESULT → chain_id, monitor_command, expected_equil_data, npt_tg_prep_data
    (npt_tg_prep_data non-null for rubbery polymers — npt_melt at T_equil_K; null for glassy)
```

Write SIMULATION STATE to run_log.md (status=monitoring, + bg task id), then run **BACKGROUND-WAIT**
(see CLAUDE.md): `Bash(command=monitor_command, run_in_background=true)` and END YOUR TURN.

## [Equil-check gate]

```
Agent(subagent_type="equilibration-checker", description="🟠 Equil check {polymer_name}",
      prompt=<gen_prompt.py --stage equil-check --plan PLAN_PATH --data_path npt_prod_data_path>)
  → RESULT → equil_verdict, density_gcm3, ct_decay_fraction, ct_tau_relax_ps,
      end_to_end_r_mean_A, end_to_end_r_std_A, end_to_end_n_chains
    → write D-05 to run_log.md (populate Chain Structure Summary rows from these fields)
```

- **equil_verdict=EXTEND** → re-spawn equilibration-worker in extend mode (prompt: mode=extend,
  extend_from_data=`<npt_prod_data_path>`, extend_ns=1–2, press/engine same, temp=npt_prod_temp_K —
  the 300 K production temperature of the cell, **NOT** the melt T_equil/T_workflow; the melt T
  would re-melt a cooled glassy cell). The worker generates a single deterministic npt_extend stage
  via `generate_equilibration_workflow(extend_only=True)` and submits it — do **not** hand-write a
  continuation `.in`. Re-run BACKGROUND-WAIT, then re-run equil-check on `npt_extend_out.data`
  (max 2 extensions).
- **equil_verdict=FAIL** → write UNRESOLVED to run_log.md and stop.
