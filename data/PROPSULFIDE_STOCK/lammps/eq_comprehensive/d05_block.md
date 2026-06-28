## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=299.86 K · 451 frames analysed (skip=50) · 2026-06-28 10:27

**Overall: FAIL**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 1.0723% (p=0.0001) | <1%, p<0.01 | FAIL |
| Energy drift | 1.9011% (p=0.2526) | <1%, p<0.01 | PASS |
| Density block-SEM | 0.1662% | <1% | PASS |
| Energy block-SEM | 0.5489% | <1% | PASS |
| τ_eff density | 0.1% of trajectory | — | OK |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 16.4% | <30% | PASS |
| MSID slope | 1.275 (R²=0.9999) | 1.0 ±20% | ⚠ non-Gaussian |
| C(t) τ_relax | 29127.1 ps (7% decayed) | — | ⚠ partial |
| MSD kinetic trap | no (α=0.305, MSD=121.37 Å²>>Rg²=114.105) | — | OK |
| R_ee mean ± std | 26.49 ± 9.51 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0254 ± 0.0097 | <0.10 | PASS |
| Density homogeneity CV | 21.8% (4³ grid, 31.6 atoms/voxel) | <25% | PASS |

**Warnings:** MSID slope = 1.275 (expected 1.0 ±20% for Gaussian chain) — possible chain collapse or extension; C(t) partially decayed: 7% decayed at end of trajectory (τ_relax=29127.1 ps vs T_traj=451.0 ps)