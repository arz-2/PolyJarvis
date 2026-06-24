---
name: ps-ct-advisory-glassy
description: PS glassy C(t) decay is ADVISORY-only; gate on structural density/thermo/packing instead
metadata:
  type: feedback
---

**C(t) slowness in glassy PS is ADVISORY, not a blocking gate.**

PS3 run (DP40, 300K, PCFF): overall_pass=true despite C(t) only 10% decayed at trajectory end (tau_relax=264 ms vs T_traj=1.95 ns). The comprehensive check passed because the hard-gate set (density drift, energy drift, density plateau SEM, density homogeneity CV, P2 nematic order) all converged cleanly.

**Why:** Glassy PS at 300 K is below Tg (exp Tg≈373 K). In the glassy state, segmental diffusion is severely restricted by the energy landscape. C(t) decay (defined as correlation of Cα end-to-end vector over time) decays on timescales governed by cooperative rearrangements, not thermal diffusion. For DP40 glassy polymer, observing tau_relax >> T_traj is physically realistic and does NOT indicate under-equilibration of the DENSITY.

**How to apply:** For `is_glassy=true` and `ct_min_decay` specified (0.1–0.25):
- If `overall_pass=true` for the STRUCTURAL gates (density/thermo/homogeneity), do NOT escalate to FAIL or EXTEND based solely on C(t) decay fraction <ct_min_decay.
- Do report the C(t) partial decay as an advisory warning in the markdown.
- Set `ct_decay_fraction` and `ct_tau_relax_ps` in output; these are real measurements, just not blocking for glassy systems.

Related: [[C(t)-advisory-for-aromatic-main-chain]]
