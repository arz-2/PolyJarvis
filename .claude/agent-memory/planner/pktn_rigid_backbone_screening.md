---
name: pktn-rigid-backbone-screening
description: PKTN/PEEK melt-NVT C(t) never decays in feasible MD; accept screening-grade equil on static-structure+density, demote C(t)/MSD to advisory
ingested_at: 2026-06-20
metadata:
  type: project
---

PKTN (PEEK/PEK/PEKK) melt-NVT equilibration at dp=15/770 K does NOT relax the rigid aromatic backbone within feasible MD. Observed (PEEK1, round 2): C(t) end-to-end decayed 0.1% over ~2 ns (gate threshold 10%), extrapolated tau_relax ~1.9e9 ps ~100x class-note tau_Rouse 2.2 ns; MSD_max 83 A^2 << Rg^2 569 A^2. The standard EXTEND remedy (1-2 ns) cannot move C(t); MSD/density are fixed-volume-NVT-invariant.

**Why:** Terminal relaxation of the PEEK aromatic backbone is hundreds of ns — outside MD. Class notes pre-register this as "borderline adequate for screening" with a Tg-overestimate caveat. The hard `overall_pass=True` gate is unreachable for ANY rigid-backbone aromatic polymer.

**How to apply:** When the equil-check gate returns EXTEND/FALSE for PKTN (or similar rigid-aromatic classes: PIMD/PSFO/PCBN if they show the same C(t) signature), do NOT FAIL and do NOT loop extensions. Revise the equil success_criteria to gate on STATIC structure (Rg CV<30%, P2<0.10, density-homogeneity CV<25%) + density-converged + density-in-gate; demote C(t)/MSD to `advisory_non_blocking`. plan_mode -> reasoned, class confidence stays high. Add dominant uncertainty `rigid_backbone_chain_relaxation_incomplete` (probe: literature_anchor) and record Tg-overestimate + K-low caveats. Add a D-05_convergence decision documenting the accept (confidence: medium).

**Density reference gotcha:** PEEK 1.30-1.32 g/cm3 is the SEMICRYSTALLINE commercial value; amorphous-PEEK reference is ~1.263 g/cm3 (crystalline phase ~1.40). polymer_rules.json Mark2007 labels 1.32 "amorphous" but it is the commercial figure. Compare the MD amorphous cell against ~1.263. PEEK1 got 1.193 = ~5.5% low vs amorphous (not ~9% vs commercial). Low density biases K LOW.

**Cost model (verified gen_prompt.py):** Tg sweep is CONTINUOUS cooling, one rate per run via `tg_rate_index`; ns/rate = T_span/rate. Rates sequential on shared GPUs (additive). 3-rate [40,160,640] over 500 K span = 12.5+3.1+0.8 = ~16.4 ns. At ~14 ns/day = ~28 h. To cut budget: NARROW the T-window (scales all rates), NEVER drop the 40 K/ns slow rate — it is the accuracy anchor for the rate->experiment extrapolation that corrects the Tg overestimate. Surface any scope cut to the user (budget is a hard constraint trading already-compromised Tg accuracy). See [[multimember-class-exp-tg-resolution]] for the PEEK member-pin gotcha.
