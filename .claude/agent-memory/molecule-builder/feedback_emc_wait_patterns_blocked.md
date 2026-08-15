---
name: emc-wait-patterns-blocked
description: How to wait for an EMC build — arm a run_in_background until-loop on emc_build.data and end the turn; chained `sleep N; ls` is hard-blocked and foreground until-loops blow the 600 s cap
metadata:
  type: feedback
---

To wait on an EMC cell build, launch the artifact wait with `run_in_background: true`:
`until [ -f <output_dir>/emc_build.data ]; do sleep 15; done`, then end the turn. The
completion notification re-invokes you exactly once; from there call
`get_emc_job_status` -> `get_emc_job_output`.

Two patterns fail:

- `sleep 240; ls ...` — hard-blocked by the Bash guard ("Do not chain shorter sleeps to
  work around this block").
- A **foreground** until-loop — blows the 600 s Bash cap and is shunted to background
  anyway. A 32-chain PSFO build (dp=25, 43k atoms) took ~17 min; a 27k-atom build already
  exceeded the cap once.

Never `Read` the background task's `/tmp/claude-.../tasks/<id>.output` file — it is outside
this worker's read scope (guide + rules JSON + `data/**` + agent-memory) and the Read is
denied. The notification plus a status poll carries everything needed; `ls` the artifact if
a direct check is wanted.

**How to apply:** On every EMC submit, poll `get_emc_job_status` once, then arm the
background waiter and end the turn. Do not sit in a foreground loop.

Related: [[emc-wait-and-scope-friction]], [[output-contract-footguns]]
