## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=299.99 K · 2451 frames analysed (skip=50) · 2026-09-13 13:47

**Overall: FAIL**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.8164% (p=0.0) | <1%, p<0.01 | PASS |
| Energy drift | 2.9246% (p=0.0) | <1%, p<0.01 | FAIL |
| Energy component drift | bond=0.126%, angle=0.3933%, dihedral=1.4326%✗, vdw=1.2491%✗, coul=0.0%, kspace=0.0% | <1%, p<0.01 each | FAIL |
| Density block-SEM | 0.0865% | <1% | PASS |
| Energy block-SEM | 0.3634% | <1% | PASS |
| τ_eff density | 8.2% of trajectory | — | OK |
| Independent density samples | 12 | ≥20 | FAIL |
| Residual deviatoric stress | 11.9 atm von Mises (max |dev| 7.7 atm, z=0.71, not resolved (z<2)) | — | INFO |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 21.3% | <30% | PASS |
| MSID slope (combined) | 1.136 (R²=0.9974) | 1.0 ±20% | OK |
| MSID slope (large-s, n=[61, 180]) | 1.076 (R²=0.9993) | 1.0 ±20% | OK |
| Torsion JS-divergence (last block-pair) | 4e-05 | ≤0.05 | OK (stable) |
| C(t) τ_relax | 9534621.1 ps (1% decayed) | — | ⚠ partial |
| MSD kinetic trap | yes (α=0.306, MSD=1039.11 Å²>>Rg²=1273.666) | — | ⚠ trapped |
| R_ee mean ± std | 81.88 ± 22.56 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0508 ± 0.0086 | <0.10 | PASS |
| Finite size | L=46.03 Å · L/2r_cut=1.644 · L/2Rg=0.659 · L/R_ee=0.562 | ≥1.0 | SIZE_CHAIN_SELF_IMAGE_ADVISORY |
| Density homogeneity CV (signal) | 0.0% (raw 10.7% − Poisson 18.6%; 5³ grid, 28.8 atoms/voxel) | <11% | PASS |

**Warnings:** C(t) partially decayed: 1% decayed at end of trajectory (τ_relax=9534621.1 ps vs T_traj=4902.0 ps); MSD kinetic trap: chains have not displaced their own size (MSD_max < Rg²) — expected below Tg, problematic in melt state