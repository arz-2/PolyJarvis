# Equilibration Checker Memory Index

- [mcp_async_job_opacity](feedback_mcp_async_job_opacity.md) — MCP returned "Poll with get_run_status(run_id)" but tool unavailable; use filesystem monitoring instead
- [async_job_delay_and_cutoff_unused](feedback_async_job_delay_and_cutoff_unused.md) — comprehensive check ~120s latency; cutoff_A parameter silently ignored (L_over_2cutoff always null)
- [rubbery_ct_undecayed_pass](feedback_rubbery_ct_undecayed_pass.md) — C(t) tau_relax >> trajectory: comprehensive pass=false but gate returns PASS if binding gates pass (carve-out working as designed)
- [psu3_equil_aromatic_dp25](project_psu3_equil_aromatic_dP.md) — PSU3 DP=25 aromatic: C(t) advisory only; gate on density SEM/CV/P2/energy
- [pacr_backbone_auto_detection](feedback_pacr_backbone_type_detection.md) — PMMA/PACR: passed backbone_types=[1], check_equilibration_comprehensive auto-expanded to [1,3]; type 3 is carbonyl (not backbone) — flag if C(t) issues arise
- [scratchpad_prompt_unreachable](feedback_scratchpad_prompt_unreachable.md) — orchestrator passes eqcheck prompt in scratchpad; worker cannot access (context boundary); use data/** path instead
