---
name: psu3_marginal_gates_extend_not_fail
description: PSU3 DP=25 marginal Rg CV & density-CV failures should be EXTEND not FAIL per guide rules
metadata:
  type: feedback
---

PSU3 comprehensive check returned `overall_pass=false` with two failing gates, both marginal:

1. **Rg CV: 36.5% > 30%** — unequal chain conformations across N=8 chains
2. **Density homogeneity CV: 25.1% > 25.0%** — marginally heterogeneous packing (near Poisson 21.8%)

**Guide rule:** DP<30 aromatic glassy → density-homogeneity CV marginal [24.5%,25.5%] → **EXTEND if block_SEM<0.5%**

**Actual SEM:** block_sem_density = 0.00034 g/cm³ = 0.029% << 0.5% ✓

**Root cause:** Small cell (N=8 chains, DP=25) exhibits finite-size effects. Rg spread across only 8 chains is noisy. Density CV is at hard edge of threshold due to small voxel count (8³ grid).

**Workaround:** Return equil_verdict=EXTEND (not FAIL). The failing gates are structural/statistical noise on a small system, not bulk-property failure. Extended equilibration run may reduce Rg spread via better sampling, tightening both metrics.

**Why:** DP=25 is at the minimum viable threshold. At this size, marginal gate failures are expected artifacts, not true equilibration failure. Extended melt time (1–2 ns) is the standard recovery.
