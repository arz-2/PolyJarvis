## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=300.05 K · 1951 frames analysed (skip=50) · 2026-08-13 00:53

**Overall: FAIL**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.1944% (p=0.0001) | <1%, p<0.01 | PASS |
| Energy drift | 0.0052% (p=0.9656) | <1%, p<0.01 | PASS |
| Density block-SEM | 0.0333% | <1% | PASS |
| Energy block-SEM | 0.0531% | <1% | PASS |
| τ_eff density | 0.7% of trajectory | — | OK |
| Independent density samples | 149 | ≥20 | PASS |
| Residual deviatoric stress | 50.1 atm von Mises (max |dev| 33.3 atm, z=1.22, not resolved (z<2)) | — | INFO |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 15.9% | <30% | PASS |
| MSID slope | 0.99 (R²=0.9719) | 1.0 ±20% | OK |
| C(t) τ_relax | 1917264.7 ps (2% decayed) | — | ⚠ partial |
| MSD kinetic trap | yes (α=0.168, MSD=224.91 Å²>>Rg²=324.11) | — | ⚠ trapped |
| R_ee mean ± std | 41.66 ± 13.81 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0134 ± 0.0036 | <0.10 | PASS |
| Finite size | L=40.33 Å · L/2r_cut=n/a · L/2Rg=1.134 · L/R_ee=0.968 | ≥1.0 | PASS |
| Density homogeneity CV (signal) | 0.0% (raw 21.6% − Poisson 22.1%; 7³ grid, 20.5 atoms/voxel) | <11% | PASS |

**Warnings:** C(t) partially decayed: 2% decayed at end of trajectory (τ_relax=1917264.7 ps vs T_traj=1951.0 ps); MSD kinetic trap: chains have not displaced their own size (MSD_max < Rg²) — expected below Tg, problematic in melt state