---
name: glassy-B0prime-inflation-narrow-span
description: Glassy polymers (PVC, PEEK) give inflated B0' (~16) at ±1000 atm 5-pt Murnaghan; widen to ±3000 atm to resolve curvature; K value may still be sound
metadata:
  type: feedback
---

Narrow ±1000 atm Murnaghan series on stiff glassy polymers systematically inflates B0' to ~16 (PCFF/PKTN PEEK4: B0'=16.16; PCFF/PVNL PVC: B0'=16.3 before widening to 9.53). This also slightly degrades r² (PEEK4: 0.9981 < 0.999 threshold).

**Why:** The ±0.1 GPa pressure span is too narrow to constrain the EOS curvature (B0') independently from B0. Glassy polymers have high B0 (~5 GPa) and the volume response to ±1000 atm is only ~2%, within noise for a typical NPT run length.

**How to apply:** When B0' > 12 AND r² < 0.999 from a ±1000 atm series on a glassy polymer, flag as BORDERLINE and recommend widening to ±3000 atm (5-pt: [-3000,-1000,0,1000,3000] or 7-pt symmetric). K value is likely still directionally correct (within exp range) but B0' is unreliable. Do NOT widen to include large tensions (< -1000 atm for PVNL) to avoid cavitation — see [[pvc-murnaghan-tension-cavitation]].

Runs affected: data/PEEK4, data/PVC3/PVC4 (PVC widened to [-1000,+5000] compression-biased).
