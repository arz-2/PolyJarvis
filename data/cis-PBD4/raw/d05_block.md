## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=300.0 K · 1951 frames analysed (skip=50) · 2026-06-26 11:29

**Overall: FAIL**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.1244% (p=0.0082) | <1%, p<0.01 | PASS |
| Energy drift | 0.1111% (p=0.3091) | <1%, p<0.01 | PASS |
| Density block-SEM | 0.0311% | <1% | PASS |
| Energy block-SEM | 0.0526% | <1% | PASS |
| τ_eff density | 0.1% of trajectory | — | OK |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 20.8% | <30% | PASS |
| MSID slope | 1.011 (R²=0.9944) | 1.0 ±20% | OK |
| C(t) τ_relax | 59072.1 ps (5% decayed) | — | ⚠ partial |
| MSD kinetic trap | no (α=0.355, MSD=1086.38 Å²>>Rg²=716.463) | — | OK |
| R_ee mean ± std | 63.34 ± 21.35 Å (N=20 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0112 ± 0.0036 | <0.10 | PASS |
| Density homogeneity CV | 12.7% (7³ grid, 23.4 atoms/voxel) | <25% | PASS |

**Warnings:** C(t) partially decayed: 5% decayed at end of trajectory (τ_relax=59072.1 ps vs T_traj=1951.0 ps)