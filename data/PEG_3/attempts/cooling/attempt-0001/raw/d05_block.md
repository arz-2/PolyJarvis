## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=299.79 K · 1951 frames analysed (skip=50) · 2026-09-13 10:50

**Overall: PASS**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.0447% (p=0.2721) | <1%, p<0.01 | PASS |
| Energy drift | 0.5885% (p=0.0093) | <1%, p<0.01 | PASS |
| Energy component drift | bond=0.1561%, angle=0.3738%, dihedral=0.116%, vdw=0.3%, coul=0.0056%, kspace=0.0045% | <1%, p<0.01 each | PASS |
| Density block-SEM | 0.0226% | <1% | PASS |
| Energy block-SEM | 0.0876% | <1% | PASS |
| τ_eff density | 0.7% of trajectory | — | OK |
| Independent density samples | 142 | ≥20 | PASS |
| Residual deviatoric stress | 234.7 atm von Mises (max |dev| 140.4 atm, z=5.33, resolved) | — | INFO |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 14.4% | <30% | PASS |
| MSID slope (combined) | 1.036 (R²=0.9629) | 1.0 ±20% | OK |
| MSID slope (large-s, n=[58, 171]) | 0.755 (R²=0.994) | 1.0 ±20% | ⚠ non-Gaussian (large-s) |
| Torsion JS-divergence (last block-pair) | 8e-05 | ≤0.05 | OK (stable) |
| C(t) τ_relax | 2486158631.1 ps (0% decayed) | — | ⚠ partial |
| MSD kinetic trap | yes (α=-0.018, MSD=19.91 Å²>>Rg²=563.485) | — | ⚠ trapped |
| R_ee mean ± std | 61.71 ± 18.45 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0546 ± 0.004 | <0.10 | PASS |
| Finite size | L=42.88 Å · L/2r_cut=2.257 · L/2Rg=0.913 · L/R_ee=0.695 | ≥1.0 | SIZE_CHAIN_SELF_IMAGE_ADVISORY |
| Density homogeneity CV (signal) | 0.0% (raw 20.0% − Poisson 29.2%; 7³ grid, 23.3 atoms/voxel) | <11% | PASS |

**Warnings:** C(t) partially decayed: 0% decayed at end of trajectory (τ_relax=2486158631.1 ps vs T_traj=1951.0 ps); MSD kinetic trap: chains have not displaced their own size (MSD_max < Rg²) — expected below Tg, problematic in melt state