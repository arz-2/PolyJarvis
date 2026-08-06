---
name: plan-fields-unvalidated
description: run_plan.json free-text fields (criteria_evaluated, uncertainty cross-refs, t_range_brackets_exp_tg) have no schema check — mechanically diff them before reading a reasoned plan's prose
metadata:
  type: feedback
---

**Rule: on every reasoned plan, mechanically diff these three fields before reading any prose.**

Three `run_plan.json` fields carry no schema validation, and the recurring reasoned-plan defect
is the same shape each time: **claimed in prose, absent from the field.**

1. `decisions[].criteria_evaluated` — free strings with no link to
   `decision_policy.json:policies.<p>.evaluate` keys. PVDF1's D-06 listed 4 invented names
   (`steps_per_t_floor`, `rate_span_decades`, …) against a 6-item policy list.
2. Cross-references from `decisions[].evidence` to `uncertainties[].name` — unchecked. PVDF1's
   D-06 justified keeping a narrow rate span because the risk was "recorded as a non-dominant
   uncertainty (`tg_rate_span_slope_gate`)" — that entry did not exist.
3. `planned_stages[tg].success_criteria.t_range_brackets_exp_tg` — typed inconsistently across the
   corpus: numeric for single-member classes (PSU 463, PS 373, PEEK 418, PE 205), `null` where the
   scaffold left it unpinned, bare `true` in reasoned multi-member plans (PVC4, PSU4, PVDF1). Only
   PVC1 pins the member machine-readably, via a companion `exp_tg_K: 354`.
4. `decisions[].id` — never checked against `policies.<p>.decision_id`. PVDF1 ships
   `D-06_tg_ladder` where the policy says `D-06_tg_fit_quality`; a strict id match (what the
   critic procedure literally specifies) finds no policy and would skip enforcement entirely.
   Match on the `D-0N` prefix, then flag the drift as advisory.

**Why:** `_exp_tg_bracket()` in `make_deterministic_plan.py` deliberately returns `None` for a
multi-member class so the planner pins the member; nothing then checks that it did. Same for the
other two fields.

**How to apply:** on every reasoned plan, mechanically diff `criteria_evaluated` against the
policy's `evaluate` list, and grep each uncertainty name cited in `evidence` against
`uncertainties[].name`, before reading the prose. Recommend the PVC1 `exp_tg_K:` companion pattern
for multi-member classes. A schema/CI check over these four would remove the whole finding class.
Validated on PVDF1 (2026-08-05): the same ~20-line diff script found both round-1 blockers and
then confirmed both round-2 fixes as exact set matches — keep it as the first move, before prose.
Related: [[property-method-is-glassy-contradiction]].
