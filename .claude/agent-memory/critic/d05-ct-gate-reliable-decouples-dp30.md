---
name: d05-ct-gate-reliable-decouples-dp30
description: D-05 require_glassy DP>=30 carve-out reads as blocking a DP<30 rigid-aromatic plan, but ct_gate_reliable=false already makes melt-diffusion advisory independent of DP — do not false-flag overall_pass=true on a DP<30 aromatic
metadata:
  type: feedback
---

When critiquing a reasoned D-05_convergence on a rigid AROMATIC class (e.g. PSFO/PKTN/PIMD/PCBN) with DP < 30 that sets the equil success_criterion to standard `check_equilibration_comprehensive.overall_pass=true`, do NOT raise a finding that the require_glassy melt-diffusion exemption is unavailable (DP<30) and the gate is therefore unsatisfiable.

**Why:** `decision_policy.json:policies.equilibration.require_glassy` is gated on "glassy AND DP>=30", which reads as if a DP=25 stiff-aromatic melt — which can never reach melt self-diffusion — would hard-gate on MSD/Rg/C(t) and loop EXTEND forever (the PVC1 failure mode). But the gating is actually DECOUPLED from that policy clause at the tool level:
- `check_equilibration_comprehensive` (mcp-lammps-engine/server.py ~2359) takes NO is_glassy/dp/require_glassy param. Its HARD gates are A density-drift, B energy-drift, C density block-SEM, D energy block-SEM, **E Rg CV across chains <30%**, F P2 nematic <0.10, G density homogeneity CV <25% — all structural/packing, achievable with the class's anneal schedule. The melt-diffusion metrics (C(t), MSD kinetic-trap, MSID slope, C-inf) are SOFT/advisory by default and only become hard gate H when `ct_min_decay` is explicitly supplied.
- For a class with `ct_gate_reliable:false` (PSFO has it; aromatic main chain → C(t)/C-inf undefined via atom-type backbone), `gen_prompt.py:669` sets `ct_min_decay = None`, so C(t) is never armed — INDEPENDENT of DP. The require_glassy DP>=30 carve-out is about arming `ct_min_decay`; for these classes that arming is already suppressed by the class flag.

So `overall_pass=true` IS satisfiable for a DP<30 rigid-aromatic cell. The standard gate keys only on density/energy/Rg-CV/P2/homogeneity, all reachable.

**How to apply:** For an aromatic class, check `jq '.classes.<CLASS>.ct_gate_reliable'` — if false, the melt-diffusion metrics are advisory regardless of DP, and a standard `overall_pass=true` equil criterion is fine. The DP>=30 require_glassy clause only bites when a class would otherwise arm ct_min_decay (ct_gate_reliable true/absent) AND is glassy DP<30 — there the melt metrics WOULD hard-gate and you should flag it. A planner D-05 whose prose muddles "require_glassy gate ... DP>=30? no -> use standard overall_pass with advisory melt-diffusion" is awkwardly worded but lands correct — note it advisory, do not bounce. See [[hardware-require-mpi4-stale-clause]] for the analogous "policy clause reads as contradicting tool behavior" pattern.

**Codebase friction (for /ingest-memory):** decision_policy.json require_glassy DP>=30 clause and gen_prompt comment (line 692/714 "DP>=30 required for require_glassy carve-out") should note that ct_gate_reliable=false ALSO suppresses melt-diffusion arming independent of DP, so the two paths aren't conflated when reading a DP<30 aromatic plan.
