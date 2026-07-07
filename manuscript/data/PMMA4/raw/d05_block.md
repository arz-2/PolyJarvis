## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=300.07 K · 1951 frames analysed (skip=50) · 2026-06-27 20:26

**Overall: FAIL**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.0229% (p=0.5505) | <1%, p<0.01 | PASS |
| Energy drift | 0.0393% (p=0.2959) | <1%, p<0.01 | PASS |
| Density block-SEM | 0.0165% | <1% | PASS |
| Energy block-SEM | 0.0089% | <1% | PASS |
| τ_eff density | 0.0% of trajectory | — | OK |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 12.5% | <30% | PASS |
| MSID slope | 1.105 (R²=0.9961) | 1.0 ±20% | OK |
| C(t) τ_relax | 5641859137.6 ps (1% decayed) | — | ⚠ partial |
| MSD kinetic trap | no (α=0.146, MSD=292.53 Å²>>Rg²=239.873) | — | OK |
| R_ee mean ± std | 40.11 ± 11.44 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0137 ± 0.0041 | <0.10 | PASS |
| Density homogeneity CV | 28.3% (7³ grid, 21.9 atoms/voxel) | <25% | FAIL |

**Warnings:** C(t) partially decayed: 1% decayed at end of trajectory (τ_relax=5641859137.6 ps vs T_traj=1951.0 ps)