---
name: feedback-d09-edit-anchor-slip
description: Anchoring the D-09_characterization Edit on the bare `"planned_stages": [` string inserts the new decision object OUTSIDE the decisions[] array (after its closing `],`), not inside it — always anchor on the preceding decision's closing `}`/`],` so the insert lands inside decisions[]
metadata:
  type: feedback
---

While patching `run_plan.json` for PMMA_PROBETEST1 (2026-08-06), an `Edit` with
`old_string="  \"planned_stages\": ["` and a `new_string` that prepended the whole D-09 decision
object landed the object **between** the decisions array's closing `],` and the `planned_stages`
key — i.e. outside `decisions[]` entirely, producing structurally invalid intent (still
parseable JSON at the top level, but D-09 wasn't inside the array `jq '.decisions[]'` iterates).
Caught by immediately re-reading the file with line numbers before validating with `jq`.

**Why:** every `refine_from_equil` invocation appends a D-09 entry to `decisions[]`, so this exact
anchor mistake will recur unless the anchor is fixed.

**How to apply:** when appending to `decisions[]`, anchor the `Edit` on the **last existing
decision's closing content**, not the array's own closing bracket or the next top-level key —
e.g. `old_string` should end with the prior decision's `"confidence": "...", \n "alternatives":
[] \n }` and `new_string` should append `,\n{new D-09 object}\n}` before the array's `],`. After
any such Edit, always re-`Read` the surrounding ~10 lines (not just run `jq .` — a misplaced
object can still be valid top-level JSON) to confirm the new object is nested inside `decisions[]`
before moving on, e.g. `jq '.decisions[] | .id'` should list `D-09_characterization` alongside
D-01..D-04/D-07.
