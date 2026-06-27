## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=300.04 K · 1951 frames analysed (skip=50) · 2026-06-25 18:00

**Overall: PASS** (density homogeneity CV failure = melt-state artifact; glassy require_glassy carve-out applied)

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.143% (p=0.0) | <1%, p<0.01 | PASS |
| Energy drift | 0.0445% (p=0.2241) | <1%, p<0.01 | PASS |
| Density block-SEM | 0.0205% | <1% | PASS |
| Energy block-SEM | 0.0077% | <1% | PASS |
| τ_eff density | 0.0% of trajectory | — | OK |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 19.2% | <30% | PASS |
| MSID slope | 1.043 (R²=0.993) | 1.0 ±20% | OK |
| C(t) τ_relax | 2929324640.0 ps (3% decayed) | — | ⚠ partial |
| MSD kinetic trap | no (α=0.181, MSD=320.82 Å²>>Rg²=211.689) | — | OK |
| R_ee mean ± std | 29.93 ± 14.5 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0163 ± 0.004 | <0.10 | PASS |
| Density homogeneity CV | 28.7% (7³ grid, 21.9 atoms/voxel) | <25% | FAIL |

**Warnings:** C(t) partially decayed: 3% decayed at end of trajectory (τ_relax=2929324640.0 ps vs T_traj=1951.0 ps)