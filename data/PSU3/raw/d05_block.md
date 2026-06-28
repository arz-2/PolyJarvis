## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=300.09 K · 1951 frames analysed (skip=50) · 2026-06-25 02:02

**Overall: FAIL**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.1153% (p=0.0002) | <1%, p<0.01 | PASS |
| Energy drift | 0.0345% (p=0.481) | <1%, p<0.01 | PASS |
| Density block-SEM | 0.0285% | <1% | PASS |
| Energy block-SEM | 0.0096% | <1% | PASS |
| τ_eff density | 0.0% of trajectory | — | OK |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 36.5% | <30% | FAIL |
| MSID slope | 1.026 (R²=0.9923) | 1.0 ±20% | OK |
| C(t) τ_relax | 19471772.4 ps (2% decayed) | — | ⚠ partial |
| MSD kinetic trap | yes (α=0.226, MSD=666.09 Å²>>Rg²=1260.449) | — | ⚠ trapped |
| R_ee mean ± std | 83.89 ± 44.66 Å (N=8 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0225 ± 0.0046 | <0.10 | PASS |
| Density homogeneity CV | 25.1% (8³ grid, 21.1 atoms/voxel) | <25% | FAIL |

**Warnings:** C(t) partially decayed: 2% decayed at end of trajectory (τ_relax=19471772.4 ps vs T_traj=1951.0 ps); MSD kinetic trap: chains have not displaced their own size (MSD_max < Rg²) — expected below Tg, problematic in melt state