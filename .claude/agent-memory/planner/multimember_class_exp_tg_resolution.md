---
name: multimember-class-exp-tg-resolution
description: Disambiguating the exp Tg/density/K target by SMILES substituent when a polymer_rules class covers multiple named members (PVNL, PACR, POXI, etc.)
metadata:
  type: feedback
---

Several polymer_rules classes are **buckets of multiple named polymers** with DIFFERENT experimental targets stored together in one class entry. The orchestrator passes only the class id + SMILES, so the planner MUST resolve which member the SMILES is and pin that member's exp target — otherwise is_glassy routing and run-summary grading use the wrong number.

**Why:** `experimental_tg_K` (and the density/K notes) in a multi-member class entry is an OBJECT keyed by member name, not a single value. e.g. PVNL: `{PVA:303, PVC:354, PVAc:304}`. If you don't disambiguate, downstream code can't pick — and is_glassy (Tg vs 300 K) can flip wrong (PVA 303 is borderline-rubbery-ish; PVC 354 is clearly glassy).

**How to apply:**
- Read the class `examples`, `experimental_tg_K`, and density/K notes; match the SMILES substituent to the member.
  - PVNL: `*CC(Cl)*`=PVC, `*CC(O)*`=PVA, `*CC(OC(C)=O)*`=PVAc.
- Pin the resolved member's Tg/density/K in the D-04 evidence (`value_K`) AND in `assumptions[]`, so is_glassy and grading are unambiguous.
- Drive **is_glassy off the pinned exp Tg**, never the artefactual MD Tg (a noisy fast-rate fit can wrongly flip the mechanical regime).

Applies to any class whose `experimental_tg_K` is a dict rather than a scalar. See [[pvnl-reasoned-plan]].
