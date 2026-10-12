## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=300.05 K · 2451 frames analysed (skip=50) · 2026-09-11 18:47

**Overall: FAIL**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.2962% (p=0.0) | <1%, p<0.01 | PASS |
| Energy drift | 1.2409% (p=0.0) | <1%, p<0.01 | FAIL |
| Energy component drift | bond=0.687%, angle=0.1564%, dihedral=1.2112%✗, vdw=0.4493%, coul=0.0%, kspace=0.0% | <1%, p<0.01 each | FAIL |
| Density block-SEM | 0.0512% | <1% | PASS |
| Energy block-SEM | 0.1605% | <1% | PASS |
| τ_eff density | 0.8% of trajectory | — | OK |
| Independent density samples | 122 | ≥20 | PASS |
| Residual deviatoric stress | 23.6 atm von Mises (max |dev| 14.9 atm, z=1.35, not resolved (z<2)) | — | INFO |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 21.8% | <30% | PASS |
| MSID slope (combined) | 1.078 (R²=0.9966) | 1.0 ±20% | OK |
| MSID slope (large-s, n=[61, 180]) | 0.996 (R²=0.9993) | 1.0 ±20% | OK |
| Torsion JS-divergence (last block-pair) | 0.0002 | ≤0.05 | OK (stable) |
| C(t) τ_relax | 410214.8 ps (2% decayed) | — | ⚠ partial |
| MSD kinetic trap | yes (α=0.306, MSD=737.85 Å²>>Rg²=1017.508) | — | ⚠ trapped |
| R_ee mean ± std | 74.0 ± 27.92 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.026 ± 0.0064 | <0.10 | PASS |
| Finite size | L=46.06 Å · L/2r_cut=1.645 · L/2Rg=0.739 · L/R_ee=0.622 | ≥1.0 | SIZE_CHAIN_SELF_IMAGE_ADVISORY |
| Density homogeneity CV (signal) | 0.0% (raw 10.8% − Poisson 18.6%; 5³ grid, 28.8 atoms/voxel) | <11% | PASS |

**Warnings:** C(t) partially decayed: 2% decayed at end of trajectory (τ_relax=410214.8 ps vs T_traj=4902.0 ps); MSD kinetic trap: chains have not displaced their own size (MSD_max < Rg²) — expected below Tg, problematic in melt state