# Thermal Track — Orchestrator Guide (Phase B)

This guide governs the `reasoned` path. For `plan_mode=="deterministic"` Phase B execution, see
`orchestration/DETERMINISTIC_REPLICATE.md` (its scripted executor runs this same single-sweep /
is_glassy logic directly, no agent spawns).

Loaded on-demand by the orchestrator at Phase B entry when "tg" in properties_requested.
On session restart mid-thermal-track: re-read this file before resuming.

Default is single-rate-primary: one sweep at the class's primary configured rate, reported
honestly against experiment (no offset baked into PASS/FAIL). Multirate extrapolation
(`extract_tg_multirate.py`, `select_tg_path.py`, the `analyze-tg-multirate` stage) still exists
as a legacy/opt-in capability but is not part of this default flow.

---

```
  [thermal track — if "tg" in properties_requested]  # single sweep at the class's primary rate
  Read rate config from the plan:
    TG_RATES=$(jq -r '.decided_params.tg_rates_K_per_ns | @csv' PLAN_PATH)     # e.g. 25,50,100
    FALLBACK=$(jq -r '.decided_params.tg_slope_gate_fallback // empty' PLAN_PATH)
    # Primary-rate selection: highest configured rate by default (cheapest sweep, and is_glassy
    # is already keyed off the highest rate); classes whose highest rate is documented as
    # unreliable (PKTN, PSFO) name tg_slope_gate_fallback="slowest_rate" to run rates[0] instead.
    IDX = 0 if FALLBACK == "slowest_rate" else (len(TG_RATES) - 1)

  [Tg sweep @ primary rate]
  Claim GPU(s): orchestration/pick_gpu.py --json claim --run <RUN> --need ${GPU_PER_RUN:-1}
    → on shortfall (exit 1) defer/retry; NEVER --allow-busy on the shared box.
  # Starting cell routing (Option C):
  #   Rubbery (npt_tg_prep_data non-null from equil RESULT): --tg_start_data $npt_tg_prep_data
  #   Glassy  (npt_tg_prep_data null):                        --data_path $npt_prod300_out_data
  Agent(subagent_type="tg-sweep-worker", description="🟣 Tg sweep {polymer_name}",
        prompt=<gen_prompt.py --stage tg --plan PLAN_PATH
                [--tg_start_data $npt_tg_prep_data | --data_path $npt_prod300_out_data]
                --tg_rate_index {IDX} --gpu_ids <claimed>>)
    → parse RESULT → run_id, tg_log_path (.../thermal/tg_sweep_r{rate}/tg_sweep.log), monitor_command
  Write SIMULATION STATE (status=monitoring, + bg task id) to run_log.md
  BACKGROUND-WAIT (CLAUDE.md canonical pattern): Bash(command=monitor_command, run_in_background=true),
    then END YOUR TURN. Do NOT release the GPU or call get_run_status in this turn.
  # On the completion wakeup (next turn):
  orchestration/pick_gpu.py release --run <RUN>
  get_run_status(run_id) → RUN_COMPLETE/completed → proceed;
    PROCESS_DEAD_NO_SENTINEL/failed → /recover (max 2/worker)

  [Tg analysis @ primary rate]
  Agent(subagent_type="tg-analysis-worker", description="🟢 Extract Tg {polymer_name}",
        prompt=<gen_prompt.py --stage analyze-tg --plan PLAN_PATH
                --data_path {tg_log_path} --tg_rate_index {IDX}>)
    → parse RESULT → Tg_K, Tg_fit_quality, Tg_r_squared, cooling_rate_K_per_ns, output_dir
  Hold (Tg_K, Tg_fit_quality, output_dir) in orchestrator state and the D-06 run_log row —
    output_dir is TG_PATH's parent for Phase C (SUMMARY.md), no extra resolution step needed.

  [is_glassy determination]
  if "tg" in properties_requested:
    used_highest_rate = (IDX == len(TG_RATES) - 1)
    # is_glassy is only safe to compute from THIS sweep's Tg when it ran at the class's highest
    # configured rate (the protocol-fixed, reproducible gate). A class that deliberately ran the
    # slowest rate instead (PKTN, PSFO — their highest-rate fit is documented as degenerate/
    # inverted) falls through to the exp-Tg decision below — the same outcome those classes
    # already got via the old slope-gate-failure path, just reached directly now.
    degenerate = (Tg_fit_quality == "POOR") or (not used_highest_rate)
    if degenerate:
      is_glassy = (experimental_tg_K > 300)   # plan decided_params.experimental_tg_K
      # Record D-06 note: "is_glassy from plan exp-Tg (MD fit degenerate or non-highest rate)".
    else:
      is_glassy = (Tg_K > 300)       # safe default: True if None
  else:
    is_glassy = glassy_hint      # from plan; write D-06 = "N/A — tg not requested"
    Tg_K = None; Tg_fit_quality = "N/A (not requested)"
```

---

## Backlog

- Melt-start Tg sweep for rigid aromatics (PSFO/PKTN): start the staircase from a melt cell (or prepend a ≥750 K NPT pre-equilibration) so the top plateaus don't cold-start from glass — root fix for the inverted Tg-vs-rate trend that forces these classes onto the slowest-rate fallback instead of the default highest-rate primary.
