## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=299.9 K · 951 frames analysed (skip=50) · 2026-07-02 16:05

**Overall: PASS**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.1026% (p=0.0246) | <1%, p<0.01 | PASS |
| Energy drift | 0.0724% (p=0.2058) | <1%, p<0.01 | PASS |
| Density block-SEM | 0.0403% | <1% | PASS |
| Energy block-SEM | 0.019% | <1% | PASS |
| τ_eff density | 0.1% of trajectory | — | OK |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 17.8% | <30% | PASS |
| MSID slope | 1.107 (R²=0.9905) | 1.0 ±20% | OK |
| C(t) τ_relax | 569571.5 ps (4% decayed) | — | ⚠ partial |
| MSD kinetic trap | no (α=0.277, MSD=706.18 Å²>>Rg²=629.2) | — | OK |
| R_ee mean ± std | 55.89 ± 21.39 Å (N=8 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0364 ± 0.0098 | <0.10 | PASS |
| Density homogeneity CV | 17.6% (5³ grid, 32.8 atoms/voxel) | <25% | PASS |

**Warnings:** C(t) partially decayed: 4% decayed at end of trajectory (τ_relax=569571.5 ps vs T_traj=951.0 ps)