---
name: feedback-result-block-no-prose-lead
description: RESULT block must be the entire final message with zero leading prose, even a one-line status sentence — orchestrator parses it verbatim
metadata:
  type: feedback
---

Ending a turn with a one-sentence status recap before the `RESULT:` block (e.g. "Run completed
cleanly — no errors...") breaks the orchestrator's parser. It has nothing to thread downstream
and has to send a correction message asking for the RESULT block only.

**Why:** The guide already states "The `RESULT:` block must be the entire final message — no
leading sentence, no prose recap — for all phases; the orchestrator parses it verbatim." This was
violated even in a fully clean, no-error run, on the assumption that a short status line was
harmless.

**How to apply:** When phase=full/melt/cooldown work finishes (or fails), the final assistant
message must START with `RESULT:` — nothing before it, not even "done" or "clean run, no issues."
Any commentary belongs in memory notes or is simply omitted. Do not confuse this with routine
per-step status sentences allowed earlier in the turn (per the agent system prompt) — those are
fine mid-task; only the final message is constrained to just the RESULT block.

**Repeat violation (2026-08-11, cis-PBD1):** this memory was already loaded in context and was
still violated in a worse form — after finishing the memory-save step post-submission, the turn
ended with only a memory-save confirmation sentence and the `RESULT:` block was omitted entirely
(not just preceded by prose). The coordinator had to send a correction message and re-supply
`watch_run` output context before work could continue. Root cause: treating "save memory" as the
task's last step and stopping there, instead of treating the `RESULT:` block as the mandatory
final action that must follow *any* other end-of-turn work, including memory saves. Fix: after
saving memory, always emit the `RESULT:` block as the true last message of the turn — memory
saves are never the last action.
