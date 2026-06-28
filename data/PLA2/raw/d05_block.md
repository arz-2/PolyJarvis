## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=300.13 K · 951 frames analysed (skip=50) · 2026-06-22 18:22

**Overall: FAIL**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.0622% (p=0.1565) | <1%, p<0.01 | PASS |
| Energy drift | 0.0732% (p=0.1162) | <1%, p<0.01 | PASS |
| Density block-SEM | 0.0129% | <1% | PASS |
| Energy block-SEM | 0.0121% | <1% | PASS |
| τ_eff density | 0.0% of trajectory | — | OK |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 21.3% | <30% | PASS |
| MSID slope | 1.142 (R²=0.9967) | 1.0 ±20% | OK |
| C(t) τ_relax | 266666.2 ps (4% decayed) | — | ⚠ partial |
| MSD kinetic trap | no (α=0.483, MSD=359.78 Å²>>Rg²=281.233) | — | OK |
| R_ee mean ± std | 36.36 ± 13.78 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0171 ± 0.0061 | <0.10 | PASS |
| Density homogeneity CV | 23.7% (6³ grid, 20.9 atoms/voxel) | <25% | PASS |

**Warnings:** C(t) partially decayed: 4% decayed at end of trajectory (τ_relax=266666.2 ps vs T_traj=951.0 ps)