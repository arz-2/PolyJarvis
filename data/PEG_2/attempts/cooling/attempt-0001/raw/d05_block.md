## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=300.06 K · 1951 frames analysed (skip=50) · 2026-09-13 08:28

**Overall: FAIL**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.3364% (p=0.0) | <1%, p<0.01 | PASS |
| Energy drift | 1.9748% (p=0.0) | <1%, p<0.01 | FAIL |
| Energy component drift | bond=0.2223%, angle=0.2349%, dihedral=0.3445%, vdw=1.1528%✗, coul=0.263%✗, kspace=0.0596% | <1%, p<0.01 each | FAIL |
| Density block-SEM | 0.0348% | <1% | PASS |
| Energy block-SEM | 0.2248% | <1% | PASS |
| τ_eff density | 0.9% of trajectory | — | OK |
| Independent density samples | 112 | ≥20 | PASS |
| Residual deviatoric stress | 118.4 atm von Mises (max |dev| 74.9 atm, z=2.89, resolved) | — | INFO |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 15.4% | <30% | PASS |
| MSID slope (combined) | 1.049 (R²=0.964) | 1.0 ±20% | OK |
| MSID slope (large-s, n=[58, 171]) | 0.789 (R²=0.9975) | 1.0 ±20% | ⚠ non-Gaussian (large-s) |
| Torsion JS-divergence (last block-pair) | 3e-05 | ≤0.05 | OK (stable) |
| C(t) τ_relax | 25304893.4 ps (0% decayed) | — | ⚠ partial |
| MSD kinetic trap | yes (α=0.298, MSD=79.36 Å²>>Rg²=593.627) | — | ⚠ trapped |
| R_ee mean ± std | 57.19 ± 17.56 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0225 ± 0.0043 | <0.10 | PASS |
| Finite size | L=42.78 Å · L/2r_cut=2.252 · L/2Rg=0.888 · L/R_ee=0.748 | ≥1.0 | SIZE_CHAIN_SELF_IMAGE_ADVISORY |
| Density homogeneity CV (signal) | 0.0% (raw 19.9% − Poisson 29.2%; 7³ grid, 23.3 atoms/voxel) | <11% | PASS |

**Warnings:** C(t) partially decayed: 0% decayed at end of trajectory (τ_relax=25304893.4 ps vs T_traj=1951.0 ps); MSD kinetic trap: chains have not displaced their own size (MSD_max < Rg²) — expected below Tg, problematic in melt state