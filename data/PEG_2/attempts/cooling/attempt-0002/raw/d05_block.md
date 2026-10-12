## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=300.04 K · 451 frames analysed (skip=50) · 2026-09-13 08:58

**Overall: PASS**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.0962% (p=0.2219) | <1%, p<0.01 | PASS |
| Energy drift | 0.6382% (p=0.1789) | <1%, p<0.01 | PASS |
| Energy component drift | bond=0.7694%, angle=0.1013%, dihedral=0.1369%, vdw=0.0023%, coul=0.1534%✗, kspace=0.074% | <1%, p<0.01 each | FAIL |
| Density block-SEM | 0.0233% | <1% | PASS |
| Energy block-SEM | 0.152% | <1% | PASS |
| τ_eff density | 0.6% of trajectory | — | OK |
| Independent density samples | 167 | ≥20 | PASS |
| Residual deviatoric stress | 63.8 atm von Mises (max |dev| 42.0 atm, z=0.85, not resolved (z<2)) | — | INFO |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 16.0% | <30% | PASS |
| MSID slope (combined) | 1.047 (R²=0.9637) | 1.0 ±20% | OK |
| MSID slope (large-s, n=[58, 171]) | 0.796 (R²=0.9973) | 1.0 ±20% | ⚠ non-Gaussian (large-s) |
| Torsion JS-divergence (last block-pair) | 9e-05 | ≤0.05 | OK (stable) |
| C(t) τ_relax | 3089168332.0 ps (0% decayed) | — | ⚠ partial |
| MSD kinetic trap | yes (α=0.11, MSD=54.03 Å²>>Rg²=591.048) | — | ⚠ trapped |
| R_ee mean ± std | 57.53 ± 17.87 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0192 ± 0.0038 | <0.10 | PASS |
| Finite size | L=42.88 Å · L/2r_cut=2.257 · L/2Rg=0.893 · L/R_ee=0.745 | ≥1.0 | SIZE_CHAIN_SELF_IMAGE_ADVISORY |
| Density homogeneity CV (signal) | 0.0% (raw 20.3% − Poisson 29.2%; 7³ grid, 23.3 atoms/voxel) | <11% | PASS |

**Warnings:** C(t) partially decayed: 0% decayed at end of trajectory (τ_relax=3089168332.0 ps vs T_traj=451.0 ps); MSD kinetic trap: chains have not displaced their own size (MSD_max < Rg²) — expected below Tg, problematic in melt state