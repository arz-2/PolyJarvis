---
name: feedback-cache-write-blind-no-read
description: guides/system_characterization_cache.json is Read/Bash-denied for this agent too -- Write succeeds but is blind, verify prior emptiness from the run_plan's own assumptions note before overwriting
metadata:
  type: feedback
---

`guides/system_characterization_cache.json` -- the exact file this agent's step 6 must write to
every run -- is denied on both `Read` and `Bash` by the per-agent context-boundary hook ("outside
your allowed context: guide + relevant rules JSON + your own data/** workspace + agent-memory").
`Write` to it is NOT denied, so a full-file overwrite goes through with zero visibility into what
was there before.

**Why:** on cis-PBD1 (2026-08-11) this meant writing the cache entry required trusting the
run_plan.json's own `assumptions[]` note ("guides/system_characterization_cache.json is currently
empty ({})", recorded by the planner minutes earlier at plan-generation time) as the only evidence
of the file's prior state, since this agent cannot read it directly to confirm or to preserve
other SMILES' existing entries.

**How to apply:** before writing this file, check the calling run_plan.json's `assumptions[]`/
`critique.findings[]` for a recent statement of the cache's prior content (planner/critic usually
already inspected it). If no such statement exists, treat the file as **unknown, not empty** --
do not `Write` a bare `{"<key>": {...}}`; instead flag to the orchestrator that a read-verified
merge is needed (e.g. via a script on the orchestrator's own allowlist) rather than risking
clobbering other cached SMILES entries. [[feedback_bash_denied_guides_json]] covers the parallel
Read-only-guides case; this is the stricter write-hazard variant for the one file this agent
actually mutates.
