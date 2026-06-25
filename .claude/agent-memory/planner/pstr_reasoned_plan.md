---
name: pstr-reasoned-plan
description: How to build a PSTR (polystyrenics, e.g. aPS) reasoned run_plan — confidence=medium, in-table temps, PCFF/EMC, glassy K, hardware
metadata:
  type: feedback
---

PSTR is confidence=medium and IS in polymer_rules.json with class-specific temperatures (T_equil=550, anneal=630, Tg sweep 200-600 K @ 20 K step, rates [25,50,100] K/ns). Build a **reasoned** plan (not deterministic).

**Why:** medium confidence forces reasoned mode; the Critic escalates a deterministic plan on a non-high class.

**How to apply:**
- **Skip** `estimate_tg_group_contribution.py` — that step is only for off-table or confidence=low classes. PSTR's temps are already class-specific; leave global_defaults from the scaffold unchanged.
- **Dominant uncertainty = `ff_transferability`** with `reduction_probe: literature_anchor`. There is NO direct PCFF PS Tg validation paper; PCFF Class II is used by analogy to PC (Tg 417 vs exp 422) and PMMA vinyl. SimPoly MD Tg ~399±22 K vs exp 373 K → expect MD overprediction.
- **D-01 FF = pcff** (NOT TraPPE-UA: UA omits phenyl ring partial charges / pi-dihedral barriers; switched 2026-06-11). Reject GAFF2_mod (Tg err >45% PMMA). Cite ja00086a030 + Tang2022/NkepsuMbitou2025/Soldera2006.
- **D-03 = pppm REQUIRED** even though backbone is pure C/H — PCFF puts partial charges on the aromatic ring. lj/cut is only for apolar UA (PHYC/PDIE).
- **D-07 = glassy** path: PS is glassy at 300 K (exp Tg 373 K). Murnaghan NPT compression at 300 K is primary; deform fallback; Born+NVT removed. Exp glassy K_T 3.3-4.0 GPa. DP=40 < entanglement Me (DP@Me~160) → deform K underestimated 30-50%; Murnaghan is less size-sensitive, flag offset in summary.
- **D-08 hardware:** PCFF→family pcff. Cell ≈ dp40 × nchain10 × 16 (all-atom styrene-repeat atoms) ≈ 6,400 atoms <10k → 1 GPU. Adopt by_forcefield.pcff default (engine=kokkos, mpi=1, gpu_per_run=1). directional_probe is HINT-only here: values_are_benchmarked=false AND probe host (A800/A100) != live host (RTX 6000), and 6,400 is ~2.1x the 3,020-atom benchmark cell (outside [0.5x,2x]). So keep the default, do NOT write engine/gpu/mpi into decided_params (stay on policy path), set D-08 confidence=low + a planned `hardware_benchmark` probe (uncertainty `hardware_optimum`).
- **D-06 Tg ladder [25,50,100]** clears the steps-per-T floor at dt=1fs/step=20K (800/400/200 ps). Retired [40,160,400] gave degenerate 50/125 ps fits. PS PCFF multirate slope-gate is seed/build-dependent (PS2 failed-inverted; PS3 fresh seed → Tg 376.5 K = exp). Handled by orchestrator fresh-seed recovery, not at plan time — record as a non-dominant uncertainty.
- Set `t_range_brackets_exp_tg: true` in the tg stage success_criteria (200-600 K brackets 373 K).
