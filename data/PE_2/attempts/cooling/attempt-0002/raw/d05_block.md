## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=300.37 K · 201 frames analysed (skip=50) · 2026-09-13 11:45

**Overall: PASS**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.2626% (p=0.0915) | <1%, p<0.01 | PASS |
| Energy drift | 0.1135% (p=0.8631) | <1%, p<0.01 | PASS |
| Energy component drift | bond=0.374%, angle=0.0686%, dihedral=0.1099%, vdw=0.2145%, coul=0.0%, kspace=0.0% | <1%, p<0.01 each | PASS |
| Density block-SEM | 0.0686% | <1% | PASS |
| Energy block-SEM | 0.1648% | <1% | PASS |
| τ_eff density | 1.7% of trajectory | — | OK |
| Independent density samples | 59 | ≥20 | PASS |
| Residual deviatoric stress | 38.3 atm von Mises (max |dev| 25.3 atm, z=0.66, not resolved (z<2)) | — | INFO |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 25.7% | <30% | PASS |
| MSID slope (combined) | 1.078 (R²=0.9933) | 1.0 ±20% | OK |
| MSID slope (large-s, n=[61, 180]) | 0.921 (R²=0.9979) | 1.0 ±20% | OK |
| Torsion JS-divergence (last block-pair) | 0.00018 | ≤0.05 | OK (stable) |
| C(t) τ_relax | 78330976.6 ps (0% decayed) | — | ⚠ partial |
| MSD kinetic trap | yes (α=0.331, MSD=0.26 Å²>>Rg²=984.948) | — | ⚠ trapped |
| R_ee mean ± std | 69.07 ± 29.91 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0189 ± 0.0036 | <0.10 | PASS |
| Finite size | L=46.0 Å · L/2r_cut=1.643 · L/2Rg=0.757 · L/R_ee=0.666 | ≥1.0 | SIZE_CHAIN_SELF_IMAGE_ADVISORY |
| Density homogeneity CV (signal) | 0.0% (raw 10.6% − Poisson 18.6%; 5³ grid, 28.8 atoms/voxel) | <11% | PASS |

**Warnings:** C(t) partially decayed: 0% decayed at end of trajectory (τ_relax=78330976.6 ps vs T_traj=402.0 ps); MSD kinetic trap: chains have not displaced their own size (MSD_max < Rg²) — expected below Tg, problematic in melt state