# Equilibration Checker Memory Index

- [mcp_async_job_opacity](feedback_mcp_async_job_opacity.md) — MCP returned "Poll with get_run_status(run_id)" but tool unavailable; use filesystem monitoring instead
- [async_job_delay_and_cutoff_unused](feedback_async_job_delay_and_cutoff_unused.md) — comprehensive check ~120s latency; cutoff_A parameter silently ignored (L_over_2cutoff always null)
- [rubbery_ct_undecayed_pass](feedback_rubbery_ct_undecayed_pass.md) — C(t) tau_relax >> trajectory: comprehensive pass=false but gate returns PASS if binding gates pass (carve-out working as designed)
- [psu3_equil_aromatic_dp25](project_psu3_equil_aromatic_dP.md) — PSU3 DP=25 aromatic: C(t) advisory only; gate on density SEM/CV/P2/energy
- [pacr_backbone_auto_detection](feedback_pacr_backbone_type_detection.md) — PMMA/PACR: passed backbone_types=[1], check_equilibration_comprehensive auto-expanded to [1,3]; type 3 is carbonyl (not backbone) — flag if C(t) issues arise
- [scratchpad_prompt_unreachable](feedback_scratchpad_prompt_unreachable.md) — orchestrator passes eqcheck prompt in scratchpad; worker cannot access (context boundary); use data/** path instead
- [pla_backbone_ester_oxygen_type](feedback_pla_backbone_ester_oxygen.md) — PLA backbone type=[2,3,7] not [2,3,6]; o_2 (type 7) bridges units, o_1 (type 6) is pendant — verify coordination
- [comprehensive_check_timeout_large_dump](feedback_comprehensive_check_timeout.md) — check_equilibration_comprehensive hung 30+ min on 312 MB dump, produced no JSON; MCP server unresponsive or queued indefinitely
- [comprehensive_async_hang_full_phase](feedback_comprehensive_async_hang_full_phase.md) — melt-phase JSON unsafe for full-phase gate (T_mean differs); async job hung on full-phase run; check T_mean, rename cached JSON, investigate dump subsample
