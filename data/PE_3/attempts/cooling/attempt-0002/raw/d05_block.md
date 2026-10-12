## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=299.37 K · 117 frames analysed (skip=50) · 2026-09-13 14:01

**Overall: PASS**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.5873% (p=0.0022) | <1%, p<0.01 | PASS |
| Energy drift | 1.5087% (p=0.0437) | <1%, p<0.01 | PASS |
| Energy component drift | bond=1.2758%, angle=1.5371%, dihedral=0.8358%, vdw=0.601%, coul=0.0%, kspace=0.0% | <1%, p<0.01 each | PASS |
| Density block-SEM | 0.0733% | <1% | PASS |
| Energy block-SEM | 0.2018% | <1% | PASS |
| τ_eff density | 5.8% of trajectory | — | OK |
| Independent density samples | 17 | ≥20 | FAIL |
| Residual deviatoric stress | 89.1 atm von Mises (max |dev| 52.6 atm, z=1.12, not resolved (z<2)) | — | INFO |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 21.2% | <30% | PASS |
| MSID slope (combined) | 1.145 (R²=0.9973) | 1.0 ±20% | OK |
| MSID slope (large-s, n=[61, 180]) | 1.074 (R²=0.9994) | 1.0 ±20% | OK |
| Torsion JS-divergence (last block-pair) | 0.00024 | ≤0.05 | OK (stable) |
| C(t) τ_relax | 308191658.1 ps (0% decayed) | — | ⚠ partial |
| MSD kinetic trap | yes (α=0.361, MSD=424.79 Å²>>Rg²=1301.128) | — | ⚠ trapped |
| R_ee mean ± std | 81.9 ± 21.26 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0624 ± 0.0046 | <0.10 | PASS |
| Finite size | L=45.8 Å · L/2r_cut=1.636 · L/2Rg=0.649 · L/R_ee=0.559 | ≥1.0 | SIZE_CHAIN_SELF_IMAGE_ADVISORY |
| Density homogeneity CV (signal) | 0.0% (raw 10.6% − Poisson 18.6%; 5³ grid, 28.8 atoms/voxel) | <11% | PASS |

**Warnings:** C(t) partially decayed: 0% decayed at end of trajectory (τ_relax=308191658.1 ps vs T_traj=234.0 ps); MSD kinetic trap: chains have not displaced their own size (MSD_max < Rg²) — expected below Tg, problematic in melt state