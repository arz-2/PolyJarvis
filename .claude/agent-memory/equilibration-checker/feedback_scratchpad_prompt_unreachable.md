---
name: scratchpad_prompt_unreachable
description: Orchestrator passes eqcheck prompt in scratchpad file path; worker cannot access it (context boundary)
metadata:
  type: feedback
---

**Rule:** Orchestrator must pass equilibration-checker prompt parameters inline or via a data/** file path, not scratchpad.

**Why:** Subagent context boundary restricts access to only guide + rules JSON + data/** + agent-memory; scratchpad is outside that perimeter. Scratchpad was used as a convenience by orchestrator, but it's not in the worker's allowed context.

**How to apply:** When launching equilibration-checker, pass the prompt object or write it to data/<run_name>/raw/prompt.json (or similar repo-tracked location) rather than scratchpad. Alternatively, inject parameters as environment variables or inline them in the subagent message.
