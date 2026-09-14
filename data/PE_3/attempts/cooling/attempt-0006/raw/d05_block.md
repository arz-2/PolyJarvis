## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=299.44 K · 250 frames analysed (skip=50) · 2026-09-13 14:08

**Overall: PASS**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.7246% (p=0.0) | <1%, p<0.01 | PASS |
| Energy drift | 1.0599% (p=0.0705) | <1%, p<0.01 | PASS |
| Energy component drift | bond=0.5309%, angle=0.1526%, dihedral=3.0183%✗, vdw=0.7684%✗, coul=0.0%, kspace=0.0% | <1%, p<0.01 each | FAIL |
| Density block-SEM | 0.0946% | <1% | PASS |
| Energy block-SEM | 0.2099% | <1% | PASS |
| τ_eff density | 5.6% of trajectory | — | OK |
| Independent density samples | 17 | ≥20 | FAIL |
| Residual deviatoric stress | 84.6 atm von Mises (max |dev| 55.5 atm, z=1.54, not resolved (z<2)) | — | INFO |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 21.0% | <30% | PASS |
| MSID slope (combined) | 1.146 (R²=0.9975) | 1.0 ±20% | OK |
| MSID slope (large-s, n=[61, 180]) | 1.073 (R²=0.9994) | 1.0 ±20% | OK |
| Torsion JS-divergence (last block-pair) | 0.00018 | ≤0.05 | OK (stable) |
| C(t) τ_relax | 254549.2 ps (0% decayed) | — | ⚠ partial |
| MSD kinetic trap | yes (α=0.289, MSD=277.06 Å²>>Rg²=1294.7) | — | ⚠ trapped |
| R_ee mean ± std | 82.41 ± 20.72 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0574 ± 0.0045 | <0.10 | PASS |
| Finite size | L=45.83 Å · L/2r_cut=1.637 · L/2Rg=0.651 · L/R_ee=0.556 | ≥1.0 | SIZE_CHAIN_SELF_IMAGE_ADVISORY |
| Density homogeneity CV (signal) | 0.0% (raw 10.5% − Poisson 18.6%; 5³ grid, 28.8 atoms/voxel) | <11% | PASS |

**Warnings:** C(t) partially decayed: 0% decayed at end of trajectory (τ_relax=254549.2 ps vs T_traj=500.0 ps); MSD kinetic trap: chains have not displaced their own size (MSD_max < Rg²) — expected below Tg, problematic in melt state