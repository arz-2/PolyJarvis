## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=299.96 K · 1951 frames analysed (skip=50) · 2026-06-23 01:34

**Overall: FAIL**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.1909% (p=0.0) | <1%, p<0.01 | PASS |
| Energy drift | 0.0582% (p=0.1097) | <1%, p<0.01 | PASS |
| Density block-SEM | 0.022% | <1% | PASS |
| Energy block-SEM | 0.009% | <1% | PASS |
| τ_eff density | 0.0% of trajectory | — | OK |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 16.3% | <30% | PASS |
| MSID slope | 0.942 (R²=0.9863) | 1.0 ±20% | OK |
| C(t) τ_relax | 533038167.0 ps (1% decayed) | — | ⚠ partial |
| MSD kinetic trap | yes (α=0.107, MSD=52.82 Å²>>Rg²=235.544) | — | ⚠ trapped |
| R_ee mean ± std | 36.46 ± 11.09 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0069 ± 0.0025 | <0.10 | PASS |
| Density homogeneity CV | 27.7% (7³ grid, 21.9 atoms/voxel) | <25% | FAIL |

**Warnings:** C(t) partially decayed: 1% decayed at end of trajectory (τ_relax=533038167.0 ps vs T_traj=1951.0 ps); MSD kinetic trap: chains have not displaced their own size (MSD_max < Rg²) — expected below Tg, problematic in melt state