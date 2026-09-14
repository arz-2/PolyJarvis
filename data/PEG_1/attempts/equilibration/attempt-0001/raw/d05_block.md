## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=499.92 K · 1951 frames analysed (skip=50) · 2026-09-12 01:04

**Overall: PASS**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.1435% (p=0.0655) | <1%, p<0.01 | PASS |
| Energy drift | 0.324% (p=0.0049) | <1%, p<0.01 | PASS |
| Energy component drift | bond=0.3079%, angle=0.0201%, dihedral=0.0826%, vdw=1.0178%, coul=0.0741%, kspace=0.0201% | <1%, p<0.01 each | PASS |
| Density block-SEM | 0.0602% | <1% | PASS |
| Energy block-SEM | 0.0728% | <1% | PASS |
| τ_eff density | 0.6% of trajectory | — | OK |
| Independent density samples | 170 | ≥20 | PASS |
| Residual deviatoric stress | 53.0 atm von Mises (max |dev| 33.4 atm, z=1.12, not resolved (z<2)) | — | INFO |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 21.7% | <30% | PASS |
| MSID slope (combined) | 1.035 (R²=0.9648) | 1.0 ±20% | OK |
| MSID slope (large-s, n=[58, 171]) | 0.757 (R²=0.9997) | 1.0 ±20% | ⚠ non-Gaussian (large-s) |
| Torsion JS-divergence (last block-pair) | 9e-05 | ≤0.05 | OK (stable) |
| C(t) τ_relax | 43671.0 ps (26% decayed) | — | ⚠ partial |
| MSD kinetic trap | no (α=0.261, MSD=1551.1 Å²>>Rg²=584.905) | — | OK |
| R_ee mean ± std | 65.14 ± 32.38 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0286 ± 0.0099 | <0.10 | PASS |
| Finite size | L=44.71 Å · L/2r_cut=2.353 · L/2Rg=0.948 · L/R_ee=0.686 | ≥1.0 | SIZE_CHAIN_SELF_IMAGE_ADVISORY |
| Density homogeneity CV (signal) | 0.0% (raw 22.3% − Poisson 29.2%; 7³ grid, 23.3 atoms/voxel) | <11% | PASS |

**Warnings:** C(t) partially decayed: 26% decayed at end of trajectory (τ_relax=43671.0 ps vs T_traj=4951.0 ps)