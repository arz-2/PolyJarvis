## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=300.04 K · 1951 frames analysed (skip=50) · 2026-06-23 23:31

**Overall: PASS**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.0943% (p=0.0313) | <1%, p<0.01 | PASS |
| Energy drift | 0.4308% (p=0.0001) | <1%, p<0.01 | PASS |
| Density block-SEM | 0.0283% | <1% | PASS |
| Energy block-SEM | 0.0445% | <1% | PASS |
| τ_eff density | 0.1% of trajectory | — | OK |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 17.6% | <30% | PASS |
| MSID slope | 1.042 (R²=0.9898) | 1.0 ±20% | OK |
| C(t) τ_relax | 585304.5 ps (3% decayed) | — | ⚠ partial |
| MSD kinetic trap | no (α=0.334, MSD=940.11 Å²>>Rg²=704.194) | — | OK |
| R_ee mean ± std | 62.81 ± 20.65 Å (N=20 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0159 ± 0.0068 | <0.10 | PASS |
| Density homogeneity CV | 12.8% (7³ grid, 23.4 atoms/voxel) | <25% | PASS |

**Warnings:** C(t) partially decayed: 3% decayed at end of trajectory (τ_relax=585304.5 ps vs T_traj=1951.0 ps)