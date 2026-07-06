## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=299.98 K · 4951 frames analysed (skip=50) · 2026-07-02 16:09

**Overall: PASS**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.0% (p=1.0) | <1%, p<0.01 | N/A (NVT — fixed volume) |
| Energy drift | 0.834% (p=0.0045) | <1%, p<0.01 | PASS |
| Density block-SEM | 0.0% | <1% | N/A (NVT — fixed volume) |
| Energy block-SEM | 0.1875% | <1% | PASS |
| τ_eff density | 0.0% of trajectory | — | OK |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 19.4% | <30% | PASS |
| MSID slope | 1.178 (R²=0.9667) | 1.0 ±20% | OK |
| C(t) τ_relax | 88154.6 ps (6% decayed) | — | ⚠ partial |
| MSD kinetic trap | yes (α=0.278, MSD=496.78 Å²>>Rg²=614.601) | — | ⚠ trapped |
| R_ee mean ± std | 59.81 ± 18.95 Å (N=20 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0411 ± 0.0065 | <0.10 | PASS |
| Density homogeneity CV | 12.8% (6³ grid, 22.4 atoms/voxel) | <25% | PASS |

**Warnings:** C(t) partially decayed: 6% decayed at end of trajectory (τ_relax=88154.6 ps vs T_traj=4951.0 ps); MSD kinetic trap: chains have not displaced their own size (MSD_max < Rg²) — expected below Tg, problematic in melt state