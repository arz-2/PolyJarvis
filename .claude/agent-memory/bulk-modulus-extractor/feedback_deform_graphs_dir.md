---
name: feedback-deform-graphs-dir
description: extract_bulk_modulus_deform analysis script does not accept --graphs_dir; MCP tool silently fails with completed sentinel when script exits non-zero
ingested_at: 2026-06-20
metadata:
  type: feedback
---

The `extract_bulk_modulus_deform.py` CLI script does NOT accept a `--graphs_dir` argument (as of 2026-06-20). When `graphs_dir` is passed to the MCP tool `extract_bulk_modulus_deform()`, the server passes `--graphs_dir <path>` to the script, which exits with code 2 (unrecognized argument). The background thread catches a zero-result and the sentinel is still written as "completed", but no JSON or CSV output files are produced.

**Why:** The deform analysis script was written before the `--graphs_dir` convention was standardized across all analysis scripts. The MCP tool wrapper passes it but the script ignores/rejects it.

**How to apply:** When the MCP tool call returns "completed" sentinel but `bulk_modulus_deform.json` is missing from output_dir, re-run the underlying script directly without `--graphs_dir`:

```bash
conda run -n mol-builder python <MDA_SCRIPTS_DIR>/extract_bulk_modulus_deform.py \
  --log_file <path> --output_dir <path> --strain_rate <rate> \
  --strain_max <max> --strain_start <start> --eq_steps <steps> --avg_window 2000
```

The output files (bulk_modulus_deform.json, stress_strain.csv) are then written correctly to output_dir.
