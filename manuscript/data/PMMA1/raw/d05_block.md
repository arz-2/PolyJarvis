## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=300.27 K · 451 frames analysed (skip=50) · 2026-07-02 16:06

**Overall: PASS**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.6166% (p=0.0) | <1%, p<0.01 | PASS |
| Energy drift | 0.0208% (p=0.7352) | <1%, p<0.01 | PASS |
| Density block-SEM | 0.0716% | <1% | PASS |
| Energy block-SEM | 0.0085% | <1% | PASS |
| τ_eff density | 0.3% of trajectory | — | OK |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 12.7% | <30% | PASS |
| MSID slope | 1.094 (R²=0.993) | 1.0 ±20% | OK |
| C(t) τ_relax | 1685226660.8 ps (6% decayed) | — | ⚠ partial |
| MSD kinetic trap | yes (α=0.061, MSD=127.3 Å²>>Rg²=166.093) | — | ⚠ trapped |
| R_ee mean ± std | 22.13 ± 10.67 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0233 ± 0.0054 | <0.10 | PASS |
| Density homogeneity CV | 24.2% (6³ grid, 27.9 atoms/voxel) | <25% | PASS |

**Warnings:** C(t) partially decayed: 6% decayed at end of trajectory (τ_relax=1685226660.8 ps vs T_traj=451.0 ps); MSD kinetic trap: chains have not displaced their own size (MSD_max < Rg²) — expected below Tg, problematic in melt state