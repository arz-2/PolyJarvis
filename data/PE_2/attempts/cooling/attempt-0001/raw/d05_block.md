## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=300.0 K · 2451 frames analysed (skip=50) · 2026-09-13 11:31

**Overall: FAIL**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.4609% (p=0.0) | <1%, p<0.01 | PASS |
| Energy drift | 2.0656% (p=0.0) | <1%, p<0.01 | FAIL |
| Energy component drift | bond=0.4499%, angle=0.0169%, dihedral=2.0468%✗, vdw=0.6937%✗, coul=0.0%, kspace=0.0% | <1%, p<0.01 each | FAIL |
| Density block-SEM | 0.0711% | <1% | PASS |
| Energy block-SEM | 0.2509% | <1% | PASS |
| τ_eff density | 2.0% of trajectory | — | OK |
| Independent density samples | 50 | ≥20 | PASS |
| Residual deviatoric stress | 47.9 atm von Mises (max |dev| 31.8 atm, z=2.86, resolved) | — | INFO |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 26.1% | <30% | PASS |
| MSID slope (combined) | 1.076 (R²=0.9929) | 1.0 ±20% | OK |
| MSID slope (large-s, n=[61, 180]) | 0.913 (R²=0.9986) | 1.0 ±20% | OK |
| Torsion JS-divergence (last block-pair) | 4e-05 | ≤0.05 | OK (stable) |
| C(t) τ_relax | 109419.2 ps (3% decayed) | — | ⚠ partial |
| MSD kinetic trap | yes (α=0.33, MSD=324.01 Å²>>Rg²=981.657) | — | ⚠ trapped |
| R_ee mean ± std | 68.51 ± 31.27 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0184 ± 0.0049 | <0.10 | PASS |
| Finite size | L=46.08 Å · L/2r_cut=1.646 · L/2Rg=0.76 · L/R_ee=0.673 | ≥1.0 | SIZE_CHAIN_SELF_IMAGE_ADVISORY |
| Density homogeneity CV (signal) | 0.0% (raw 10.7% − Poisson 18.6%; 5³ grid, 28.8 atoms/voxel) | <11% | PASS |

**Warnings:** C(t) partially decayed: 3% decayed at end of trajectory (τ_relax=109419.2 ps vs T_traj=4902.0 ps); MSD kinetic trap: chains have not displaced their own size (MSD_max < Rg²) — expected below Tg, problematic in melt state