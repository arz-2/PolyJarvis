## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=300.03 K · 951 frames analysed (skip=50) · 2026-06-23 23:46

**Overall: FAIL**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.0344% (p=0.5026) | <1%, p<0.01 | PASS |
| Energy drift | 0.4766% (p=0.0572) | <1%, p<0.01 | PASS |
| Density block-SEM | 0.0579% | <1% | PASS |
| Energy block-SEM | 0.1414% | <1% | PASS |
| τ_eff density | 0.1% of trajectory | — | OK |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 20.4% | <30% | PASS |
| MSID slope | 1.089 (R²=0.969) | 1.0 ±20% | OK |
| C(t) τ_relax | 481230223.3 ps (1% decayed) | — | ⚠ partial |
| MSD kinetic trap | yes (α=0.026, MSD=109.98 Å²>>Rg²=582.646) | — | ⚠ trapped |
| R_ee mean ± std | 61.5 ± 23.94 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0356 ± 0.0046 | <0.10 | PASS |
| Density homogeneity CV | 21.2% (7³ grid, 20.5 atoms/voxel) | <25% | PASS |

**Warnings:** C(t) partially decayed: 1% decayed at end of trajectory (τ_relax=481230223.3 ps vs T_traj=951.0 ps); MSD kinetic trap: chains have not displaced their own size (MSD_max < Rg²) — expected below Tg, problematic in melt state