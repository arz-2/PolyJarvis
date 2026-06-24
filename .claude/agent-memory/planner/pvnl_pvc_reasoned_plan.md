---
name: pvnl-pvc-reasoned-plan
description: PVNL/PVC (medium confidence) reasoned-plan lessons — Tg degeneracy and BM B0' failure modes and their plan-level fixes
metadata:
  type: project
---

PVNL is **medium confidence** in polymer_rules.json → reasoned plan (not deterministic). PVC member disambiguated by the `*CC(Cl)*` substituent: exp Tg=354 K, exp RT density=1.38 g/cm3, exp K_T=3.5–4.5 GPa (glassy, 25 C). PVC monomer (-CH2-CHCl-) = 6 all-atom atoms → DP60×nchain10 ≈ 3600 atoms (matches measured 3620).

**Two recurring PVC failure modes and their plan-level fixes (PVC3 revision of PVC2):**

1. **Degenerate Tg fit.** Caused by the RETIRED `[40,160,400]` K/ns rate set: at T_STEP=20K that is 500/125/50 ps per-T holds, so the two fast rates are degenerate by construction (rate == per-T sampling knob), giving transition_width c≈0 kink artifacts. Compounded by melt under-equilibration before cooling (end-to-end τ_relax ≈17.6 ns ≫ trajectory). **Fix:** (a) adopt validated `[25,50,100]` K/ns (800/400/200 ps, all clear the 200 ps floor); (b) lengthen melt equilibration `t_equil_ns` 5→8 ns and `eq_annealing_cycles` 5→7 — at DP60 melt self-diffusion is unattainable (τ_relax ~3.6e9 ps) so the high-T anneal is the policy-sanctioned substitute (require_glassy). The make_deterministic_plan.py scaffold already emits `[25,50,100]`; the equilibration bump is the reasoned override.

2. **Unphysical Murnaghan B0'.** PVC2 at ±1000 atm gave B0'=16.34 (glassy PVC should be 4–10) and K=2.91 GPa (−27% vs exp 4.0). Narrow pressure span under-constrains EOS curvature → B0' floats high. **Fix:** widen `bm_pressures_atm` to ±3000 atm (±0.3 GPa), 5 points `[-3000,-1500,0,1500,3000]`. Strain stays below glassy yield. Deform fallback if B0' still outside [4,20].

**Scaffold gotcha:** make_deterministic_plan.py writes a stale `born` mechanical stage. D-07 policy REMOVED Born+NVT (PCFF+PPPM virial incompatibility, failed 3/3 PMMA4/PVC1/PEEK1). Always rewrite the mechanical stage to `murnaghan` (success_criteria fit_converged + b0_prime_in_range [4,20], fallback deform) on the reasoned path.

**Hardware (D-08):** pcff family → KOKKOS full-offload `{engine:kokkos, mpi:1, gpu_per_run:1}`. ~3600-atom cell <10k → 1 GPU. This EQUALS by_forcefield[pcff] default, so write NO decided_params hardware override (keeps prompt byte-identical to policy path). But host mismatch (directional_probe on 4x A800/32-core vs live 4x Quadro RTX 6000/18-core) + values_are_benchmarked=false → D-08 confidence:low + planned `hardware_benchmark` probe as a non-dominant uncertainty.

See [[multimember_class_exp_tg_resolution]] for member-disambiguation pattern.
