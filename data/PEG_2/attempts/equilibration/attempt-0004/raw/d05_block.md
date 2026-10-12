## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=500.05 K · 1951 frames analysed (skip=50) · 2026-09-13 05:54

**Overall: PASS**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.1138% (p=0.1383) | <1%, p<0.01 | PASS |
| Energy drift | 0.0405% (p=0.7179) | <1%, p<0.01 | PASS |
| Energy component drift | bond=0.1558%, angle=0.0877%, dihedral=0.0508%, vdw=0.2561%, coul=0.1431%, kspace=0.0382% | <1%, p<0.01 each | PASS |
| Density block-SEM | 0.037% | <1% | PASS |
| Energy block-SEM | 0.0413% | <1% | PASS |
| τ_eff density | 0.3% of trajectory | — | OK |
| Independent density samples | 321 | ≥20 | PASS |
| Residual deviatoric stress | 48.3 atm von Mises (max |dev| 32.1 atm, z=1.15, not resolved (z<2)) | — | INFO |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 16.4% | <30% | PASS |
| MSID slope (combined) | 1.088 (R²=0.9758) | 1.0 ±20% | OK |
| MSID slope (large-s, n=[58, 171]) | 0.843 (R²=0.9991) | 1.0 ±20% | OK |
| Torsion JS-divergence (last block-pair) | 2e-05 | ≤0.05 | OK (stable) |
| C(t) τ_relax | 36426.9 ps (22% decayed) | — | ⚠ partial |
| MSD kinetic trap | no (α=0.309, MSD=1633.45 Å²>>Rg²=586.697) | — | OK |
| R_ee mean ± std | 50.57 ± 19.99 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0183 ± 0.0062 | <0.10 | PASS |
| Finite size | L=44.63 Å · L/2r_cut=2.349 · L/2Rg=0.935 · L/R_ee=0.882 | ≥1.0 | SIZE_CHAIN_SELF_IMAGE_ADVISORY |
| Density homogeneity CV (signal) | 0.0% (raw 22.4% − Poisson 29.2%; 7³ grid, 23.3 atoms/voxel) | <11% | PASS |

**Warnings:** C(t) partially decayed: 22% decayed at end of trajectory (τ_relax=36426.9 ps vs T_traj=4951.0 ps)