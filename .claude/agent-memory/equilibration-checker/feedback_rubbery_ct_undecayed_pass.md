---
name: rubbery_ct_undecayed_pass
description: C(t) tau_relax >> trajectory length still passes rubbery gate when binding gates (density, energy, n_eff, homogeneity, finite-size) are sound
metadata:
  type: feedback
---

**Rule:** C(t) decayed <5% in trajectory, tau_relax >> T_traj → comprehensive check reports overall_pass=false and warnings. For rubbery polymer (phase=full), enforce_equilibration_gate correctly returns PASS if binding gates pass.

**Why:** Rubbery regime carve-out (require_rubbery) marks C(t) and MSD as advisory, not binding. A short trajectory (1951 ps vs tau_relax 1917264.7 ps) is a physical statement that reptation timescale vastly exceeds observation window, not a convergence failure. This is expected for flexible ether-backbone polymers at low T (300K, Tg 206K, well in glassy storage regime).

**How to apply:** When comprehensive check shows overall_pass=false due to C(t) but you're on rubbery regime:
- Do NOT short-circuit to EXTEND/FAIL based on overall_pass or warnings alone
- Call enforce_equilibration_gate and use its verdict field (PASS/EXTEND/STRUCTURAL_FAIL/FAIL) directly
- Report the C(t)/MSD warnings in equilibration_warnings as-is (they are still informative)
- If all binding gates pass and gate returns PASS, accept it
