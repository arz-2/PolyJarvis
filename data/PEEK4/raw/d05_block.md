## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=299.98 K · 1951 frames analysed (skip=50) · 2026-06-26 04:36

**Overall: PASS**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.3385% (p=0.0) | <1%, p<0.01 | PASS |
| Energy drift | 0.0555% (p=0.143) | <1%, p<0.01 | PASS |
| Density block-SEM | 0.0398% | <1% | PASS |
| Energy block-SEM | 0.0122% | <1% | PASS |
| τ_eff density | 0.1% of trajectory | — | OK |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 18.4% | <30% | PASS |
| MSID slope | 1.042 (R²=0.9963) | 1.0 ±20% | OK |
| C(t) τ_relax | 1390437.7 ps (3% decayed) | — | ⚠ partial |
| MSD kinetic trap | yes (α=0.23, MSD=740.66 Å²>>Rg²=1146.647) | — | ⚠ trapped |
| R_ee mean ± std | 72.84 ± 17.17 Å (N=8 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0184 ± 0.0063 | <0.10 | PASS |
| Density homogeneity CV | 20.6% (7³ grid, 25.4 atoms/voxel) | <25% | PASS |

**Warnings:** C(t) partially decayed: 3% decayed at end of trajectory (τ_relax=1390437.7 ps vs T_traj=1951.0 ps); MSD kinetic trap: chains have not displaced their own size (MSD_max < Rg²) — expected below Tg, problematic in melt state