---
name: pvc3_r50_setup_clean
description: PVC3 r50 (50 K/ns cooling rate) Tg sweep setup completed cleanly — template choice, per-T dump, script generation
metadata:
  type: feedback
---

Run: PVC3, rate 50 K/ns (index 1 of multirate [25,50,100])
Status: CLEAN — script generated, submitted, monitor command obtained

**Template:** npt_tg_step (CORRECT for multi-T cooling staircase — not single-T npt)
**FF verification:** PCFF Class II confirmed in generated .in (pair_style lj/class2/coul/long, kspace pppm, dihedral_style class2)
**Per-T dump:** enabled (WRITE_PER_T_DUMP=True, PER_T_DUMP_FILE="per_t_structs.dump") — each T step writes one final-frame snapshot for Rg/P2 order-parameter analysis
**Velocity seed:** auto-drawn (null in prompt → template RNG) — seed 360534 captured and reported

**Why:** Multirate Tg sweeps require the full npt_tg_step template to handle 21 temperature steps (550→150 K, step 20 K) with momentum inheritance across steps. Per-T dumps are lightweight (one snapshot per T, not full trajectory) and required for structural order parameter post-processing.

**How to apply:** (1) Always use npt_tg_step for cooling staircases, never single-T npt. (2) Always enable WRITE_PER_T_DUMP when run plan specifies structural analysis (here: per-T Rg). (3) Always capture velocity seed immediately after script generation, even when template draws RNG.
