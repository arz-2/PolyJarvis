---
name: property-method-is-glassy-contradiction
description: decision_policy.json property_method has two require clauses that contradict for multi-member classes when tg is requested — do not escalate a plan over it
metadata:
  type: feedback
---

`orchestration/decision_policy.json:policies.property_method.require` contains two clauses that
diverge for a **multi-member class with `tg` in properties**:

- `"is_glassy from measured Tg>300K when tg requested, else from experimental_tg_K glassy_hint"`
- the multi-member clause: `"Drive is_glassy off the pinned exp Tg, never the noisy MD Tg"`

Treat this as a **policy defect, not a plan defect**. Log it as an advisory finding; do NOT
`revise` or `escalate` a plan for picking one clause, provided the plan flags the consequence.

**Why:** hit on PVDF1 (PHAL, multi-member `experimental_tg_K` {PVDF:233, PTFE:160, PCTFE:325},
properties include tg). Pinned exp Tg 233 K ⇒ rubbery at T_workflow 300 K; the class's own notes
say MD overpredicts by 80–120 K (expected MD Tg 310–350 K) ⇒ glassy. The two clauses therefore
select opposite mechanical paths for the same run. The planner followed the measured-Tg clause
and documented the flip risk, which is the defensible reading.

**How to apply:** when reviewing D-07 on any multi-member class (PHAL, PVNL, PACR, POXI) with tg
requested, check only that (a) the member is pinned from the SMILES in D-04 evidence and
`assumptions[]`, and (b) the plan names the regime-flip as an uncertainty and states what happens
to `bm_pressures_atm` if the regime flips (the ladder is passed verbatim to the murnaghan worker
with no runtime re-derivation). Both present ⇒ approve that decision. Related:
[[plan-fields-unvalidated]].
