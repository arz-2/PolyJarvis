# FOUNDATION track guide (Phase A) — orchestrator-read

This guide governs the `reasoned` path (`confidence` in {low, medium, offtable}) and Phase A's
Build→Equilibration flow for the `IS_NOVEL=true` case inside the `deterministic` path (see
`orchestration/DETERMINISTIC_REPLICATE.md`'s phase split for how the two interleave). For
`plan_mode=="deterministic"` Phase A execution otherwise, see `DETERMINISTIC_REPLICATE.md`.

Read this at **Phase A entry**, before spawning the build/equil workers. Foundation always runs
and feeds every downstream track; density comes from the equil-check gate. All worker prompts are
generated with `gen_prompt.py --stage <STAGE> --plan PLAN_PATH [--data_path ...]` — never read
`polymer_rules.json` manually; the plan's `decided_params` drive the prompts. `BACKGROUND-WAIT` is
the canonical wait pattern defined in `CLAUDE.md` — launch the detached waiter, then end your turn.

## [Build]

```
Agent(subagent_type="molecule-builder", description="🔵 Build {polymer_name} cell",
      prompt=<gen_prompt.py --stage build --plan PLAN_PATH>)
  → RESULT → data_path, emc_params_path (EMC builds only, else null), lammps_flags,
      emc_seed (integer or null)
  → immediately write emc_seed to run_log.md header Seeds line (never log -1; log null if RadonPy path)
```

Proceed straight to `[Equilibration]` regardless of `IS_NOVEL` — a genuinely novel SMILES runs
from class defaults with no pre-measurement, same as any other run; its equilibration result is
what populates `system_characterization_cache.json` afterward (see `[Equilibration]`'s mandatory
refine step below), not the other way around.

## [Equilibration]

```
Agent(subagent_type="equilibration-worker", description="🟠 Equilibrate {polymer_name}",
      prompt=<gen_prompt.py --stage equil --plan PLAN_PATH --data_path ...>)
  → RESULT → chain_id, monitor_command, expected_equil_data, npt_tg_prep_data,
      npt_prod_log_path, npt_prod_dump_path, npt_prod_data_path
    (npt_tg_prep_data non-null for rubbery polymers — npt_melt at T_equil_K; null for glassy)
```

Write SIMULATION STATE to run_log.md, then run BACKGROUND-WAIT on `monitor_command` (see CLAUDE.md).

If `IS_NOVEL=true`, once this chain's equil-check gate below returns `equil_verdict=PASS`,
**mandatory**: spawn `system-probe-analyzer` once to characterize this SMILES from the real
chain's own genuine stationary hold — the `npt_prod300` stage for glassy chains (300 K) or
`npt_production` for rubbery (target T; there is no `npt_prod300` stage for rubbery). **Not**
`npt_pppm` — it's a pressure ramp, not a hold. This is the only measurement this SMILES ever gets
(there is no separate pre-equilibration probe); it's longer and better-sampled than a short probe
could afford anyway, and matches the actual state point where the derived knobs get consumed
downstream (glassy Murnaghan work runs at `npt_prod300`; rubbery at `npt_production`).

```
Agent(subagent_type="system-probe-analyzer", description="🟢 Characterize {polymer_name} from equil",
      prompt="run_name: <RUN>\ncanonical_smiles: <CANONICAL_SMILES>\npolymer_class: <CLASS>\n"
             "run_plan_path: PLAN_PATH\ndata_file: <npt_prod_data_path>\n"
             "backbone_types: <from inspect_data_file, on the ORIGINAL pre-simulation .data file>\n"
             "output_dir: data/<RUN>/raw\ngraphs_dir: data/<RUN>/graphs\n"
             "log_file: <npt_prod_log_path>\ndump_file: <npt_prod_dump_path>")
  → RESULT → tau_relax_ps, tau_relax_reliable, K0_GPa, K0_reliable, fields_derived,
      cache_path, characterization_path
  → PLAN_PATH's decided_params.bm_pressures_atm/K_deform_rate_inv_s/_slow are patched in place if
    reliable (Phase B hasn't started yet — these still gate it); guides/system_characterization_
    cache.json[CANONICAL_SMILES] is created/updated only if at least one reliability flag is
    true — an unreliable characterization leaves the cache exactly as it was (absent, or
    present-with-partial-data from an earlier run), it does not force a write.
```

Write a `run_log.md` note: which knobs came from this characterization, which stayed at class
defaults. No re-critique — this is a narrowly-scoped numeric refinement of an already-approved
plan (mechanical-track knobs only), not a new decision category.

## [Equil-check gate]

```
Agent(subagent_type="equilibration-checker", description="🟠 Equil check {polymer_name}",
      prompt=<gen_prompt.py --stage equil-check --plan PLAN_PATH --data_path npt_prod_data_path>)
  → RESULT → equil_verdict, structural_fail_remedy, structural_fail_remedy_confidence,
      density_gcm3, ct_decay_fraction, ct_tau_relax_ps,
      end_to_end_r_mean_A, end_to_end_r_std_A, end_to_end_n_chains
    → write D-05 to run_log.md (populate Chain Structure Summary rows from these fields)
```

- **equil_verdict=EXTEND** → re-spawn equilibration-worker in extend mode (prompt: mode=extend,
  extend_from_data=`<npt_prod_data_path>`, extend_ns=1–2 (if this check's `ct_tau_relax_ps` is a
  finite, reasonably-fit number, prefer `extend_ns = max(1.5, 1.5 * ct_tau_relax_ps/1000)` over
  the flat guess — a measured signal from this run's own data beats a blind guess), press/engine
  same, temp=npt_prod_temp_K — the 300 K production temperature of the cell, **NOT** the melt
  T_equil/T_workflow; the melt T would re-melt a cooled glassy cell). The worker generates a single
  deterministic npt_extend stage via `generate_equilibration_workflow(extend_only=True)` and
  submits it — do **not** hand-write a continuation `.in`. Re-run BACKGROUND-WAIT, then re-run
  equil-check on `npt_extend_out.data` (max 2 extensions).
- **equil_verdict=STRUCTURAL_FAIL** → do NOT EXTEND (the cell converged to the wrong value, not
  merely an unconverged one) and do NOT silently accept as FF bias. Route through `/recover`
  (attempt cap, escalation ladder, low-confidence handling, and UNRESOLVED fallback are all owned
  by `.claude/commands/recover.md` §2b — don't re-derive those rules here) with
  `structural_fail_remedy` as diagnostic context. That field's text (emitted live by
  `enforce_gate.py`) already explains what the remedy means and cites its source where relevant —
  read it rather than re-deriving the diagnosis. What `/recover` needs from you that it can't get
  from the remedy string alone is the **worker-spawn routing**:
  - `re_melt_slow_recool` / `heavy_melt_anneal_probe` → fresh (non-extend) equilibration-worker
    spawn under a corrected protocol — never a continuation of the existing chain. If this is a
    recurring pattern for the class, consider bumping `guides/polymer_rules.json`'s class defaults
    per `.claude/commands/ingest-memory.md`'s existing rule.
  - melt-mixing remedy (density_homogeneity) → extend melt-stage dwell (`melt_npt_steps`/
    `t_equil_ns`) via a fresh equilibration-worker spawn, not an extend-mode continuation — the
    defect is upstream of the stage `extend` operates on. (Not covered in `recover.md`'s ladder —
    the routing above is FOUNDATION-specific.)
- **equil_verdict=FAIL** → write UNRESOLVED to run_log.md and stop.
