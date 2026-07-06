## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=300.05 K · 451 frames analysed (skip=50) · 2026-07-02 16:08

**Overall: PASS**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.0622% (p=0.056) | <1%, p<0.01 | PASS |
| Energy drift | 0.0506% (p=0.3591) | <1%, p<0.01 | PASS |
| Density block-SEM | 0.0111% | <1% | PASS |
| Energy block-SEM | 0.0154% | <1% | PASS |
| τ_eff density | 0.0% of trajectory | — | OK |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 25.7% | <30% | PASS |
| MSID slope | 0.99 (R²=0.9965) | 1.0 ±20% | OK |
| C(t) τ_relax | 83299.5 ps (4% decayed) | — | ⚠ partial |
| MSD kinetic trap | yes (α=0.145, MSD=467.57 Å²>>Rg²=928.402) | — | ⚠ trapped |
| R_ee mean ± std | 71.61 ± 38.89 Å (N=8 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0154 ± 0.0053 | <0.10 | PASS |
| Density homogeneity CV | 23.2% (7³ grid, 25.2 atoms/voxel) | <25% | PASS |

**Warnings:** C(t) partially decayed: 4% decayed at end of trajectory (τ_relax=83299.5 ps vs T_traj=451.0 ps); MSD kinetic trap: chains have not displaced their own size (MSD_max < Rg²) — expected below Tg, problematic in melt state