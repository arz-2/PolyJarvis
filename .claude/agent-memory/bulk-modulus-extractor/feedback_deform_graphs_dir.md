---
name: feedback-deform-graphs-dir
description: extract_bulk_modulus_deform --graphs_dir bug was fixed; as of 2026-06-21 the script accepts --graphs_dir and server.py forwards it correctly
ingested_at: 2026-06-20
updated_at: 2026-06-21
metadata:
  type: feedback
---

**Status: RESOLVED as of 2026-06-21.**

The `extract_bulk_modulus_deform.py` CLI script previously did NOT accept a `--graphs_dir` argument (as of 2026-06-20). This caused silent failure: the sentinel was written as "completed" but no output files were produced.

**Fix confirmed:** As of 2026-06-21, `extract_bulk_modulus_deform.py` defines `--graphs_dir` at argparse line 146, and `server.py` forwards it via `--graphs_dir {graphs_dir}`. The MCP tool `extract_bulk_modulus_deform()` can now be called with `graphs_dir=` safely.

**How to apply:** Pass `graphs_dir=` normally to the MCP tool. After the run reports `completed`, still verify the output files exist on disk (bulk_modulus_deform.json, stress_strain.csv) before reading values — this guards against any future regression.

**If the bug reappears:** Re-run the script directly without `--graphs_dir`:
```bash
conda run -n mol-builder python <MDA_SCRIPTS_DIR>/extract_bulk_modulus_deform.py \
  --log_file <path> --output_dir <path> --strain_rate <rate> \
  --strain_max <max> --strain_start <start> --eq_steps <steps> --avg_window 2000
```
