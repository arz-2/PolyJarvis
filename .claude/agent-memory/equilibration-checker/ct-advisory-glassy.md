---
name: ct-advisory-glassy
description: C(t) partial decay is expected & advisory for aromatic main-chain glassy polymers (PS, etc.)
metadata:
  type: feedback
---

Aromatic main-chain polymers (e.g. polystyrene, polyaromatics) show incomplete C(t) autocorrelation decay within typical MD timescales due to slow segmental relaxation from aromatic ring constraints.

**Why:** Phenyl ring pendant groups (aromatic) experience higher rotational barriers than alkyl groups. The effective τ_relax >> simulation window. This is not a simulation failure — it is expected chemistry.

**How to apply:** For `is_glassy=true` + aromatic pendant or main-chain atoms:
- C(t) decay_fraction <100% is advisory only (report but do not block PASS)
- Gate PASS/FAIL on thermo (density/energy drift + SEM) and spatial (P2, density homogeneity) checks only
- Report C(t) partial decay as warning in equilibration result, do not set equil_verdict=EXTEND or FAIL on this gate alone
- MSID slope deviation (non-Gaussian behavior) is also advisory for aromatic polymers
