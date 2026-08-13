---
name: mcp-async-job-opacity
description: MCP async job polling is opaque; returned "Poll with get_run_status(run_id)" but tool unavailable to agent — had to use filesystem monitoring instead
metadata:
  type: feedback
---

**Rule:** When MCP tools submit async jobs, don't rely on the returned poll hint — it names a tool not available in the agent's namespace. Instead, monitor the output directory directly for the result file.

**Why:** During PEEK1 equilibration check, the mcp tool returned run_id=9fa3294c with instruction "Poll with get_run_status(run_id)". No such tool was accessible in my environment. The job ran successfully in the background (PID 2506263), consuming 3+ minutes processing a 1.2 GB dump file, but I had no way to poll its status without fallback to filesystem checks and process inspection.

**How to apply:** After submitting an async MCP job, immediately start monitoring `output_dir` for the expected result file (e.g., `equilibration_comprehensive.json`) rather than relying on a polling-hint tool. Use `until ! ps -p <pid> > /dev/null` + background waits to avoid blocking on long-running analyses.
