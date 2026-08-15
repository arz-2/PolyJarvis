---
name: emc-wait-and-scope-friction
description: EMC builds can exceed the 600s Bash timeout — poll get_emc_job_status instead of a foreground until-loop; MCP server source is outside Bash scope
metadata:
  type: feedback
---

Do not block on EMC artifacts with a foreground `until [ -f ... ]; do sleep N; done` Bash call,
and do not try to read the MCP server source to resolve a spec question.

**Why:** Two frictions hit on the PSU1/PSFO build.
1. The guide's `until [ -f <output_dir>/emc_build.data ]; do sleep 5; done` snippet ran past the
   600 s Bash ceiling and was force-backgrounded. That build (PSFO, dp=25, nchains=20,
   27,040 atoms) took ~10 min wall. Anything of that size or larger will blow the timeout.
   `get_emc_job_status(job_id)` returned `completed` promptly and is the reliable signal;
   it has no progress fraction but does flip status.
2. `grep`/`find` under `/home/arz2/PolyJarvis/mcp-servers/mcp-emc-server/` is denied — Bash scope
   is `data/**` plus allowlisted scripts only. Tool behavior questions must be settled from the
   guide and the tool's own returned fields, not from source.

**How to apply:** After `submit_emc_cell_job`, poll `get_emc_job_status` across turns; if you
also want a file waiter, launch it with `run_in_background: true` and end the turn. Never spend
turns trying to inspect server internals — for the seed question the answer came from the
returned `resolved_seed` field instead (see [[emc-seed-null-conflict]]).

Related: [[output-contract-footguns]]
