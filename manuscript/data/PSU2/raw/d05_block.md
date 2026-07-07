## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=299.99 K · 1951 frames analysed (skip=50) · 2026-06-23 19:35

**Overall: FAIL**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.0572% (p=0.054) | <1%, p<0.01 | PASS |
| Energy drift | 0.0997% (p=0.0521) | <1%, p<0.01 | PASS |
| Density block-SEM | 0.0104% | <1% | PASS |
| Energy block-SEM | 0.0134% | <1% | PASS |
| τ_eff density | 0.0% of trajectory | — | OK |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 15.5% | <30% | PASS |
| MSID slope | 0.901 (R²=0.9855) | 1.0 ±20% | OK |
| C(t) τ_relax | 2692819.5 ps (4% decayed) | — | ⚠ partial |
| MSD kinetic trap | no (α=0.242, MSD=971.03 Å²>>Rg²=651.065) | — | OK |
| R_ee mean ± std | 52.72 ± 19.92 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0098 ± 0.0037 | <0.10 | PASS |
| Density homogeneity CV | 25.6% (8³ grid, 21.1 atoms/voxel) | <25% | FAIL |

**Warnings:** C(t) partially decayed: 4% decayed at end of trajectory (τ_relax=2692819.5 ps vs T_traj=1951.0 ps)