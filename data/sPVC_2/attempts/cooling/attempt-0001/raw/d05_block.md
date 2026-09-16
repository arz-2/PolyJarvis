## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=299.99 K · 451 frames analysed (skip=50) · 2026-09-11 01:31

**Overall: FAIL**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.3108% (p=0.0011) | <1%, p<0.01 | PASS |
| Energy drift | 3.6947% (p=0.1558) | <1%, p<0.01 | PASS |
| Energy component drift | bond=0.4494%, angle=0.0212%, dihedral=0.3182%, vdw=2.1374%, coul=0.0907%, kspace=0.0016% | <1%, p<0.01 each | PASS |
| Density block-SEM | 0.0539% | <1% | PASS |
| Energy block-SEM | 1.1185% | <1% | FAIL |
| τ_eff density | 1.0% of trajectory | — | OK |
| Independent density samples | 103 | ≥20 | PASS |
| Residual deviatoric stress | 171.2 atm von Mises (max |dev| 113.8 atm, z=2.05, resolved) | — | INFO |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 17.2% | <30% | PASS |
| MSID slope (combined) | 1.284 (R²=0.9868) | 1.0 ±20% | ⚠ non-Gaussian |
| MSID slope (large-s, n=[29, 82]) | 1.041 (R²=0.9989) | 1.0 ±20% | OK |
| Torsion JS-divergence (last block-pair) | 0.00022 | ≤0.05 | OK (stable) |
| C(t) τ_relax | 3195398448.2 ps (0% decayed) | — | ⚠ partial |
| MSD kinetic trap | yes (α=0.034, MSD=108.43 Å²>>Rg²=457.275) | — | ⚠ trapped |
| R_ee mean ± std | 51.21 ± 14.7 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0243 ± 0.0033 | <0.10 | PASS |
| Finite size | L=39.79 Å · L/2r_cut=2.094 · L/2Rg=0.944 · L/R_ee=0.777 | ≥1.0 | SIZE_CHAIN_SELF_IMAGE_ADVISORY |
| Density homogeneity CV (signal) | 0.0% (raw 19.9% − Poisson 32.3%; 6³ grid, 22.9 atoms/voxel) | <11% | PASS |

**Warnings:** MSID slope = 1.284 (expected 1.0 ±20% for Gaussian chain) — possible chain collapse or extension; C(t) partially decayed: 0% decayed at end of trajectory (τ_relax=3195398448.2 ps vs T_traj=451.0 ps); MSD kinetic trap: chains have not displaced their own size (MSD_max < Rg²) — expected below Tg, problematic in melt state