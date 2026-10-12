## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=499.78 K · 1951 frames analysed (skip=50) · 2026-09-15 02:50

**Overall: PASS**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.1104% (p=0.2322) | <1%, p<0.01 | PASS |
| Energy drift | 0.0314% (p=0.7171) | <1%, p<0.01 | PASS |
| Energy component drift | bond=0.1072%, angle=0.0157%, dihedral=0.0295%, vdw=0.4401%, coul=0.0343%, kspace=0.0031% | <1%, p<0.01 each | PASS |
| Density block-SEM | 0.0599% | <1% | PASS |
| Energy block-SEM | 0.0229% | <1% | PASS |
| τ_eff density | 0.4% of trajectory | — | OK |
| Independent density samples | 275 | ≥20 | PASS |
| Residual deviatoric stress | 24.8 atm von Mises (max |dev| 14.5 atm, z=0.51, not resolved (z<2)) | — | INFO |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 14.5% | <30% | PASS |
| MSID slope (combined) | 1.111 (R²=0.9919) | 1.0 ±20% | OK |
| MSID slope (large-s, n=[58, 171]) | 0.971 (R²=0.9987) | 1.0 ±20% | OK |
| Torsion JS-divergence (last block-pair) | 3e-05 | ≤0.05 | OK (stable) |
| C(t) τ_relax | 17067.4 ps (39% decayed) | — | ⚠ partial |
| MSD kinetic trap | no (α=0.303, MSD=1426.47 Å²>>Rg²=479.397) | — | OK |
| R_ee mean ± std | 48.72 ± 18.94 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0122 ± 0.0044 | <0.10 | PASS |
| Finite size | L=44.2 Å · L/2r_cut=2.326 · L/2Rg=1.022 · L/R_ee=0.907 | ≥1.0 | PASS |
| Density homogeneity CV (signal) | 0.0% (raw 23.5% − Poisson 29.2%; 7³ grid, 23.3 atoms/voxel) | <11% | PASS |

**Warnings:** C(t) partially decayed: 39% decayed at end of trajectory (τ_relax=17067.4 ps vs T_traj=4951.0 ps)