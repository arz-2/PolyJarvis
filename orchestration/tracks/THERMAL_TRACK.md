# Thermal Track — Orchestrator Guide (Phase B)

Governs the `reasoned` path when "tg" in properties_requested; loaded on-demand at Phase B entry.
For `plan_mode=="deterministic"`, see `DETERMINISTIC_REPLICATE.md` instead (same single-sweep /
is_glassy logic, no agent spawns). Re-read this file after a mid-thermal-track session restart.

Single sweep at the class's primary configured rate, reported honestly against experiment — no
offset baked into PASS/FAIL.

---

```
  [thermal track — if "tg" in properties_requested]
  TG_RATES=$(jq -r '.decided_params.tg_rates_K_per_ns | @csv' PLAN_PATH)     # e.g. 25,50,100
  FALLBACK=$(jq -r '.decided_params.tg_slope_gate_fallback // empty' PLAN_PATH)
  IDX = 0 if FALLBACK == "slowest_rate" else (len(TG_RATES) - 1)   # else highest rate

  [Tg sweep @ primary rate]
  Claim GPU(s): orchestration/scripts/pick_gpu.py --json claim --run <RUN> --need ${GPU_PER_RUN:-1}
    → on shortfall (exit 1) defer/retry; NEVER --allow-busy on the shared box.
  Agent(subagent_type="tg-sweep-worker", description="🟣 Tg sweep {polymer_name}",
        prompt=<gen_prompt.py --stage tg --plan PLAN_PATH
                [--tg_start_data $npt_tg_prep_data | --data_path $npt_prod300_out_data]
                --tg_rate_index {IDX} --gpu_ids <claimed>>)
    → RESULT → run_id, tg_log_path (.../thermal/tg_sweep_r{rate}/tg_sweep.log), monitor_command
  Write SIMULATION STATE to run_log.md, then BACKGROUND-WAIT on `monitor_command` — keep the GPU
    claimed until the wakeup.
  # completion wakeup:
  orchestration/scripts/pick_gpu.py release --run <RUN>
  get_run_status(run_id) → RUN_COMPLETE/completed → proceed; PROCESS_DEAD_NO_SENTINEL/failed →
    RECOVERY (`track=thermal step=tg`)

  [Tg analysis @ primary rate]
  Agent(subagent_type="tg-analysis-worker", description="🟢 Extract Tg {polymer_name}",
        prompt=<gen_prompt.py --stage analyze-tg --plan PLAN_PATH
                --data_path {tg_log_path} --tg_rate_index {IDX}>)
    → RESULT → Tg_K, Tg_fit_quality, Tg_r_squared, tg_gate_verdict, tg_method_gap_K,
               cooling_rate_K_per_ns, output_dir
  Hold (Tg_K, Tg_fit_quality, tg_gate_verdict, output_dir) in state and the D-06 run_log row.

  [Tg reportability]
  if tg_gate_verdict == "TG_NOT_REPORTABLE":  report no Tg value; D-06 records tg_gate_reasons.
  if tg_gate_verdict == "TG_REVIEW":       halt to human review before reporting Tg.
  Either way, continue to the is_glassy determination below — routing is a separate decision.

  [is_glassy determination]
  if "tg" in properties_requested:
    used_highest_rate = (IDX == len(TG_RATES) - 1)
    degenerate = (Tg_fit_quality == "POOR") or (not used_highest_rate)
    if degenerate:
      is_glassy = (experimental_tg_K > 300)   # plan decided_params.experimental_tg_K
      # D-06 note: "is_glassy from plan exp-Tg (MD fit degenerate or non-highest rate)"
    else:
      is_glassy = (Tg_K > 300)       # True if None
  else:
    is_glassy = glassy_hint      # from plan; D-06 = "N/A — tg not requested"
    Tg_K = None; Tg_fit_quality = "N/A (not requested)"
```
