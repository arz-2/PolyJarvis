## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=300.21 K · 1951 frames analysed (skip=50) · 2026-09-12 03:50

**Overall: PASS**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.1252% (p=0.0042) | <1%, p<0.01 | PASS |
| Energy drift | 0.7495% (p=0.0011) | <1%, p<0.01 | PASS |
| Energy component drift | bond=0.2105%, angle=0.1637%, dihedral=0.1845%, vdw=0.0417%, coul=0.1675%✗, kspace=0.0029% | <1%, p<0.01 each | FAIL |
| Density block-SEM | 0.0496% | <1% | PASS |
| Energy block-SEM | 0.187% | <1% | PASS |
| τ_eff density | 1.3% of trajectory | — | OK |
| Independent density samples | 74 | ≥20 | PASS |
| Residual deviatoric stress | 106.7 atm von Mises (max |dev| 69.8 atm, z=2.78, resolved) | — | INFO |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 23.3% | <30% | PASS |
| MSID slope (combined) | 0.998 (R²=0.9494) | 1.0 ±20% | OK |
| MSID slope (large-s, n=[58, 171]) | 0.71 (R²=0.9814) | 1.0 ±20% | ⚠ non-Gaussian (large-s) |
| Torsion JS-divergence (last block-pair) | 7e-05 | ≤0.05 | OK (stable) |
| C(t) τ_relax | 505764.6 ps (2% decayed) | — | ⚠ partial |
| MSD kinetic trap | yes (α=0.187, MSD=207.93 Å²>>Rg²=606.862) | — | ⚠ trapped |
| R_ee mean ± std | 63.96 ± 35.96 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0517 ± 0.0043 | <0.10 | PASS |
| Finite size | L=42.88 Å · L/2r_cut=2.257 · L/2Rg=0.894 · L/R_ee=0.67 | ≥1.0 | SIZE_CHAIN_SELF_IMAGE_ADVISORY |
| Density homogeneity CV (signal) | 0.0% (raw 20.1% − Poisson 29.2%; 7³ grid, 23.3 atoms/voxel) | <11% | PASS |

**Warnings:** C(t) partially decayed: 2% decayed at end of trajectory (τ_relax=505764.6 ps vs T_traj=1951.0 ps); MSD kinetic trap: chains have not displaced their own size (MSD_max < Rg²) — expected below Tg, problematic in melt state