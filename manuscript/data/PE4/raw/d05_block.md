## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=299.72 K · 951 frames analysed (skip=50) · 2026-06-26 00:10

**Overall: FAIL**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.1224% (p=0.0041) | <1%, p<0.01 | PASS |
| Energy drift | 0.5788% (p=0.0032) | <1%, p<0.01 | PASS |
| Density block-SEM | 0.0347% | <1% | PASS |
| Energy block-SEM | 0.1189% | <1% | PASS |
| τ_eff density | 0.1% of trajectory | — | OK |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 19.2% | <30% | PASS |
| MSID slope | 1.12 (R²=0.9946) | 1.0 ±20% | OK |
| C(t) τ_relax | 4172606.9 ps (3% decayed) | — | ⚠ partial |
| MSD kinetic trap | yes (α=0.203, MSD=579.45 Å²>>Rg²=684.603) | — | ⚠ trapped |
| R_ee mean ± std | 58.36 ± 21.05 Å (N=20 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0238 ± 0.0057 | <0.10 | PASS |
| Density homogeneity CV | 12.9% (6³ grid, 22.4 atoms/voxel) | <25% | PASS |

**Warnings:** C(t) partially decayed: 3% decayed at end of trajectory (τ_relax=4172606.9 ps vs T_traj=951.0 ps); MSD kinetic trap: chains have not displaced their own size (MSD_max < Rg²) — expected below Tg, problematic in melt state