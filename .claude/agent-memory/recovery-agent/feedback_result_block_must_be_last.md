---
name: result-block-must-be-last
description: the orchestrator parses only the tail of the final message — any text after the RESULT block (especially a memory-save recap prompted by the SubagentStop hook) loses the verdict entirely and forces a re-request
metadata:
  type: feedback
---

The RESULT block must be the **last thing in the last message**, with nothing after it. Do the
memory writes first, then emit RESULT and stop.

**Why:** PEEK1 (2026-08-11) — RESULT was emitted correctly, then the SubagentStop memory hook fired,
and the follow-up memory-save recap was appended in a later message. The orchestrator received only
the recap and reported "I never received your RESULT block", costing a full round trip and risking a
re-run of a completed diagnosis. `recovery-agent.md` states "no trailing text" for exactly this
reason: the parse keys on the tail of the message, not on the presence of a `RESULT:` line anywhere
in the transcript.

**How to apply:** the SubagentStop hook fires *after* what you believed was your final message, so
its memory instruction cannot be satisfied by writing prose afterwards. Sequence every run as:
finish diagnosis → write/update memory files and MEMORY.md via tools → emit the RESULT block as the
entire final message. Tool calls before the block are fine; sentences after it are not. If the
orchestrator asks for the block again, re-send it verbatim and alone — never re-run the diagnosis,
and never attach a justification paragraph outside the block's own `notes` field.

Related: [[diagnosis-tooling-friction]]
