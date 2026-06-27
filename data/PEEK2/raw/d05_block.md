## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=299.91 K · 1951 frames analysed (skip=50) · 2026-06-22 14:50

**Overall: PASS**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.0466% (p=0.0946) | <1%, p<0.01 | PASS |
| Energy drift | 0.0039% (p=0.9112) | <1%, p<0.01 | PASS |
| Density block-SEM | 0.0172% | <1% | PASS |
| Energy block-SEM | 0.0076% | <1% | PASS |
| τ_eff density | 0.0% of trajectory | — | OK |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 14.3% | <30% | PASS |
| MSID slope | 1.097 (R²=0.9964) | 1.0 ±20% | OK |
| C(t) τ_relax | 23803674.5 ps (2% decayed) | — | ⚠ partial |
| MSD kinetic trap | no (α=0.318, MSD=1860.39 Å²>>Rg²=1401.964) | — | OK |
| R_ee mean ± std | 95.12 ± 27.29 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0267 ± 0.0075 | <0.10 | PASS |
| Density homogeneity CV | 22.9% (8³ grid, 21.3 atoms/voxel) | <25% | PASS |

**Warnings:** C(t) partially decayed: 2% decayed at end of trajectory (τ_relax=23803674.5 ps vs T_traj=1951.0 ps)