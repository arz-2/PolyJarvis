---
name: pvnl-reasoned-plan
description: How to build a PVNL (polyvinyls, esp. PVC *CC(Cl)*) reasoned run_plan — medium confidence, in-table temps, PCFF/EMC, glassy K, Tg-ladder slope-gate fix
metadata:
  type: feedback
  ingested_at: 2026-06-25
---

PVNL is confidence=medium and IS in polymer_rules.json with class-specific temperatures (T_equil=530, anneal=610, 7 cycles, Tg sweep 150-550 K @ 20 K, default rates [25,50,100]). Build a **reasoned** plan (not deterministic) — medium confidence forces it; the Critic escalates a deterministic plan on a non-high class.

**Disambiguating the PVNL member by SMILES:** `*CC(Cl)*`=PVC (Tg 354, density 1.38, K_T 3.5-4.5 GPa); `*CC(O)*`=PVA (Tg 303, density 1.26); `*CC(OC(C)=O)*`=PVAc (Tg 304, density 1.19). polymer_rules `experimental_tg_K` and `density notes` carry all three — pick the one matching the substituent and pin it in D-04 evidence + assumptions so is_glassy and grading use the right target.

**How to apply (PVC specifically):**
- **Skip** `estimate_tg_group_contribution.py` — only for off-table/confidence=low. PVNL temps are class-specific; leave the scaffold global_defaults unchanged.
- **D-01 FF = pcff** (EMC). OPLS-AA is NOT an available alternative — EMC build FAILED for PVC and PVAc on OPLS-AA. GAFF2_mod retired. Cite 10.1007/s10118-019-2249-5.
- **D-03 = pppm REQUIRED** — chloride puts significant partial charges on backbone carbons. confidence=high on this decision.
- **D-07 = glassy** — PVC Tg 354 > 300 ⇒ glassy at 300 K. Murnaghan compression primary with **compression-biased pressures [-1000,0,1500,3000,5000] atm** (the -3000 atm tension cavitates the glassy cell AND inflates B0'; the widened compression span fixed B0' 16.3→9.5). DP=60 < entanglement Me ⇒ deform fallback underestimates K 30-50%; Murnaghan less size-sensitive.
- **DOMINANT uncertainty = `tg_rate_span_slope_gate`** (NOT ff_transferability). PVC2 had degenerate Tg fits (under-equilibration); PVC3 FIXED that with slower rates [25,50,100] + 8ns/7cyc equil → good per-rate fits, BUT the 0.6-decade span then FAILED the multirate slope-gate (slope inverted, loglinear R²=0.38, fell back to single_rate). Seed-reroll does NOT fix span. The plan-level fix is a **wider rate ladder ≥1.2 decades** — PVC4 uses **[6.25,12.5,25,50,100] K/ns** (log10(100/6.25)=1.20 dec). reduction_probe=none (fix already applied in the plan, not a probe).
  - **CRITICAL: widen at the SLOW end, never the fast end.** There is a **200 ps steps-per-T-hold HARD floor** (200000 steps at dt=1fs). At ΔT=20 K: N = ΔT/(rate·dt) steps, so 100 K/ns = 200 ps (exactly at the floor) and 200 K/ns = 100 ps (VIOLATES it → degenerate c~0 fits, the retired-[40,160,400] failure). My round-1 [12.5,25,50,100,200] was rejected by the critic for exactly this. Anchor the TOP rate at 100 K/ns and extend the slow end DOWN (6.25 K/ns = 3200 ps/hold) to buy the ≥1.2-decade span.
- **ff_transferability is a SECONDARY uncertainty** here: PCFF underpredicts PVC Tg ~-12% and K ~-20% (consistent sign, known FF limit, not a fit artifact). Density reliable ~-2.5%. reduction_probe=literature_anchor (OPLS cross-check unavailable — build fails).
- **D-08 hardware:** family pcff. Cell ≈ dp60 × nch10 × 6 (all-atom C2H3Cl per monomer) ≈ 3,600 atoms < 10k → 1 GPU. Adopt by_forcefield.pcff default (engine=kokkos, mpi=1, gpu_per_run=1); do NOT write engine/gpu/mpi into decided_params (stay on policy path). **The live host IS 4× NVIDIA A800 40GB (verify with nvidia-smi — do NOT assume RTX 6000; I got this wrong in round 1).** That is the SAME host the directional_probe was measured_on (A800, 2026-06-21), so the recommended_by_ff.pcff figure (42.8 ns/day, parity PASS) is **host-matched** → set D-08 confidence=**medium**, reduction_probe=**none** (no hardware_benchmark needed). Only residual caveat: hardware_policy.values_are_benchmarked is still flagged false (2026-06-21 revalidation ran under CPU contention) — note it separately; it does not change the config choice.
- Set `t_range_brackets_exp_tg: true` in tg success_criteria (150-550 brackets 354).

See [[pstr-reasoned-plan]] (sibling medium/in-table PCFF class).
