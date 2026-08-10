# FOUNDATION track guide (Phase A) — orchestrator-read

Governs Phase A's `reasoned` path and the `IS_NOVEL=true` Build→Equil-check leg inside
`deterministic` — see `DETERMINISTIC_REPLICATE.md` for how the two interleave and for
`plan_mode=="deterministic"` execution otherwise.

Read at Phase A entry, before spawning build/equil workers. Foundation always runs and feeds
every downstream track; density comes from the equil-check gate. Keep run_log.md notes terse:
cite the field/verdict, not rationale already covered here or in the spawned worker's own doc.

## [Build]

```
Agent(subagent_type="molecule-builder", description="🔵 Build {polymer_name} cell",
      prompt=<gen_prompt.py --stage build --plan PLAN_PATH>)
  → RESULT → data_path, emc_params_path (EMC builds only, else null), lammps_flags,
      emc_seed (integer or null)
  → write emc_seed to run_log.md header Seeds line
```

## [Equilibration]

Rubbery (`T_workflow_K ≤ 300`): single submission, `phase=full` (gen_prompt.py forces this
regardless of what's passed — nothing to gate early, `npt_production` is already both the melt
checkpoint and the final state). Glassy (`T_workflow_K > 300`): two submissions gated by a
melt-mixing check *before* the `npt_cool300`/`npt_prod300` cool-to-300 tail ever runs — a badly
mixed melt is caught without spending that ~1-3 ns of GPU time cooling it.

Claim GPU before every submission below; release on that
submission's completion wakeup — build is not a GPU stage, so no claim before `[Build]`.

**Rubbery / `phase=full`:**
```
Agent(subagent_type="equilibration-worker", description="🟠 Equilibrate {polymer_name}",
      prompt=<gen_prompt.py --stage equil --plan PLAN_PATH --data_path ...>)
  → RESULT → chain_id, monitor_command, expected_equil_data, npt_tg_prep_data,
      npt_prod_log_path, npt_prod_dump_path, npt_prod_data_path
    (npt_tg_prep_data non-null for rubbery polymers — npt_melt at T_equil_K; null for glassy)
```
Write SIMULATION STATE to run_log.md, then BACKGROUND-WAIT on `monitor_command`. Proceed to
`[Equil-check gate]` (`phase=full`).

**Glassy — melt phase (`phase=melt`):**
```
Agent(subagent_type="equilibration-worker", description="🟠 Equilibrate {polymer_name} (melt)",
      prompt=<gen_prompt.py --stage equil --plan PLAN_PATH --phase melt --data_path ...>)
  → RESULT → chain_id, monitor_command, npt_production_log_path, npt_production_data_path,
      nvt_production_dump_path, pending_cooldown_path
```
Write SIMULATION STATE to run_log.md, then BACKGROUND-WAIT on `monitor_command`. Proceed to
`[Equil-check gate]` (`phase=melt`) — do NOT submit the cooldown tail yet.

**Glassy — cooldown phase (`phase=cooldown`, only after the melt gate PASSes):**
```
Agent(subagent_type="equilibration-worker", description="🟠 Equilibrate {polymer_name} (cooldown)",
      prompt=<gen_prompt.py --stage equil --plan PLAN_PATH --phase cooldown
              --pending_cooldown_path <from melt-phase RESULT>>)
  → RESULT → chain_id, monitor_command, npt_prod_log_path, npt_prod_dump_path, npt_prod_data_path
    (same RESULT shape as phase=full — npt_prod300 paths)
```
Write SIMULATION STATE to run_log.md, then BACKGROUND-WAIT on `monitor_command`. Proceed to
`[Equil-check gate]` (`phase=full`) for the final density/cooling-contraction check.

If `IS_NOVEL=true`, once `[Equil-check gate]`'s `phase=full` call returns `equil_verdict=PASS`:
mandatory, spawn `system-characterization-analyzer` once:

```
Agent(subagent_type="system-characterization-analyzer", description="🟢 Characterize {polymer_name} from equil",
      prompt="run_name: <RUN>\ncanonical_smiles: <CANONICAL_SMILES>\npolymer_class: <CLASS>\n"
             "run_plan_path: PLAN_PATH\ndata_file: <npt_prod_data_path>\n"
             "backbone_types: <from inspect_data_file, on the ORIGINAL pre-simulation .data file>\n"
             "output_dir: data/<RUN>/raw\ngraphs_dir: data/<RUN>/graphs\n"
             "log_file: <npt_prod_log_path>\ndump_file: <npt_prod_dump_path>")
  → RESULT → tau_relax_ps, tau_relax_reliable, K0_GPa, K0_reliable, fields_derived,
      fields_kept_as_class_default, cache_path, characterization_path
```

Write a run_log.md note: `fields_derived` vs `fields_kept_as_class_default`. No re-critique —
this is a numeric refinement of an already-approved plan, not a new decision category.

## [Equil-check gate]

**`phase=full`** (rubbery's only gate; glassy's gate after cooldown):
```
Agent(subagent_type="equilibration-checker", description="🟠 Equil check {polymer_name}",
      prompt=<gen_prompt.py --stage equil-check --plan PLAN_PATH --data_path npt_prod_data_path>)
  → RESULT → equil_verdict, structural_fail_remedy, structural_fail_remedy_confidence,
      density_gcm3, ct_decay_fraction, ct_tau_relax_ps,
      end_to_end_r_mean_A, end_to_end_r_std_A, end_to_end_n_chains
    → write D-05 to run_log.md (Chain Structure Summary rows)
```
- `PASS` → proceed.
- `EXTEND` / `STRUCTURAL_FAIL` / `FAIL` → RECOVERY (`track=foundation step=equil-check`)

**`phase=melt`** (glassy only, before cooldown — structural/thermo gates only, no density
extraction, no cooling-contraction diagnosis; see `guides/EQUIL_CHECK.md`'s Phase section):
```
Agent(subagent_type="equilibration-checker", description="🟠 Melt-mixing check {polymer_name}",
      prompt=<gen_prompt.py --stage equil-check --plan PLAN_PATH --phase melt
              --data_path npt_production_data_path
              --npt_prod_log npt_production_log_path --npt_prod_dump nvt_production_dump_path>)
  → RESULT → equil_verdict, structural_fail_remedy, equilibration_warnings
```
- `PASS` → proceed to `[Equilibration]`'s cooldown phase.
- `EXTEND` / `STRUCTURAL_FAIL` (remedy is a melt-mixing note, never
  `re_melt_slow_recool`/`heavy_melt_anneal_probe` — those need the post-cool glass state, which
  doesn't exist yet) / `FAIL` → RECOVERY (`track=foundation step=equil-check`, MELT-MIXING
  procedure) — extends the melt checkpoint in place and re-runs this same `phase=melt` gate; only
  PASS here reaches cooldown.
