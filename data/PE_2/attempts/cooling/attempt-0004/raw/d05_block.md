## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=300.21 K · 201 frames analysed (skip=50) · 2026-09-13 21:10

**Overall: FAIL**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.582% (p=0.0003) | <1%, p<0.01 | PASS |
| Energy drift | 1.7315% (p=0.0059) | <1%, p<0.01 | FAIL |
| Energy component drift | bond=1.6302%, angle=0.2126%, dihedral=0.8074%, vdw=0.781%✗, coul=0.0%, kspace=0.0% | <1%, p<0.01 each | FAIL |
| Density block-SEM | 0.1089% | <1% | PASS |
| Energy block-SEM | 0.3205% | <1% | PASS |
| τ_eff density | 5.0% of trajectory | — | OK |
| Independent density samples | 19 | ≥20 | FAIL |
| Residual deviatoric stress | 92.7 atm von Mises (max |dev| 58.7 atm, z=1.47, not resolved (z<2)) | — | INFO |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 15.2% | <30% | PASS |
| MSID slope (combined) | 1.117 (R²=0.9946) | 1.0 ±20% | OK |
| MSID slope (large-s, n=[61, 180]) | 1.011 (R²=0.998) | 1.0 ±20% | OK |
| Torsion JS-divergence (last block-pair) | 0.00019 | ≤0.05 | OK (stable) |
| C(t) τ_relax | 291957677.7 ps (0% decayed) | — | ⚠ partial |
| MSD kinetic trap | yes (α=0.261, MSD=374.41 Å²>>Rg²=1121.237) | — | ⚠ trapped |
| R_ee mean ± std | 70.8 ± 12.33 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0196 ± 0.0058 | <0.10 | PASS |
| Finite size | L=46.09 Å · L/2r_cut=1.646 · L/2Rg=0.696 · L/R_ee=0.651 | ≥1.0 | SIZE_CHAIN_SELF_IMAGE_ADVISORY |
| Density homogeneity CV (signal) | 0.0% (raw 10.3% − Poisson 18.6%; 5³ grid, 28.8 atoms/voxel) | <11% | PASS |

**Warnings:** C(t) partially decayed: 0% decayed at end of trajectory (τ_relax=291957677.7 ps vs T_traj=402.0 ps); MSD kinetic trap: chains have not displaced their own size (MSD_max < Rg²) — expected below Tg, problematic in melt state