---
name: pvc3_r25_submission
description: PVC3 r25 Tg sweep submission 2026-06-24 — KOKKOS engine, per-T dump enabled
metadata:
  type: project
---

**Submission:** PVC3 rate-25 K/ns (r25) Tg sweep with per-T structural dump.

**Run ID:** 01136f53  
**Velocity Seed:** 295072 (auto-generated random, documented for reproducibility)  
**Template:** npt_tg_step (multi-T ramp, not single-T npt)  
**Force Field:** PCFF Class II (lj/class2/coul/long, kspace pppm)  
**Temperature:** 550→150 K, step 20 K (21 stages)  
**Per-T Dump:** Enabled (PER_T_DUMP_FILE=per_t_structs.dump) — one single-frame snap per T step for later Rg/P2 analysis  
**Engine:** KOKKOS (avoids GPU package neigh-list overhead; manual neighbor list management)  
**GPU:** 3 (40+ GB free)  
**Steps per T:** 800k (800 ps at dt=1 fs)  

**Why this configuration:**
- KOKKOS preferred over gpu-package for PCFF (GPU package pair-only, leaves class2-heavy dihedrals on CPU; KOKKOS offloads all hotspots → more efficient).
- Per-T dump explicitly enabled per prompt (write_per_t_dump: true) for downstream per-T order-parameter analysis.
- Seed 295072 auto-drawn; captured for cross-track reproducibility rule #2.
