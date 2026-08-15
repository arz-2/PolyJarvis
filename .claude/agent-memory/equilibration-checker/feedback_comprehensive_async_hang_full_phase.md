---
name: comprehensive_async_hang_full_phase
description: check_equilibration_comprehensive MCP async job hangs on full-phase gate (npt_prod300 at 300K) with 312 MB nvt_production.dump; reuse of melt-phase JSON from same output_dir is unsafe
metadata:
  type: feedback
---

**Rule:** When enforce_equilibration_gate is called with a full-phase gate (after glassy cooldown), do not reuse equilibration_comprehensive.json from the melt-phase run in the same output_dir — T_mean will differ (620K vs 300K), breaking the density/energy analysis.

**Why:** On 2026-08-14 PLA1 full-phase gate, the existing equilibration_comprehensive.json was from melt phase (T_mean=620.45K, τ_relax=102645ps >> 951ps trajectory, decay=0.053). The MCP async call for full-phase comprehensive (dump 312 MB) submitted but hung after 120s with no output, consistent with [[comprehensive_check_timeout_large_dump]]. This forced an error block rather than a verdict. The melt JSON would have fabricated a full-phase result if passed to enforce_equilibration_gate unchecked.

**How to apply:** On full-phase gates:
1. Before calling check_equilibration_comprehensive, verify that any cached equilibration_comprehensive.json in output_dir reflects the correct phase — check T_mean in the file.
2. If reusing from melt phase (or any prior run), truncate or rename it so the async write doesn't collide.
3. If MCP async hangs >120s, the dump likely triggers the stall pattern in [[comprehensive_check_timeout_large_dump]] — escalate to restart the MCP server or investigate whether the dump can be pre-filtered (e.g., subsample frames, skip trajectory frames not needed for equilibration gates).
