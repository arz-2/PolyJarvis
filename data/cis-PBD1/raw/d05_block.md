## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=300.04 K · 451 frames analysed (skip=50) · 2026-07-02 16:09

**Overall: PASS**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.0258% (p=0.5618) | <1%, p<0.01 | PASS |
| Energy drift | 0.0628% (p=0.5689) | <1%, p<0.01 | PASS |
| Density block-SEM | 0.0259% | <1% | PASS |
| Energy block-SEM | 0.0476% | <1% | PASS |
| τ_eff density | 0.0% of trajectory | — | OK |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 15.3% | <30% | PASS |
| MSID slope | 1.01 (R²=0.9709) | 1.0 ±20% | OK |
| C(t) τ_relax | 18249.2 ps (5% decayed) | — | ⚠ partial |
| MSD kinetic trap | no (α=0.286, MSD=669.85 Å²>>Rg²=591.066) | — | OK |
| R_ee mean ± std | 57.81 ± 19.22 Å (N=20 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0157 ± 0.0037 | <0.10 | PASS |
| Density homogeneity CV | 12.8% (7³ grid, 23.4 atoms/voxel) | <25% | PASS |

**Warnings:** C(t) partially decayed: 5% decayed at end of trajectory (τ_relax=18249.2 ps vs T_traj=451.0 ps)