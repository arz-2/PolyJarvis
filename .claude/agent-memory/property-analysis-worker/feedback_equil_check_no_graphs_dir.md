---
name: equil-check-no-graphs-dir
description: check_equilibration_comprehensive does not accept --graphs_dir flag; omit it from calls
metadata:
  type: feedback
ingested_at: 2026-06-10
---

`check_equilibration_comprehensive` (the MCP tool) rejects the `--graphs_dir` argument with "unrecognized arguments" and fails immediately. The other analysis tools (extract_equilibrated_density, extract_bulk_modulus, etc.) do accept `graphs_dir`.

**Why:** The underlying script `check_equilibration_comprehensive.py` has not been updated to accept `--graphs_dir`. First seen in PE7 run on 2026-06-09.

**How to apply:** When calling `check_equilibration_comprehensive`, do NOT pass `graphs_dir`. Pass only `output_dir`. This is a known discrepancy between the tool interface and what the script supports.
