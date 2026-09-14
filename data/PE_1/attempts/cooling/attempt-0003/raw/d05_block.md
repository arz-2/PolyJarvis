## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=300.66 K · 201 frames analysed (skip=50) · 2026-09-11 19:01

**Overall: PASS**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.5955% (p=0.0001) | <1%, p<0.01 | PASS |
| Energy drift | 2.0218% (p=0.0116) | <1%, p<0.01 | PASS |
| Energy component drift | bond=2.273%✗, angle=0.3206%, dihedral=1.8961%✗, vdw=1.1476%✗, coul=0.0%, kspace=0.0% | <1%, p<0.01 each | FAIL |
| Density block-SEM | 0.076% | <1% | PASS |
| Energy block-SEM | 0.3681% | <1% | PASS |
| τ_eff density | 3.9% of trajectory | — | OK |
| Independent density samples | 25 | ≥20 | PASS |
| Residual deviatoric stress | 82.0 atm von Mises (max |dev| 53.6 atm, z=1.66, not resolved (z<2)) | — | INFO |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 21.9% | <30% | PASS |
| MSID slope (combined) | 1.075 (R²=0.9964) | 1.0 ±20% | OK |
| MSID slope (large-s, n=[61, 180]) | 1.005 (R²=0.9994) | 1.0 ±20% | OK |
| Torsion JS-divergence (last block-pair) | 0.00013 | ≤0.05 | OK (stable) |
| C(t) τ_relax | 3591357585.9 ps (0% decayed) | — | ⚠ partial |
| MSD kinetic trap | yes (α=0.184, MSD=276.75 Å²>>Rg²=1028.614) | — | ⚠ trapped |
| R_ee mean ± std | 73.77 ± 27.7 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0213 ± 0.0041 | <0.10 | PASS |
| Finite size | L=46.17 Å · L/2r_cut=1.649 · L/2Rg=0.737 · L/R_ee=0.626 | ≥1.0 | SIZE_CHAIN_SELF_IMAGE_ADVISORY |
| Density homogeneity CV (signal) | 0.0% (raw 10.4% − Poisson 18.6%; 5³ grid, 28.8 atoms/voxel) | <11% | PASS |

**Warnings:** C(t) partially decayed: 0% decayed at end of trajectory (τ_relax=3591357585.9 ps vs T_traj=402.0 ps); MSD kinetic trap: chains have not displaced their own size (MSD_max < Rg²) — expected below Tg, problematic in melt state