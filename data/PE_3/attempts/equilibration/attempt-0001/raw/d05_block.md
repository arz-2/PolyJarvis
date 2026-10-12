## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=550.34 K · 951 frames analysed (skip=50) · 2026-09-13 12:49

**Overall: PASS**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.0275% (p=0.8758) | <1%, p<0.01 | PASS |
| Energy drift | 0.192% (p=0.2997) | <1%, p<0.01 | PASS |
| Energy component drift | bond=0.1073%, angle=0.1772%, dihedral=0.0223%, vdw=0.1457%, coul=0.0%, kspace=0.0% | <1%, p<0.01 each | PASS |
| Density block-SEM | 0.0489% | <1% | PASS |
| Energy block-SEM | 0.0691% | <1% | PASS |
| τ_eff density | 0.4% of trajectory | — | OK |
| Independent density samples | 264 | ≥20 | PASS |
| Residual deviatoric stress | 39.0 atm von Mises (max |dev| 23.4 atm, z=1.15, not resolved (z<2)) | — | INFO |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 24.4% | <30% | PASS |
| MSID slope (combined) | 1.117 (R²=0.9986) | 1.0 ±20% | OK |
| MSID slope (large-s, n=[61, 180]) | 1.12 (R²=0.9998) | 1.0 ±20% | OK |
| Torsion JS-divergence (last block-pair) | 2e-05 | ≤0.05 | OK (stable) |
| C(t) τ_relax | 1669398.0 ps (16% decayed) | — | ⚠ partial |
| MSD kinetic trap | no (α=0.257, MSD=2330.47 Å²>>Rg²=1206.641) | — | OK |
| R_ee mean ± std | 92.56 ± 32.82 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0167 ± 0.0061 | <0.10 | PASS |
| Finite size | L=48.71 Å · L/2r_cut=1.739 · L/2Rg=0.723 · L/R_ee=0.526 | ≥1.0 | SIZE_CHAIN_SELF_IMAGE_ADVISORY |
| Density homogeneity CV (signal) | 0.0% (raw 14.8% − Poisson 18.6%; 5³ grid, 28.8 atoms/voxel) | <11% | PASS |

**Warnings:** C(t) partially decayed: 16% decayed at end of trajectory (τ_relax=1669398.0 ps vs T_traj=4902.0 ps)