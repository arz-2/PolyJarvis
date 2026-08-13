---
name: k_band_override_widening
description: generate_run_summary applies automatic band-widening logic; exp_K_min/max overrides are not fully respected
metadata:
  type: feedback
---

**Rule:** Expect `exp_K_range` to be widened even when explicitly specified. The tool has internal band-widening logic that overrides input parameters.

**Why:** 2026-08-11 cis-PBD1 run: orchestrator specified exp_K_range=[1.31, 1.448] (±5% band around 1.379) verbatim as an override. The tool accepted the parameters but output exp_range_GPa=[1.2411, 1.5169] (±10% band, same midpoint). The `band_widened: true` flag in results.bulk_modulus confirms automatic widening occurred. Orchestrator's intent to grade K against ±5% band was not fully realized; grading used ±10% band instead, lowering error_pct from 33% to 21%.

**How to apply:** When reviewing K results, check `band_widened` field. If true and differs from input, note that the tool's automatic logic took precedence. For critical K overrides (especially polymers with narrow exp ranges like cis-PBD), consider whether the widened band still achieves the intended FAIL/PASS outcome. If band widening breaks the grading intent, this may require manual JSON patch or escalation.
