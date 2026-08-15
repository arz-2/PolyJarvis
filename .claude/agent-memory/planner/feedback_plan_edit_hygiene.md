---
name: plan-edit-hygiene
description: Two self-inflicted errors when revising run_plan.json and planner memory — trailing comma after deleting a JSON array element, and a duplicate memory file written before reading MEMORY.md
metadata:
  type: feedback
---

Revising the scaffold `run_plan.json` with `Edit`, deleting the last element of an `alternatives` array left a **trailing comma** — `validate_run_plan.py` crashed with a raw `JSONDecodeError` traceback (exit 5) and `jq` failed, at a point where the plan had already passed validation once.

**Why:** `Edit` is textual and knows nothing about JSON syntax; a plan that validated cleanly earlier gives false confidence that later edits are safe. A structurally broken plan handed to the Critic wastes a whole round.

**How to apply:**
- After ANY `Edit` that removes a JSON array/object element, re-run `validate_run_plan.py` (it parses first, so a syntax break surfaces immediately). Never skip the final validate just because an earlier one was clean.
- Prefer *rewriting* the offending element (e.g. narrow its wording) over deleting it when the deletion is only for consistency — no comma risk.
- `validate_run_plan.py` checks stage `success_criteria` by EXACT key name and the names are documented nowhere: `t_range_brackets_exp_tg: true` demands a companion key spelled exactly `exp_tg_K` (an `exp_tg_bracketed_K` earned an advisory `exp_tg_companion` finding on PLA1, 2026-08-14). Run the validator after authoring stage criteria and let its findings name the key rather than inventing a descriptive one.
- Related self-inflicted error: wrote a new memory file for scope-denial friction that duplicated the existing [[planner-scope-denials]], because `MEMORY.md` was only read afterwards. **Read `MEMORY.md` before writing any new memory file** — a concurrent/earlier session may already have indexed the same lesson; update that file instead.
