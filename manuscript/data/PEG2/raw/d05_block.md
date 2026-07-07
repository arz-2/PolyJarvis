## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=300.09 K · 1951 frames analysed (skip=50) · 2026-06-22 20:45

**Overall: FAIL**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.1595% (p=0.0005) | <1%, p<0.01 | PASS |
| Energy drift | 0.6375% (p=0.0128) | <1%, p<0.01 | PASS |
| Density block-SEM | 0.0507% | <1% | PASS |
| Energy block-SEM | 0.1499% | <1% | PASS |
| τ_eff density | 0.1% of trajectory | — | OK |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 22.4% | <30% | PASS |
| C∞ | 11.651 | lit. varies | INFO |
| MSID slope | 1.018 (R²=0.9518) | 1.0 ±20% | OK |
| C(t) τ_relax | 7394924569.3 ps (1% decayed) | — | ⚠ partial |
| MSD kinetic trap | yes (α=0.1, MSD=117.47 Å²>>Rg²=455.921) | — | ⚠ trapped |
| R_ee mean ± std | 41.48 ± 25.48 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0461 ± 0.0044 | <0.10 | PASS |
| Density homogeneity CV | 22.1% (7³ grid, 20.5 atoms/voxel) | <25% | PASS |

**Warnings:** C(t) partially decayed: 1% decayed at end of trajectory (τ_relax=7394924569.3 ps vs T_traj=1951.0 ps); MSD kinetic trap: chains have not displaced their own size (MSD_max < Rg²) — expected below Tg, problematic in melt state