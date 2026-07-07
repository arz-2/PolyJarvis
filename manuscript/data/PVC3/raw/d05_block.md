## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=299.85 K · 951 frames analysed (skip=50) · 2026-06-24 01:26

**Overall: PASS**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.5939% (p=0.0) | <1%, p<0.01 | PASS |
| Energy drift | 0.6552% (p=0.6755) | <1%, p<0.01 | PASS |
| Density block-SEM | 0.069% | <1% | PASS |
| Energy block-SEM | 0.4727% | <1% | PASS |
| τ_eff density | 0.1% of trajectory | — | OK |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 12.9% | <30% | PASS |
| MSID slope | 1.196 (R²=0.9709) | 1.0 ±20% | OK |
| C(t) τ_relax | 16194.5 ps (13% decayed) | — | ⚠ partial |
| MSD kinetic trap | no (α=0.364, MSD=479.54 Å²>>Rg²=205.848) | — | OK |
| R_ee mean ± std | 31.5 ± 10.11 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0324 ± 0.0076 | <0.10 | PASS |
| Density homogeneity CV | 18.8% (5³ grid, 29.0 atoms/voxel) | <25% | PASS |

**Warnings:** C(t) partially decayed: 13% decayed at end of trajectory (τ_relax=16194.5 ps vs T_traj=951.0 ps)