# Mechanical Track — Orchestrator Guide (Phase B)

Governs the `reasoned` path when "bulk_modulus" in properties_requested; loaded on-demand at
Phase B entry. Re-read this file after a mid-mechanical-track session restart.

GATE: do not spawn murnaghan-worker or deform-worker until the thermal track has set is_glassy
(or glassy_hint, when tg is skipped).

---

```
  [mechanical track — if "bulk_modulus" in properties_requested]
  # Murnaghan always submits — glassy, rubbery with a class ladder, and rubbery with no
  # ladder (PROBE ladder, Leg 1) all go through the same spawn below.
  is_novel_rubbery_probe = (not is_glassy) and (plan.decided_params.bm_pressures_atm is null)

  Claim GPU: orchestration/scripts/pick_gpu.py --json claim --run <RUN> --need ${GPU_PER_RUN:-1}
  Agent(subagent_type="murnaghan-worker", description="🟠 Murnaghan BM {polymer_name} (leg 1)",
        prompt=<gen_prompt.py --stage murnaghan --plan PLAN_PATH --is_glassy <is_glassy>
                --data_path npt_prod_data_path --gpu_ids <claimed>>)
    → RESULT → chain_id_murnaghan, log_files (murnaghan_log_files), monitor_command_murnaghan,
               pressures_atm_murnaghan
  Write SIMULATION STATE, then BACKGROUND-WAIT on `monitor_command_murnaghan`.
  # completion wakeup:
  orchestration/scripts/pick_gpu.py release --run <RUN>
  get_run_status → RUN_COMPLETE/completed → proceed to extraction; PROCESS_DEAD_NO_SENTINEL/failed →
    RECOVERY (`track=mechanical step=murnaghan`)

  Agent(subagent_type="bulk-modulus-extractor", description="🟢 Extract BM {polymer_name} (leg 1)",
        prompt=<gen_prompt.py --stage analyze-bm --plan PLAN_PATH
               [--murnaghan_logs '<JSON list of log_files>']
               --npt_prod_log npt_prod_log_path>)
    → RESULT → bulk_modulus_GPa, bulk_modulus_method, excluded_points, selected_window
  # If leg 2 does NOT fire below, this IS the final result → write D-07 to run_log.md now.

  If the probe log itself crashed (missing/truncated — analyze-bm's own call errors reading
  it, distinct from a normal excluded_points screening flag): see recover.md's taxonomy row
  for this — re-run analyze-bm on the remaining compression-only logs, do not resubmit the
  probe.

  # Leg 2 (conditional deeper tension) — ONLY when is_novel_rubbery_probe and the probe point
  # (the most negative pressure, e.g. -200 atm) came back clean: present in log_files with a
  # full production window, AND absent from excluded_points.
  if is_novel_rubbery_probe and probe point clean:
    Patch decided_params.bm_pressures_atm=[-1000] into run_plan.json (same apply_plan() overlay
      pattern recover.md's RE-ANNEAL procedure already uses for npt_cool_steps).
    Claim GPU: orchestration/scripts/pick_gpu.py --json claim --run <RUN> --need ${GPU_PER_RUN:-1}
    Agent(subagent_type="murnaghan-worker", description="🟠 Murnaghan BM {polymer_name} (leg 2)",
          prompt=<gen_prompt.py --stage murnaghan --plan PLAN_PATH --is_glassy <is_glassy>
                  --data_path npt_prod_data_path --gpu_ids <claimed>>)
      → RESULT → chain_id_leg2, log_files_leg2 (one new log, the -1000 atm point)
    Write SIMULATION STATE, BACKGROUND-WAIT on the leg-2 monitor_command.
    # completion wakeup: pick_gpu.py release; get_run_status → proceed / PROCESS_DEAD →
    #   RECOVERY (track=mechanical step=murnaghan)
    Agent(subagent_type="bulk-modulus-extractor", description="🟢 Extract BM {polymer_name} (leg 2)",
          prompt=<gen_prompt.py --stage analyze-bm --plan PLAN_PATH
                 --murnaghan_logs '<leg 1's 4 compression logs + the new -1000 atm log>'
                 --npt_prod_log npt_prod_log_path>)
      → RESULT → final bulk_modulus_GPa (supersedes leg 1 — do not average the two legs) →
                 write D-07 to run_log.md (overwriting leg 1's provisional entry, if any)
  # else: leg 1's (already-screened) result is final. Note in run_log.md that tension beyond
  # the probe depth is untested for THIS system — never write a class-level bm_pressures_atm
  # from one system's outcome.

  Admissibility (both legs, and the deform fallback below) — route on the extractor's own verdict:
    bm_gate_verdict == "BM_REPORTABLE"       → write D-07 as usual.
    bm_gate_verdict == "BM_FALLBACK_DEFORM"  → the recovery path below (glassy only).
    bm_gate_verdict == "BM_INADMISSIBLE"     → do NOT write a K. Record bm_gate_reasons in D-07 and
      halt to human review. `volume_monotonic=false` means the offending pressure point must be
      re-run, not re-fitted. Same for deform_gate_verdict == "DEFORM_INADMISSIBLE" (K<0, E<0, or
      isotropy_delta_pct >= 20%).

  Recovery if murnaghan fails (fit_converged=False) — applies to whichever leg's extraction
  is final (glassy only has this fallback; rubbery does not):
    Claim GPU: orchestration/scripts/pick_gpu.py --json claim --run <RUN> --need ${GPU_PER_RUN:-1}
    Agent(subagent_type="deform-worker", description="🔵 Deform fallback {polymer_name}",
          prompt=<gen_prompt.py --stage deform --plan PLAN_PATH --data_path npt_prod_data_path
                  --is_glassy <is_glassy> --deform_rate_mode primary --gpu_ids <claimed>>)
      → RESULT → run_id_deform, deform_log_path, monitor_command_deform
    Write SIMULATION STATE, then BACKGROUND-WAIT on `monitor_command_deform`.
    # completion wakeup: orchestration/scripts/pick_gpu.py release --run <RUN>

    Always spawn a second deform-worker for the rate-sensitivity check (no-ops safely if the
    class has no K_deform_rate_slow_inv_s):
      Claim GPU: orchestration/scripts/pick_gpu.py --json claim --run <RUN> --need ${GPU_PER_RUN:-1}
      Agent(subagent_type="deform-worker", description="🔵 Deform rate-check {polymer_name}",
            prompt=<gen_prompt.py --stage deform --plan PLAN_PATH --data_path npt_prod_data_path
                    --is_glassy <is_glassy> --deform_rate_mode slow --gpu_ids <claimed>>)
        → RESULT → deform_log_path_slow, monitor_command_deform_slow
      If `monitor_command_deform_slow` is null: release the GPU immediately, proceed to
        extraction with deform_log_path_slow=null.
      Else: Write SIMULATION STATE, BACKGROUND-WAIT on `monitor_command_deform_slow`, then
        release the GPU on the completion wakeup.

      Agent(subagent_type="bulk-modulus-extractor", description="🟢 Extract BM {polymer_name} (deform)",
            prompt=<gen_prompt.py --stage analyze-bm --plan PLAN_PATH
                   --deform_log deform_log_path
                   [--deform_log_slow deform_log_path_slow]
                   --npt_prod_log npt_prod_log_path>)
        → RESULT → bulk_modulus_GPa, bulk_modulus_method → write D-07 to run_log.md
```
