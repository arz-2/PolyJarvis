---
name: feedback_worker_result_block_omission
description: "Workers substitute a memory-save summary for their RESULT block; orchestrator should derive paths from decks/watch_run rather than re-asking"
metadata:
  type: feedback
---

On cis-PBD1 (2026-08-11) three workers ended their final message with a memory-save note instead of
the RESULT block their guide requires: `literature-grounding-worker`, `planner`, and
`equilibration-worker`. The equilibration worker did it **twice** — the second time after an
explicit request for the block and nothing else.

**Why it matters:** the RESULT block is the handoff contract. Without it the orchestrator has no
`chain_id`, no `monitor_command`, and no downstream paths, and a `SendMessage` round-trip to
re-ask costs a full agent resume (~35 s) and can fail again.

**How to apply:** don't re-ask more than once. Everything in a RESULT block is recoverable from
source, usually more reliably:
- `monitor_command` → call `mcp__mcp-lammps-engine__watch_run(chain_id)` directly from the
  orchestrator; it is the canonical generator and needs no worker.
- stage output paths → `grep -hE "write_data|dump " <stage>/<stage>.in`, which is authoritative
  where a worker's report is secondhand.
- `chain_id` → the chain script and `*_progress.jsonl` in the stage work_dir.

Adding an explicit "FINAL OUTPUT CONTRACT — the RESULT block must be the entire final message; if
you save memories, do that first" line to the spawn prompt did work for every worker it was
applied to afterwards. Worth adding by default. Related:
[[feedback_worker_md_guide_structure_convention]].
