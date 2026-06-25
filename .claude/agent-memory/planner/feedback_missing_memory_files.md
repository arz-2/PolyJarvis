---
name: feedback-missing-memory-files
description: Planner MEMORY.md index pointed at memory files that did not exist on disk — index/file desync friction
metadata:
  type: feedback
---

On the PS4 run (2026-06-24) the planner `MEMORY.md` index listed `pstr_reasoned_plan.md` and `multimember_class_exp_tg_resolution.md`, but NEITHER file existed in `.claude/agent-memory/planner/` — only `MEMORY.md` was present.

**Why:** likely a partial checkout / integration where MEMORY.md (the index) landed but the referenced memory bodies did not, or the bodies were removed without updating the index. The index is checked into version control and shared across the two revision machines, so a desync is plausible after `scripts/integrate.py`.

**How to apply:** before relying on a memory that MEMORY.md points to, confirm the target file actually exists (a `[[link]]` or index line is a claim, not a guarantee). If it is missing, recreate it from the run at hand rather than assuming the lesson is lost. When adding an index line, write the body file in the same turn so the index never points at a phantom. Re-created `pstr_reasoned_plan.md` from the PS4 run; `multimember_class_exp_tg_resolution.md` is still missing and may need recreation on a future multi-member-class run.
