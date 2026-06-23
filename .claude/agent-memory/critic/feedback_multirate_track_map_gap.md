---
name: multirate-track-map-gap
description: analyze-tg-multirate is missing from decision_policy.json track_map; treat as non-blocking stale-policy artifact, never revise/escalate over it
metadata:
  type: feedback
---

The stage `analyze-tg-multirate` is absent from `decision_policy.json:stage_schema_requirements.track_map` (which lists `analyze-tg` but not the multirate variant). A reasoned thermal plan that includes this stage will appear to "violate" the stage→track mapping check in critic step 3.

**Rule:** Do NOT flag this as a finding. Approve the stage as long as its `track` is `thermal` (a valid track) and the three required fields are present.

**Why:** The slope-gate multirate stage is a CLAUDE.md hard stop — it is *required*, not optional. The gap is in the policy dict, not the plan. There is no planner-side fix (planner cannot edit the policy file, and dropping the stage is wrong), so a `revise` creates a loop that round-2 turns into a spurious UNRESOLVED escalation on a correct plan.

**How to apply:** Any reasoned thermal plan with `analyze-tg-multirate` (track=thermal). Note the omission as an observation in `critique.findings` but keep status=approved. If the policy `track_map` is ever patched to add the stage, this memory is obsolete.
