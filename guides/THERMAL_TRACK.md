# Thermal Track — Orchestrator Guide (Phase B)

Loaded on-demand by the orchestrator at Phase B entry when "tg" in properties_requested.
On session restart mid-thermal-track: re-read this file before resuming.

---

```
  [thermal track — if "tg" in properties_requested]  # MULTIRATE: one sweep PER cooling rate
  Read multirate config from the plan:
    TG_RATES=$(jq -r '.decided_params.tg_rates_K_per_ns | @csv' PLAN_PATH)     # e.g. 40,160,400
    DSC_RATE=$(jq -r '.decided_params.dsc_equiv_rate_K_per_ns // 1.6667e-10' PLAN_PATH)
  Read replicate N from run_log.md header ("Replicate: N of M").

  For idx, rate in enumerate(TG_RATES):                # idx = 0,1,2 → rates 40,160,400 K/ns
    [Tg sweep @ rate]
    Claim GPU(s): scripts/pick_gpu.py --json claim --run <RUN> --need ${GPU_PER_RUN:-1}
      → on shortfall (exit 1) defer/retry; NEVER --allow-busy on the shared box.
    Agent(subagent_type="tg-sweep-worker", description="🟣 Tg sweep r{rate} {polymer_name}",
          prompt=<gen_prompt.py --stage tg --plan PLAN_PATH --data_path equil_data_path
                  --tg_rate_index {idx} --gpu_ids <claimed>>)
      → parse RESULT → run_id, tg_log_path (now .../thermal/tg_sweep_r{rate}/tg_sweep.log), monitor_command
    Write SIMULATION STATE (status=monitoring) to run_log.md
    Monitor(command=monitor_command, timeout_ms=3600000)
    scripts/pick_gpu.py release --run <RUN>
    get_run_status(run_id) → completed → proceed; failed → /recover (max 2/worker)

    [Tg analysis @ rate]
    Agent(subagent_type="tg-analysis-worker", description="🟢 Extract Tg r{rate} {polymer_name}",
          prompt=<gen_prompt.py --stage analyze-tg --plan PLAN_PATH
                  --data_path {tg_log_path} --tg_rate_index {idx}>)
      → parse RESULT → Tg_K, Tg_fit_quality, Tg_r_squared, cooling_rate_K_per_ns
    Append one row to the multirate registry (see registry section below):
      replicate=N, rate, Tg_K, Tg_r_squared, Tg_fit_quality, run_name, timestamp_utc

  # On a single-GPU host (e.g. PEG1, GPU 0 only) the three sweeps run SEQUENTIALLY → ~3× thermal
  # wall time (the 40 K/ns rate has 10× the steps of 400 K/ns and dominates). On a multi-GPU host
  # with ≥3 free GPUs the rates are independent: you MAY claim a distinct GPU per rate and run the
  # three sweeps + Monitors in parallel (still politely — defer on shortfall, never --allow-busy).

  [multirate extrapolation → DSC-equivalent Tg]
  Build --mr_rates / --mr_tg_values from ALL registry rows for this polymer/class
    (filter to fit_quality >= ACCEPTABLE; if < 2 rows survive, skip aggregation and fall back
     to the single highest-rate Tg). Across replicates this list grows → the fit tightens.
  Agent(subagent_type="tg-analysis-worker", description="🟢 Multirate Tg {polymer_name}",
        prompt=<gen_prompt.py --stage analyze-tg-multirate --plan PLAN_PATH
                --mr_rates <rates> --mr_tg_values <tgs>>)
    → parse RESULT → tg_dsc_equiv_K, loglinear_slope_K, loglinear_r_squared, vf_fit_quality
    → write D-06b to run_log.md from d06_markdown_path. Report tg_dsc_equiv_K as the headline
      "theoretical DSC-equivalent experimental Tg".
  Validator gate: loglinear_r_squared >= plan success_criteria.loglinear_r_squared_min (0.90).
    Not met → /recover (re-run a noisy rate with more steps, or re-plan), max 2 attempts.

  [is_glassy determination]
  if "tg" in properties_requested:
    Tg_for_glassy = Tg_K at the HIGHEST screening rate (400 K/ns)  # protocol-fixed, reproducible (NOT most-equilibrated — that's the slowest rate; this is a stable is_glassy gate, see below)
    is_glassy = (Tg_for_glassy > 300)   # safe default: True if None or fit ABORT
    # Drive is_glassy off the highest-rate MD Tg, NOT tg_dsc_equiv_K: the extrapolated value
    # shifts as replicates accumulate and could flip the mechanical-track branch mid-campaign.
  else:
    is_glassy = glassy_hint      # from plan; write D-06 = "N/A — tg not requested"
    Tg_K = None; Tg_fit_quality = "N/A (not requested)"; tg_dsc_equiv_K = None
```

---

## Multirate Tg registry

- **File:** `data/_tg_registry/<CLASS_ID>__<polymer_slug>.csv` (append-only; survives across runs). `<polymer_slug>` = filesystem-safe SMILES slug.
- **Header:** `replicate,rate_K_per_ns,Tg_MD_K,r_squared,fit_quality,run_name,timestamp_utc`
- **Write:** append one row after each per-rate `analyze-tg` (3 rows/replicate).
- **Read:** pass ALL rows for this polymer (filtered to `fit_quality >= ACCEPTABLE`) as `--mr_rates`/`--mr_tg_values` to `analyze-tg-multirate`. If < 2 rows survive, fall back to the single highest-rate Tg.
