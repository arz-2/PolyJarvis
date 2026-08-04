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
- **equil_verdict=STRUCTURAL_FAIL** → do **not** EXTEND (the cell converged to the wrong value, not
  merely an unconverged one — a glass cannot densify below Tg by running longer at 300 K) and do
  **not** silently accept as force-field bias. This is the same "worker result contradicts a plan
  assumption" case the cross-run protocol already covers (`decided_params`' anneal protocol turned
  out to be insufficient for this cell) — route through `/recover` (max 2 attempts/worker) with the
  `structural_fail_remedy` field as diagnostic context, not a bare re-attempt:
  - `re_melt_slow_recool` → the equilibration protocol itself needs correcting (more anneal cycles /
    slower cooling ramp — see `guides/polymer_rules.json`'s class defaults, which may already need a
    bump if this is a recurring pattern for the class, not a one-off). `/recover` should route to a
    **fresh** (non-extend) equilibration-worker spawn under a corrected protocol, not a continuation
    of the existing chain.
  - `heavy_melt_anneal_probe` → root cause (FF underbinding vs. melt under-annealing) is
    undetermined. `/recover` should not guess a fix — run the probe first (heavy melt anneal, per
    NkepsuMbitou 10-TAC), then re-diagnose before any protocol change.
  - melt-mixing remedy → extend melt-stage dwell (`melt_npt_steps`/`t_equil_ns`) via a fresh
    equilibration-worker spawn, not an extend-mode continuation (the defect is upstream of the stage
    `extend` operates on).
  If `/recover` exhausts its 2 attempts without a passing mechanized verdict, write UNRESOLVED to
  run_log.md and stop — same as FAIL, but with the full diagnostic trail attached.
  **`structural_fail_remedy_confidence=low`** (cooling span >300K, alpha-extrapolation unreliable —
  common for rigid/aromatic classes like PEEK): treat `re_melt_slow_recool`/`heavy_melt_anneal_probe`
  as a starting hypothesis, not a firm diagnosis. If attempt 1 under the named remedy doesn't fix it,
  do not spend attempt 2 on the same hypothesis — fall through to UNRESOLVED with a note that the
  melt/cooling split itself was low-confidence, rather than burning both attempts chasing a diagnosis
  the tool already flagged as shaky.
- **equil_verdict=FAIL** → write UNRESOLVED to run_log.md and stop.
