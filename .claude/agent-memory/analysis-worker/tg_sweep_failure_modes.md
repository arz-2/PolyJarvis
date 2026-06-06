---
name: tg-sweep-failure-modes
description: How extract_tg's "Bilinear curve_fit failed" error usually means a defective sweep log (no temperature staircase), not a fit-tuning problem
metadata:
  type: project
ingested_at: 2026-06-05
---

`extract_tg` returning `status: failed, error: "Bilinear curve_fit failed — check temperature range and data quality"` is most often a **defective Tg-sweep log**, not something fixable by changing `initial_tg_guess` or `equilibration_fraction`. Before re-running the tool, inspect the log's Temp column.

**Diagnostic recipe (no numpy needed on this box — pure-Python parse):**
parse the single `Step ... Temp ... Density` thermo block, histogram Temp by 25 K bins. A valid sweep shows many populated bins spanning glassy→rubbery (e.g. ~100–500 K). A defective one collapses into a single window.

**PE4 incident (2026-06-05):** `tg_sweep.log` contained ONE isothermal NPT run of 100k steps held at ~300 K. Temp histogram: 110 rows in 275–300 K, 99 rows in 300–325 K, and exactly 1 row at 548 K (step 0 — leftover initial-velocity state before the thermostat kicked in). No staircase = no two linear regions = bilinear fit has nothing to fit. The fix is orchestrator-side: regenerate and re-run the Tg sweep with a real T_START→T_END staircase (~500 K → ~100 K, ~25 K steps). Do NOT report a Tg from such a log.

**How to apply:** on a Bilinear-fit failure, parse the Temp column first. If Temp spans < ~100 K total or collapses to one bin, declare the log defective and return overall_verdict=FAIL with a regenerate-the-sweep recommendation — do not retry extract_tg with tweaked params. Note the log also may not echo the input `.in` script (only `unfix npt_tg` appeared), so confirm the sweep from the Temp data itself, not from grepping for fix/ramp keywords.
