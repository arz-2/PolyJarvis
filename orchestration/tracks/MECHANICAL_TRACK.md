# Mechanical Track — Orchestrator Guide (Phase B)

Governs the `reasoned` path when "bulk_modulus" in properties_requested; loaded on-demand at
Phase B entry. Re-read this file after a mid-mechanical-track session restart.

GATE: do not spawn murnaghan-worker or deform-worker until the thermal track has set is_glassy
(or glassy_hint, when tg is skipped).

---

```
  [mechanical track — if "bulk_modulus" in properties_requested]
  if is_glassy or bm_pressures_atm is non-null in plan.decided_params:
    Claim GPU: orchestration/pick_gpu.py --json claim --run <RUN> --need ${GPU_PER_RUN:-1}
    Agent(subagent_type="murnaghan-worker", description="🟠 Murnaghan BM {polymer_name}",
          prompt=<gen_prompt.py --stage murnaghan --plan PLAN_PATH
                  --data_path npt_prod_data_path --gpu_ids <claimed>>)
      → RESULT → chain_id_murnaghan, log_files (murnaghan_log_files), monitor_command_murnaghan
    Write SIMULATION STATE, then BACKGROUND-WAIT on `monitor_command_murnaghan`.
    # completion wakeup:
    orchestration/pick_gpu.py release --run <RUN>
    get_run_status → RUN_COMPLETE/completed → proceed to extraction; PROCESS_DEAD_NO_SENTINEL/failed → /recover
    # Rubbery Murnaghan: if dV/dP jumps >3x between pressure intervals, report low-P points only.

    Recovery if murnaghan fails (fit_converged=False):
      Claim GPU: orchestration/pick_gpu.py --json claim --run <RUN> --need ${GPU_PER_RUN:-1}
      Agent(subagent_type="deform-worker", description="🔵 Deform fallback {polymer_name}",
            prompt=<gen_prompt.py --stage deform --plan PLAN_PATH --data_path npt_prod_data_path
                    --deform_rate_mode primary --gpu_ids <claimed>>)
        → RESULT → run_id_deform, deform_log_path, monitor_command_deform
      Write SIMULATION STATE, then BACKGROUND-WAIT on `monitor_command_deform`.
      # completion wakeup: orchestration/pick_gpu.py release --run <RUN>

      Always spawn a second deform-worker for the rate-sensitivity check (no-ops safely if the
      class has no K_deform_rate_slow_inv_s):
        Claim GPU: orchestration/pick_gpu.py --json claim --run <RUN> --need ${GPU_PER_RUN:-1}
        Agent(subagent_type="deform-worker", description="🔵 Deform rate-check {polymer_name}",
              prompt=<gen_prompt.py --stage deform --plan PLAN_PATH --data_path npt_prod_data_path
                      --deform_rate_mode slow --gpu_ids <claimed>>)
          → RESULT → deform_log_path_slow, monitor_command_deform_slow
        If `monitor_command_deform_slow` is null: release the GPU immediately, proceed to
          extraction with deform_log_path_slow=null.
        Else: Write SIMULATION STATE, BACKGROUND-WAIT on `monitor_command_deform_slow`, then
          release the GPU on the completion wakeup.
  # else (rubbery + no pressures): skip — fluctuation path, equil log already present

  Agent(subagent_type="bulk-modulus-extractor", description="🟢 Extract BM {polymer_name}",
        prompt=<gen_prompt.py --stage analyze-bm --plan PLAN_PATH
               [--deform_log deform_log_path]
               [--deform_log_slow deform_log_path_slow]
               [--murnaghan_logs '<JSON list of log_files>']
               --npt_prod_log npt_prod_log_path>)
    → RESULT → bulk_modulus_GPa, bulk_modulus_method → write D-07 to run_log.md
```
