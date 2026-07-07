## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=299.78 K · 1951 frames analysed (skip=50) · 2026-06-23 20:46

**Overall: PASS**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.0022% (p=0.9644) | <1%, p<0.01 | PASS |
| Energy drift | 0.0161% (p=0.868) | <1%, p<0.01 | PASS |
| Density block-SEM | 0.0296% | <1% | PASS |
| Energy block-SEM | 0.0116% | <1% | PASS |
| τ_eff density | 0.0% of trajectory | — | OK |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 12.0% | <30% | PASS |
| MSID slope | 0.994 (R²=0.9927) | 1.0 ±20% | OK |
| C(t) τ_relax | 264166.6 ps (10% decayed) | — | ⚠ partial |
| MSD kinetic trap | no (α=0.22, MSD=515.37 Å²>>Rg²=200.619) | — | OK |
| R_ee mean ± std | 29.74 ± 11.09 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0173 ± 0.0062 | <0.10 | PASS |
| Density homogeneity CV | 24.8% (6³ grid, 29.7 atoms/voxel) | <25% | PASS |

**Warnings:** C(t) partially decayed: 10% decayed at end of trajectory (τ_relax=264166.6 ps vs T_traj=1951.0 ps)