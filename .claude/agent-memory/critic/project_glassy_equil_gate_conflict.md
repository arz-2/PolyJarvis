---
name: glassy-equil-gate-conflict
description: Glassy DP>=30 equil gate — resolved 2026-06-20 by require_glassy in decision_policy.json; plans whose glassy criteria match require_glassy are APPROVED, not escalated
ingested_at: 2026-06-20
metadata:
  type: project
---

Glassy high-MW polymer plans (regime=glassy & DP>=30) hit a conflict at the equilibration gate that is now RESOLVED in policy.

**History (round-1 escalate, PVC1 2026-06-20):** `policies.equilibration.require` was once an absolute "check_equilibration_comprehensive overall_pass=True before ANY property extraction" with NO glassy carve-out. For glassy DP>=30, overall_pass embeds a melt-NVT C(t) full-decay sub-check whose tau_relax (~3.6e9 ps for DP=60) is physically unattainable. A planner revision demoting overall_pass to advisory was scientifically sound but overrode a FIXED require, so the Critic escalated (could neither approve an override of fixed policy nor revise an identical plan back).

**Resolution (out-of-band, user-authorized 2026-06-20):** `decision_policy.json:policies.equilibration` now has a `require_glassy` field. The `require` clause reads "...EXCEPT glassy DP>=30 systems, which use require_glassy." `require_glassy` gates on: density plateau in experimental range AND density homogeneity CV<0.25 AND P2 nematic<0.10 AND energy drift/SEM within bounds; the four melt chain-self-diffusion metrics (C(t) decay, MSD diffusivity, MSID slope, Rg chain-chain CV) are ADVISORY, and overall_pass may be False on them without blocking property extraction. `rationale_glassy` documents the tau_relax infeasibility.

**How to apply (current rule):** When a reasoned plan for regime=glassy & DP>=30 demotes overall_pass to advisory AND its equil/equil-check success_criteria match require_glassy verbatim (four structural gates + four advisory diffusion metrics, rubbery path unchanged), the verdict is APPROVE — the framework now sanctions the demotion; it is no longer a Critic waiver. Verify regime via experimental_tg_K>300 (or measured Tg>300) and DP>=30. If a glassy plan demotes a gate that is NOT covered by require_glassy (e.g. demotes density homogeneity, or P2), that is still a finding. Determining glassy: PE1, PMMA1, PLA1 are the other glassy revision polymers expected to hit this path — approve them on the same basis. See [[born-method-implementation]] for the glassy K_T path that consumes the accepted npt_prod300 data.
