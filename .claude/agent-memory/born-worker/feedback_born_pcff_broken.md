---
name: born-pcff-broken
description: Born+NVT is broken for PCFF+PPPM — K_Born 8-15x too high, Var(P) ~10^7x too high. Never submit Born for PCFF/OPLS/PPPM classes.
metadata:
  type: feedback
---

Born+NVT has been removed from the PolyJarvis pipeline as of 2026-06-21. Never spawn born-worker for a standard pipeline run.

**Why:** PCFF cross-term virial (bond-angle, angle-angle, torsion cross-terms) and PPPM kspace contributions inflate:
- K_Born: 8–15× too high (PVC1: 31.6 GPa vs exp ~4 GPa; PEEK1: 84.3 GPa vs exp ~4 GPa)
- Var(P): ~10⁷× too high (PVC1: 401,627 atm², expected ~0.035 atm² for K≈4 GPa)
- Result: K_T = K_Born + NkT/V − (V/kT)·Var(P) gives K_T ≪ 0 regardless of run length

Failed 3/3 in-pipeline runs: PMMA4 (0.5 ns, K_T=−21.9 GPa), PVC1 (0.5 ns, K_T=−14.0 GPa), PEEK1 (4 ns, K_T=−49.6 GPa). Longer runs made results worse.

Schnell (2011, EPJ E) confirms the method needs 60,000+ independent configurations for simple pair potentials. PCFF adds virial incompatibility on top — not fixable at any practical run length.

**How to apply:** If born-worker is explicitly requested by the user for a diagnostic run, proceed but expect K_T < 0 for PCFF. Do NOT retry with different eq_fraction or born_run_ns. Do NOT route back to born-worker from the orchestrator — the standard glassy path is Murnaghan NPT compression at 300 K. See [[murnaghan-glassy-primary]] (decision_policy.json D-07).
