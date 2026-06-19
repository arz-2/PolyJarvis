---
name: reasoned-override-keeps-confidence-high
description: A confidence=high class can still require a REASONED plan when the task hands a corrected/non-standard protocol; the override flips plan_mode, not the class confidence field
metadata:
  type: feedback
---

When the orchestrator/user hands an explicit corrected-protocol override for a `confidence=high` class (e.g. PE/PHYC density re-run), produce a **reasoned** plan, not a verbatim deterministic transcription.

**Why:** The confidence_gate keys plan DEPTH off class confidence, but an override means the validated defaults are knowingly being deviated from for one stage — that deviation needs evidence fields, alternatives (with the rejected default's known error), and a critic round. Transcribing verbatim would silently drop the correction.

**How to apply:**
- Still run `make_deterministic_plan.py` to get the scaffold, then revise: `plan_mode: "reasoned"`, `critique: {status: "proposed", rounds: 0, findings: []}`.
- Keep the RESULT `confidence:` field as the class's actual confidence (high) — the override changes plan_mode, not the class's validation status. Note the key judgement call in `notes`.
- SKIP `estimate_tg_group_contribution.py` — that is off-table/confidence=low only. On-table high classes already have class-specific temperatures.
- Verify EVERY override key is actually threaded downstream (grep gen_prompt.py + the workflow tool) before encoding — do not write dead keys. See [[phyc-cooling-rate-gap]].
- Record seeds in decided_params for the orchestrator, but note gen_prompt.py does NOT consume them (it has zero seed handling); orchestrator threads seeds per cross-track rule 2.
