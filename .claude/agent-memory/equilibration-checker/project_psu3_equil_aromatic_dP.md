---
name: psu3_equil_aromatic_dp25
description: PSU3 DP=25 aromatic glassy C(t)/MSD advisory-only (backbone too rigid); gate on density SEM/CV/P2/energy only
metadata:
  type: project
---

PSU3 (PSFO, polysulfone) is a glassy aromatic polymer with DP=25 < 30 threshold.

**Key facts:**
- backbone_types = [2, 8] (aromatic C + sulfone S in PCFF)
- is_glassy = true (T_workflow = 600 K >> typical Tg ~540–580 K estimated)
- ct_min_decay_melt = null (aromatic main chain, per polymer_rules)

**Equilibration gate rules for DP<30 aromatic:**
- C(t)/C∞ and MSD are ADVISORY ONLY — rigid aromatic backbone → τ_relax is unreachable below Tg
- Hard gates are: density block-SEM < 1%, density homogeneity CV < 25%, P2 < 0.10, energy drift < 1%
- Do NOT loop EXTEND on C(t) or MSD stall — gate only on thermo/structural metrics

**Status:**
- Density: 1.1825 g/cm³ (−4.75% vs exp 1.24) ✓ within ±5%
- Density drift: 0.115% (p=0.00022) ✓ excellent
- Comprehensive check in progress (processing 1.5 GB dump file with R_ee/C(t)/MSD, reported as advisory)
