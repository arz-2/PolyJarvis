---
name: tg_k_param_does_not_exist
description: Orchestrator instructed pass --tg_k flag to generate_run_summary, but tool has no such parameter; use tg_path instead for single-rate runs
metadata:
  type: feedback
---

**Rule:** Do not attempt to pass `tg_k` to `generate_run_summary` — it will fail schema validation. The parameter does not exist in the tool.

**Why:** 2026-08-11 cis-PBD1 run: orchestrator gave instruction "Pass `--tg_k 220.2`" for single-rate Tg override, but the actual function signature has no `tg_k` parameter. Advisor confirmed: unknown key fails schema validation. Orchestrator may have written the instruction against a tool version that doesn't exist.

**How to apply:** For single-rate runs, pass `tg_path=/path/to/tg_summary.json` explicitly. The tool reads `Tg_K` from that file. For multirate, pass `tg_path` pointing to the slowest-rate folder. The tool's documented behavior is to always read DSC-equivalent Tg from `tg_multirate_result.json` when it exists; single-rate runs must have `tg_path` provided to avoid trying to read the nonexistent multirate file.
