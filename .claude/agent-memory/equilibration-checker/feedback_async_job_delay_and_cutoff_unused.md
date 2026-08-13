---
name: async_job_delay_and_cutoff_unused
description: MCP check_equilibration_comprehensive has 2-min latency; cutoff_A parameter not reflected in output
metadata:
  type: feedback
---

**Rule:** check_equilibration_comprehensive submits async with run_id but get_run_status() unavailable. Comprehensive check takes ~120 seconds to complete after submission; filesystem monitoring required. Pass cutoff_A to enable finite-size gate (L >= 2*cutoff_A), but output shows "cutoff_A": null and L_over_2cutoff: null even when cutoff_A=12.0 is provided.

**Why:** MCP tool opacity makes tool-call result handling unpredictable. Cutoff parameter silently ignored, breaking the minimum-image diagnostic. This left a gap in the finite-size verdict on PMMA1 re-check.

**How to apply:** Always expect 2+ min roundtrip for comprehensive check. Provide cutoff_A explicitly when calling, but don't assume L_over_2cutoff will be populated — it's broken or intentionally omitted. Report L_over_2Rg and L_over_Ree as the binding finite-size metrics (must be >= 1.0); L_over_2cutoff remains informational when available.
