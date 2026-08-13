# Run-Summary-Worker Memory Index

- [Async tool no polling](feedback_async_tool_no_polling.md) — generate_run_summary is async but worker has no get_run_status; fallback via canonical path Read()
- [tg_k param does not exist](feedback_tg_k_param_nonexistent.md) — orchestrator --tg_k flag not in schema; use tg_path instead for single-rate Tg
- [K band override widening](feedback_k_band_override_widening.md) — exp_K_min/max overrides not fully respected; tool applies automatic band-widening logic
- [tg_reportable not checked](feedback_tg_reportable_not_checked.md) — generate_run_summary grades Tg PASS/FAIL even when tg_summary.json marks it non-reportable (TG_REVIEW); orchestrator's run_log.md is authoritative over run_summary.json's Tg status in that case
