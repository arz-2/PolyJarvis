# Thermal Track — Orchestrator Guide (Phase B)

Loaded on-demand by the orchestrator at Phase B entry when "tg" in properties_requested.
On session restart mid-thermal-track: re-read this file before resuming.

---

```
  [thermal track — if "tg" in properties_requested]  # MULTIRATE: one sweep PER cooling rate
  Read multirate config from the plan:
    TG_RATES=$(jq -r '.decided_params.tg_rates_K_per_ns | @csv' PLAN_PATH)     # e.g. 25,50,100
    DSC_RATE=$(jq -r '.decided_params.dsc_equiv_rate_K_per_ns // 1.6667e-10' PLAN_PATH)

  For idx, rate in enumerate(TG_RATES):                # idx = 0,1,2 → rates 25,50,100 K/ns
    [Tg sweep @ rate]
    Claim GPU(s): scripts/pick_gpu.py --json claim --run <RUN> --need ${GPU_PER_RUN:-1}
      → on shortfall (exit 1) defer/retry; NEVER --allow-busy on the shared box.
    # Starting cell routing (Option C):
    #   Rubbery (npt_tg_prep_data non-null from equil RESULT): --tg_start_data $npt_tg_prep_data
    #   Glassy  (npt_tg_prep_data null):                        --data_path $npt_prod300_out_data
    Agent(subagent_type="tg-sweep-worker", description="🟣 Tg sweep r{rate} {polymer_name}",
          prompt=<gen_prompt.py --stage tg --plan PLAN_PATH
                  [--tg_start_data $npt_tg_prep_data | --data_path $npt_prod300_out_data]
                  --tg_rate_index {idx} --gpu_ids <claimed>>)
      → parse RESULT → run_id, tg_log_path (now .../thermal/tg_sweep_r{rate}/tg_sweep.log), monitor_command
    Write SIMULATION STATE (status=monitoring, + bg task id) to run_log.md
    BACKGROUND-WAIT (CLAUDE.md canonical pattern): Bash(command=monitor_command, run_in_background=true),
      then END YOUR TURN. Do NOT release the GPU or call get_run_status in this turn.
    # On the completion wakeup (next turn):
    scripts/pick_gpu.py release --run <RUN>
    get_run_status(run_id) → RUN_COMPLETE/completed → proceed;
      PROCESS_DEAD_NO_SENTINEL/failed → /recover (max 2/worker)

    [Tg analysis @ rate]
    Agent(subagent_type="tg-analysis-worker", description="🟢 Extract Tg r{rate} {polymer_name}",
          prompt=<gen_prompt.py --stage analyze-tg --plan PLAN_PATH
                  --data_path {tg_log_path} --tg_rate_index {idx}>)
      → parse RESULT → Tg_K, Tg_fit_quality, Tg_r_squared, cooling_rate_K_per_ns
    Hold (rate, Tg_K, Tg_r_squared, Tg_fit_quality) in orchestrator state and the D-06
      run_log row — inputs to the multirate fit below.

  # On a single-GPU host (e.g. PEG1, GPU 0 only) the three sweeps run SEQUENTIALLY → ~3× thermal
  # wall time (the 40 K/ns rate has 10× the steps of 400 K/ns and dominates). On a multi-GPU host
  # with ≥3 free GPUs the rates are independent: you MAY claim a distinct GPU per rate and run the
  # three sweeps in parallel — launch one BACKGROUND-WAIT waiter per sweep (run_in_background=true),
  # then end your turn; the harness wakes you once per sweep as each exits. Map each bg task id → run_id
  # via the SIMULATION STATE table so you know which sweep completed (still politely — defer on
  # shortfall, never --allow-busy).

  [multirate extrapolation → DSC-equivalent Tg]
  Build --mr_rates / --mr_tg_values from THIS RUN's per-rate results
    (filter to fit_quality >= ACCEPTABLE; if < 2 survive, skip aggregation and fall back
     to the single highest-rate Tg).
  Agent(subagent_type="tg-analysis-worker", description="🟢 Multirate Tg {polymer_name}",
        prompt=<gen_prompt.py --stage analyze-tg-multirate --plan PLAN_PATH
                --mr_rates <rates> --mr_tg_values <tgs>>)
    → parse RESULT → tg_dsc_equiv_K, loglinear_slope_K, loglinear_r_squared, vf_fit_quality
    → write D-06b to run_log.md from d06_markdown_path. Report tg_dsc_equiv_K as the headline
      "theoretical DSC-equivalent experimental Tg".
  Validator gate: loglinear_r_squared >= plan success_criteria.loglinear_r_squared_min (0.90).
    Not met → /recover (re-run a noisy rate with more steps, or re-plan), max 2 attempts.
    Exception: if result.is_flat_rate_regime == True, low R² is expected and the gate DOES NOT
    apply. extract_tg_multirate already set tg_method="flat_rate_mean" and reported the mean
    of per-rate values as tg_at_slow_rate_K. Accept that value directly.

  Rubbery polymers (T_workflow > Tg_exp + 20 K, e.g. PE, PBD):
    Rate-dependence of Tg is near-zero (|slope| < 1 K/decade) because the chain is already deep
    in the rubbery regime at T_workflow. The code detects this via is_flat_rate_regime=True and
    tg_method="flat_rate_mean". Report Tg_MD as the mean across rates with a note that this is a
    rubbery-regime estimate, NOT a DSC-equivalent extrapolation. Do NOT trigger /recover for low
    R² when is_flat_rate_regime=True.

  Slope gate (GLASSY only): for glassy polymers, if result.slope_gate_pass == False (slope ≤ 0)
    the per-rate data is contaminated. This is a HARD STOP: do NOT proceed to the mechanical
    track or run-summary until a sweep passes the gate. Discard this sweep's per-rate results.
    Spawn /recover immediately (re-run all 3 Tg sweeps from the same equil cell with a new
    velocity seed). Max 2 attempts total, then write UNRESOLVED to run_log.md and stop.
    Structural-fail exception (decided_params.tg_slope_gate_fallback set — PEST, PSFO, PKTN):
    slope-gate FAIL is the EXPECTED outcome for these classes, not seed noise, and seed rerolls
    cannot fix it — skip /recover entirely and use single_rate_fallback with the rate named by
    the field; select_tg_path.py applies it in Phase C (no hand override). Physics:
    - PEST (highest_rate): the stiff ester backbone delocalizes the transition at slow rates;
      every tested rate set fails. Highest rate = cleanest, least delocalized fit.
    - PSFO/PKTN (slowest_rate, Tg >> 300 K): the staircase cold-starts from the 300 K glassy
      cell, so the highest-T plateaus under-equilibrate at fast rates and INVERT the
      Tg-vs-rate trend (fast rate ⇒ spuriously low Tg). Slowest rate = most-equilibrated;
      report with a degeneracy caveat.
    is_glassy still settles from exp Tg; the mechanical track may proceed in parallel.
  Rubbery exemption: gen_prompt passes `--regime rubbery` to extract_tg_multirate for rubbery
    polymers (T_workflow >> Tg). In that regime a negative slope is meaningless scatter (the
    per-rate "Tg" is an extrapolation artefact), NOT contamination — the tool returns
    slope_gate_pass=True, tg_method="rubbery_flat_mean", rubbery_regime_exemption=True, and the
    per-rate results remain valid inputs to the flat-rate mean. Do NOT /recover on slope sign
    for rubbery. Equilibration quality is
    already guarded upstream by the equil-check require_rubbery carve-out (density SEM/CV); the
    slope-gate only guards glassy-Tg extrapolation, which the rubbery path never performs.
    VF caveat: a Vogel–Fulcher Tg0 fit needs ≥2 rate decades; our 3-rate sets span ~1 decade
    ([25,50,100] or [40,160,400] K/ns), so VF diverges ("initial guess outside bounds") — this is
    expected, and `rubbery_flat_mean` (mean of per-rate Tg) is the correct fallback (PEG3 2026-06-24).

  [is_glassy determination]
  if "tg" in properties_requested:
    Tg_for_glassy = Tg_K at the HIGHEST screening rate (400 K/ns)  # protocol-fixed, reproducible (NOT most-equilibrated — that's the slowest rate; this is a stable is_glassy gate, see below)
    # Default: drive is_glassy off the highest-rate MD Tg, NOT tg_dsc_equiv_K — the extrapolated
    # value carries wide slope uncertainty (~0.6-decade rate span) and is not a stable routing gate.
    # Exp-Tg fallback (degenerate fit): if the highest-rate fit is unreliable — fit_quality==POOR,
    # primary_fit_invalid==True (extract_thermal hard-constraint flag), the fit ABORTed, or the
    # multirate slope-gate failed (glassy) — an artefactual MD Tg must NOT decide routing. In that
    # case decide is_glassy from the plan's experimental Tg instead:
    #   is_glassy = (experimental_tg_K > 300)   # plan decided_params.experimental_tg_K
    # Otherwise:
    #   is_glassy = (Tg_for_glassy > 300)       # safe default: True if None
    if highest_rate_fit_degenerate:   # POOR / primary_fit_invalid / ABORT / glassy slope-gate fail
      is_glassy = (experimental_tg_K > 300)
      # Record D-06 note: "is_glassy from plan exp-Tg (MD fit degenerate)".
    else:
      is_glassy = (Tg_for_glassy > 300)
  else:
    is_glassy = glassy_hint      # from plan; write D-06 = "N/A — tg not requested"
    Tg_K = None; Tg_fit_quality = "N/A (not requested)"; tg_dsc_equiv_K = None
```

---

## Backlog

- Melt-start Tg sweep for rigid aromatics (PSFO/PKTN): start the staircase from a melt cell (or prepend a ≥750 K NPT pre-equilibration) so the top plateaus don't cold-start from glass — root fix for the inverted Tg-vs-rate trend that makes the slope gate structurally unpassable for these classes.
