## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=299.99 K · 451 frames analysed (skip=50) · 2026-09-13 04:23

**Overall: PASS**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.2371% (p=0.0006) | <1%, p<0.01 | PASS |
| Energy drift | 0.0702% (p=0.4316) | <1%, p<0.01 | PASS |
| Energy component drift | bond=0.0075%, angle=0.2645%, dihedral=0.405%, vdw=0.9298%, coul=0.0618%, kspace=0.0144% | <1%, p<0.01 each | PASS |
| Density block-SEM | 0.0361% | <1% | PASS |
| Energy block-SEM | 0.023% | <1% | PASS |
| τ_eff density | 0.7% of trajectory | — | OK |
| Independent density samples | 135 | ≥20 | PASS |
| Residual deviatoric stress | 195.8 atm von Mises (max |dev| 119.0 atm, z=2.25, resolved) | — | INFO |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 23.5% | <30% | PASS |
| MSID slope (combined) | 1.292 (R²=0.9847) | 1.0 ±20% | ⚠ non-Gaussian |
| MSID slope (large-s, n=[46, 135]) | 0.977 (R²=0.9969) | 1.0 ±20% | OK |
| Torsion JS-divergence (last block-pair) | 5e-05 | ≤0.05 | OK (stable) |
| C(t) τ_relax | 2025375602.8 ps (0% decayed) | — | ⚠ partial |
| MSD kinetic trap | yes (α=0.003, MSD=97.27 Å²>>Rg²=744.017) | — | ⚠ trapped |
| R_ee mean ± std | 64.38 ± 26.86 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0417 ± 0.0023 | <0.10 | PASS |
| Finite size | L=41.53 Å · L/2r_cut=2.186 · L/2Rg=0.782 · L/R_ee=0.645 | ≥1.0 | SIZE_CHAIN_SELF_IMAGE_ADVISORY |
| Density homogeneity CV (signal) | 0.0% (raw 16.4% − Poisson 22.5%; 6³ grid, 28.4 atoms/voxel) | <11% | PASS |

**Warnings:** MSID slope = 1.292 (expected 1.0 ±20% for Gaussian chain) — possible chain collapse or extension; C(t) partially decayed: 0% decayed at end of trajectory (τ_relax=2025375602.8 ps vs T_traj=451.0 ps); MSD kinetic trap: chains have not displaced their own size (MSD_max < Rg²) — expected below Tg, problematic in melt state