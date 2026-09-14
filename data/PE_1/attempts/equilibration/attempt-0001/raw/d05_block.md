## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=549.72 K · 951 frames analysed (skip=50) · 2026-09-11 17:43

**Overall: PASS**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.2812% (p=0.114) | <1%, p<0.01 | PASS |
| Energy drift | 0.292% (p=0.115) | <1%, p<0.01 | PASS |
| Energy component drift | bond=0.7212%, angle=0.3224%, dihedral=0.1525%, vdw=0.3984%, coul=0.0%, kspace=0.0% | <1%, p<0.01 each | PASS |
| Density block-SEM | 0.0762% | <1% | PASS |
| Energy block-SEM | 0.0588% | <1% | PASS |
| τ_eff density | 0.4% of trajectory | — | OK |
| Independent density samples | 245 | ≥20 | PASS |
| Residual deviatoric stress | 71.3 atm von Mises (max |dev| 46.8 atm, z=2.43, resolved) | — | INFO |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 23.4% | <30% | PASS |
| MSID slope (combined) | 1.117 (R²=0.9981) | 1.0 ±20% | OK |
| MSID slope (large-s, n=[61, 180]) | 1.053 (R²=0.9999) | 1.0 ±20% | OK |
| Torsion JS-divergence (last block-pair) | 2e-05 | ≤0.05 | OK (stable) |
| C(t) τ_relax | 10456.3 ps (32% decayed) | — | ⚠ partial |
| MSD kinetic trap | no (α=0.285, MSD=2080.05 Å²>>Rg²=1058.198) | — | OK |
| R_ee mean ± std | 80.68 ± 25.62 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0268 ± 0.0073 | <0.10 | PASS |
| Finite size | L=48.82 Å · L/2r_cut=1.744 · L/2Rg=0.773 · L/R_ee=0.605 | ≥1.0 | SIZE_CHAIN_SELF_IMAGE_ADVISORY |
| Density homogeneity CV (signal) | 0.0% (raw 14.7% − Poisson 18.6%; 5³ grid, 28.8 atoms/voxel) | <11% | PASS |

**Warnings:** C(t) partially decayed: 32% decayed at end of trajectory (τ_relax=10456.3 ps vs T_traj=4902.0 ps)