## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=300.07 K · 1951 frames analysed (skip=50) · 2026-06-22 13:55

**Overall: PASS**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.1896% (p=0.0) | <1%, p<0.01 | PASS |
| Energy drift | 0.2138% (p=0.0458) | <1%, p<0.01 | PASS |
| Density block-SEM | 0.0342% | <1% | PASS |
| Energy block-SEM | 0.0535% | <1% | PASS |
| τ_eff density | 0.1% of trajectory | — | OK |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 17.5% | <30% | PASS |
| MSID slope | 1.031 (R²=0.9793) | 1.0 ±20% | OK |
| C(t) τ_relax | 153255.8 ps (7% decayed) | — | ⚠ partial |
| MSD kinetic trap | no (α=0.279, MSD=986.61 Å²>>Rg²=598.942) | — | OK |
| R_ee mean ± std | 52.73 ± 24.68 Å (N=20 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0104 ± 0.0035 | <0.10 | PASS |
| Density homogeneity CV | 12.7% (7³ grid, 23.4 atoms/voxel) | <25% | PASS |

**Warnings:** C(t) partially decayed: 7% decayed at end of trajectory (τ_relax=153255.8 ps vs T_traj=1951.0 ps)