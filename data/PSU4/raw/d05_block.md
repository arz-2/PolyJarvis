## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=300.0 K · 151 frames analysed (skip=50) · 2026-06-27 04:16

**Overall: FAIL**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.0827% (p=0.0092) | <1%, p<0.01 | PASS |
| Energy drift | 0.0618% (p=0.205) | <1%, p<0.01 | PASS |
| Density block-SEM | 0.0189% | <1% | PASS |
| Energy block-SEM | 0.013% | <1% | PASS |
| τ_eff density | 0.0% of trajectory | — | OK |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 31.6% | <30% | FAIL |
| MSID slope | 1.026 (R²=0.9952) | 1.0 ±20% | OK |
| C(t) τ_relax | 29212.0 ps (3% decayed) | — | ⚠ partial |
| MSD kinetic trap | yes (α=0.332, MSD=542.56 Å²>>Rg²=1134.846) | — | ⚠ trapped |
| R_ee mean ± std | 76.63 ± 37.36 Å (N=8 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0145 ± 0.0041 | <0.10 | PASS |
| Density homogeneity CV | 26.2% (8³ grid, 21.1 atoms/voxel) | <25% | FAIL |

**Warnings:** C(t) partially decayed: 3% decayed at end of trajectory (τ_relax=29212.0 ps vs T_traj=151.0 ps); MSD kinetic trap: chains have not displaced their own size (MSD_max < Rg²) — expected below Tg, problematic in melt state