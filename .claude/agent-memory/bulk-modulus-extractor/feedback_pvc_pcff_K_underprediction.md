---
name: pvc-pcff-k-underprediction
description: PVNL/PCFF PVC Murnaghan bulk modulus consistently underpredicts experiment by ~17-20%; B0' ~9-10 (well-behaved).
metadata:
  type: feedback
---

PVNL/PCFF PVC bulk modulus from Murnaghan EOS consistently underpredicts experiment by ~17–20%:
- PVC3: K = 2.80 GPa, exp [3.5, 4.5] → −20% vs lower bound
- PVC4: K = 2.90 GPa, exp [3.5, 4.5] → −17% vs lower bound
- B0' in both cases: ~9.5–10.3 (well within accepted [4,20] window → ACCEPT verdict, not WARNING)

**Why:** PCFF partial charges and LJ parameters for C-Cl bonds underestimate the repulsive wall stiffness in PVC. Known Class II FF limitation for halogenated vinyls. See also [[ps-pcff-tg-slopegate-fail]] for PCFF limitations in PSTR.

**How to apply:** When exp_K_range=[3.5, 4.5] for PVC and Murnaghan K lands ~2.8–3.0 GPa, status=WARNING (outside exp range) is correct and expected — do NOT escalate to deform fallback unless fit_converged=False or B0' is outside [4,20]. Note the known underprediction in the RESULT block notes.

Compression-biased pressure span [-1000, 0, 1500, 3000, 5000] atm reliably avoids cavitation (see [[pvc-murnaghan-tension-cavitation]]) and gives clean EOS fits (r²>0.999).
