## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=620.2 K · 1951 frames analysed (skip=50) · 2026-09-09 09:04

**Overall: PASS**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.7811% (p=0.0) | <1%, p<0.01 | PASS |
| Energy drift | 0.227% (p=0.0) | <1%, p<0.01 | PASS |
| Energy component drift | bond=0.2467%, angle=0.0746%, dihedral=0.8147%, vdw=0.7627%, coul=0.0415%, kspace=0.0078% | <1%, p<0.01 each | PASS |
| Density block-SEM | 0.1194% | <1% | PASS |
| Energy block-SEM | 0.0329% | <1% | PASS |
| τ_eff density | 1.1% of trajectory | — | OK |
| Independent density samples | 87 | ≥20 | PASS |
| Residual deviatoric stress | 34.8 atm von Mises (max |dev| 22.5 atm, z=0.64, not resolved (z<2)) | — | INFO |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 18.4% | <30% | PASS |
| MSID slope (combined) | 1.034 (R²=0.9771) | 1.0 ±20% | OK |
| MSID slope (large-s, n=[36, 105]) | 0.799 (R²=0.9925) | 1.0 ±20% | ⚠ non-Gaussian (large-s) |
| Torsion JS-divergence (last block-pair) | 8e-05 | ≤0.05 | OK (stable) |
| C(t) τ_relax | 872660.3 ps (12% decayed) | — | ⚠ partial |
| MSD kinetic trap | no (α=0.368, MSD=736.13 Å²>>Rg²=238.4) | — | OK |
| R_ee mean ± std | 36.85 ± 15.16 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0138 ± 0.0046 | <0.10 | PASS |
| Finite size | L=42.31 Å · L/2r_cut=2.227 · L/2Rg=1.394 · L/R_ee=1.148 | ≥1.0 | PASS |
| Density homogeneity CV (signal) | 0.0% (raw 19.9% − Poisson 23.7%; 6³ grid, 29.3 atoms/voxel) | <11% | PASS |

**Warnings:** C(t) partially decayed: 12% decayed at end of trajectory (τ_relax=872660.3 ps vs T_traj=4951.0 ps)