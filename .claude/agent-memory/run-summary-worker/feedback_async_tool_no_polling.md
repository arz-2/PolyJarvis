---
name: async-tool-no-polling
description: run-summary-worker calls async generate_run_summary but has no get_run_status tool to poll; resolved via Read() of canonical path
metadata:
  type: feedback
---

**Rule:** When calling async MCP tools from a worker, ensure the worker has corresponding polling/status-check tools in its toolset, or document the fallback strategy.

**Why:** The `generate_run_summary` tool returns `status: "submitted"` with a `run_id`, implying the caller should poll. However, the run-summary-worker has no `get_run_status(run_id)` tool available. In this pilot test, the job completed fast enough that a `Read()` of the canonical output path worked as a discriminator, but this is fragile: if the job were slower, we'd have no way to block-wait or distinguish "job running" from "job failed, output not written".

**How to apply:** When designing worker toolsets for async MCP calls:
- Either expose the polling tool alongside the async tool (preferred), or
- Document an explicit fallback (e.g., "attempt Read() of canonical path N times with backoff"), or
- Make the tool sync-only for worker-scope calls (if the orchestrator can absorb latency).

For this specific case, the hook-boundary pilot succeeded — the async call didn't get blocked by PreToolUse — but the toolset gap remains a refinement for production runs.
