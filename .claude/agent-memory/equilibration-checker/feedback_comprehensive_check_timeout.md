---
name: comprehensive_check_timeout_large_dump
description: check_equilibration_comprehensive hung for 30+ minutes on 312 MB dump; tool produced no JSON output; MCP server unresponsive
metadata:
  type: feedback
---

**Incident:** PLA1 phase=melt checkpoint. Two job submissions (a5e507ed, 4ec7fff7) both exceeded 30 minutes with zero output. The 312 MB nvt_production.dump (1150 frames × 4520 atoms) was provided; npt_production.log was complete and valid.

**Symptoms:**
- Tool returned "submitted" with run_id but no subsequent JSON at `output_dir/equilibration_comprehensive.json`
- No progress in `output_dir/graphs/` or any output file
- Monitor timeout (600s) on file existence → second job → monitor timeout again → process hung
- MCP lammps-engine server remained alive (PID 3306946 running)

**Root:** Unknown — either the server queued the request and never processed it, or hung during dump parse. The advisor noted that dump work at 312 MB can legitimately take "several minutes" but 30+ min is "at the edge," suggesting a hang rather than slow completion.

**How to apply:** 
- Before resubmitting on large dumps, consider `skip_frames` parameter to thin the trajectory (but verify what it actually does in the engine's dump-parse code first — don't assume)
- If timeout recurs with skip_frames, escalate to check the MCP server logs (`/home/arz2/PolyJarvis/mcp-servers/.venv/bin/python` process stderr)
- The corrected `backbone_types=[2,3,7]` was ready for the second attempt, so re-launch with that once the server is verified live
