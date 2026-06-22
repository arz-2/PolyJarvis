# Mechanical Track — Orchestrator Guide (Phase B)

Loaded on-demand by the orchestrator at Phase B entry when "bulk_modulus" in properties_requested.
On session restart mid-mechanical-track: re-read this file before resuming.

---

```
  [mechanical track — if "bulk_modulus" in properties_requested]
  # Born+NVT is REMOVED — do not spawn born-worker. Never use --stage born.
  # Glassy primary: Murnaghan NPT compression at 300 K (npt_prod300_out.data)
  # Rubbery primary: Murnaghan EOS at T>Tg (npt_production_out.data, bm_pressures_atm set)
  # GATE: Do not spawn murnaghan-worker (or deform-worker) until thermal track confirms
  # is_glassy=True (or glassy_hint=True when tg is skipped). Murnaghan at 300 K is the
  # glassy primary path only — launching before is_glassy is known wastes ~2–5 h if the
  # polymer is rubbery at 300 K (K_rubbery requires a different T and pressure range).
  if is_glassy or bm_pressures_atm is non-null in plan.decided_params:
    Claim GPU: scripts/pick_gpu.py --json claim --run <RUN> --need ${GPU_PER_RUN:-1}
    Agent(subagent_type="murnaghan-worker", description="🟠 Murnaghan BM {polymer_name}",
          prompt=<gen_prompt.py --stage murnaghan --plan PLAN_PATH
                  --data_path npt_prod300_data_path   # glassy: 300 K cell
                              # OR equil_data_path     # rubbery: melt cell
                  --gpu_ids <claimed>>)
      → parse RESULT → extract chain_id_murnaghan, log_files (murnaghan_log_files), monitor_command_murnaghan
    Write SIMULATION STATE (status=monitoring)
    Monitor(command=monitor_command_murnaghan, timeout_ms=3600000)
    scripts/pick_gpu.py release --run <RUN>
    get_run_status → completed → proceed to extraction
    # Check Murnaghan acceptance BEFORE extraction:
    #   extract_bulk_modulus_murnaghan → check fit_converged=True AND B0_prime ∈ [4, 20]
    #   If FAIL → spawn deform-worker fallback (3-direction)
    Recovery if murnaghan fails (fit_converged=False OR B0_prime outside [4, 20]):
      Claim GPU: scripts/pick_gpu.py --json claim --run <RUN> --need ${GPU_PER_RUN:-1}
      Agent(subagent_type="deform-worker", description="🔵 Deform fallback {polymer_name}",
            prompt=<gen_prompt.py --stage deform --plan PLAN_PATH --data_path npt_prod300_data_path
                    --gpu_ids <claimed>>)
        → parse RESULT → extract run_id_deform, deform_log_path, monitor_command_deform
      Write SIMULATION STATE (status=monitoring)
      Monitor(command=monitor_command_deform, timeout_ms=3600000)
      scripts/pick_gpu.py release --run <RUN>
  # else (rubbery + no pressures + bm_pressures_atm null): skip — fluctuation path, equil log already present

  # Key: for glassy Murnaghan always pass npt_prod300_data_path (300 K cell, not melt)
  # Never hand-enter exp_K/Tg/density ranges in run_log.md — copy from run-summary RESULT block
  Agent(subagent_type="bulk-modulus-extractor", description="🟢 Extract BM {polymer_name}",
        prompt=<gen_prompt.py --stage analyze-bm --plan PLAN_PATH
               [--deform_log deform_log_path]                                                     # deform fallback only
               [--murnaghan_logs '<JSON list of log_files>']                                      # Murnaghan path (primary)
               --npt_prod_log npt_prod_log_path>)                                                 # fluctuation cross-check (always passed)
    → parse RESULT → extract bulk_modulus_GPa, bulk_modulus_method → write D-07 to run_log.md
```
