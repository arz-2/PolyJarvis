---
name: feedback_run_summary_born_gap
description: generate_run_summary does not pick up bulk_modulus_born.json; only reads bulk_modulus.json (fluctuation method)
metadata:
  type: feedback
---

`generate_run_summary` reads `bulk_modulus.json` for the reported K value. It does NOT read `bulk_modulus_born.json` or `bulk_modulus_murnaghan.json`. When only Born analysis is run (no extract_bulk_modulus call), the summary reports bulk_modulus as "no exp ref" with null values.

**Why:** The generate_run_summary.py script looks for specific filenames. Born and Murnaghan results are in separate files that are not currently wired into the summary aggregator.

**How to apply:** After Born or Murnaghan analysis, verify run_summary.json bulk_modulus section manually. The RESULT block should report the actual Born K from bulk_modulus_born.json, not rely on run_summary.json's bulk_modulus field. Note this discrepancy explicitly in the notes field of the RESULT block. The orchestrator should be aware the summary PASS/FAIL for K is unreliable when using Born/Murnaghan paths.
