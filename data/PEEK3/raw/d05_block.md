## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=299.98 K · 1951 frames analysed (skip=50) · 2026-06-24 22:10

**Overall: PASS**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.0142% (p=0.6319) | <1%, p<0.01 | PASS |
| Energy drift | 0.0055% (p=0.8861) | <1%, p<0.01 | PASS |
| Density block-SEM | 0.0231% | <1% | PASS |
| Energy block-SEM | 0.012% | <1% | PASS |
| τ_eff density | 0.0% of trajectory | — | OK |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 28.1% | <30% | PASS |
| MSID slope | 1.019 (R²=0.9969) | 1.0 ±20% | OK |
| C(t) τ_relax | 27339.1 ps (12% decayed) | — | ⚠ partial |
| MSD kinetic trap | yes (α=0.221, MSD=975.66 Å²>>Rg²=1187.317) | — | ⚠ trapped |
| R_ee mean ± std | 66.1 ± 42.31 Å (N=8 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0215 ± 0.0067 | <0.10 | PASS |
| Density homogeneity CV | 20.5% (7³ grid, 25.4 atoms/voxel) | <25% | PASS |

**Warnings:** C(t) partially decayed: 12% decayed at end of trajectory (τ_relax=27339.1 ps vs T_traj=1951.0 ps); MSD kinetic trap: chains have not displaced their own size (MSD_max < Rg²) — expected below Tg, problematic in melt state