---
name: peg3-recheck-success
description: PEG3 recheck after +2 ns NPT extension resolved energy drift (1.01% → 0.48%), all hard gates passing
metadata:
  type: feedback
---

**Energy drift is the primary equilibration gate for rubbery systems; mild extension resolves marginal failures.**

Why: PEG3 (DP=100, POXI, 300 K) initially failed on energy drift 1.0125% (marginal by <0.02 percentage points). A +2 ns NPT extension reduced energy drift to 0.4766% (p=0.0572), and all thermo/density/structural hard gates pass. Density block-SEM 0.0579%, homogeneity CV 21.2%, Rg CV 20.4% — all healthy. The C(t) stall (τ_relax 481 billion ps, 1% decay) and MSD kinetic trap (α=0.026) are regime-consistent for rubbery polymers and remain advisory-only, never blocking the verdict.

How to apply: For rubbery systems at T>Tg, when energy drift is marginal (0.95–1.05%), a +1–2 ns NPT extension is sufficient to resolve it. C(t) and MSD gates do not block rubbery verdicts. Always check the improved log after extension before declaring FAIL.
