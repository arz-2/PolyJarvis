## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=300.02 K · 1951 frames analysed (skip=50) · 2026-06-25 00:48

**Overall: PASS**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.2197% (p=0.0) | <1%, p<0.01 | PASS |
| Energy drift | 0.2002% (p=0.0395) | <1%, p<0.01 | PASS |
| Density block-SEM | 0.0328% | <1% | PASS |
| Energy block-SEM | 0.0249% | <1% | PASS |
| τ_eff density | 0.0% of trajectory | — | OK |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 9.5% | <30% | PASS |
| C∞ | 10.922 | lit. varies | INFO |
| MSID slope | 0.951 (R²=0.9934) | 1.0 ±20% | OK |
| C(t) τ_relax | 109275.4 ps (10% decayed) | — | ⚠ partial |
| MSD kinetic trap | no (α=0.208, MSD=362.11 Å²>>Rg²=168.371) | — | OK |
| R_ee mean ± std | 26.83 ± 8.37 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0231 ± 0.006 | <0.10 | PASS |
| Density homogeneity CV | 24.1% (6³ grid, 29.7 atoms/voxel) | <25% | PASS |

**Warnings:** C(t) partially decayed: 10% decayed at end of trajectory (τ_relax=109275.4 ps vs T_traj=1951.0 ps)