## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=499.91 K · 1951 frames analysed (skip=50) · 2026-09-13 08:15

**Overall: PASS**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.066% (p=0.386) | <1%, p<0.01 | PASS |
| Energy drift | 0.1792% (p=0.1283) | <1%, p<0.01 | PASS |
| Energy component drift | bond=0.1513%, angle=0.2376%, dihedral=0.0745%, vdw=0.1627%, coul=0.0826%, kspace=0.0153% | <1%, p<0.01 each | PASS |
| Density block-SEM | 0.028% | <1% | PASS |
| Energy block-SEM | 0.0311% | <1% | PASS |
| τ_eff density | 0.3% of trajectory | — | OK |
| Independent density samples | 297 | ≥20 | PASS |
| Residual deviatoric stress | 100.2 atm von Mises (max |dev| 65.6 atm, z=2.42, resolved) | — | INFO |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 11.9% | <30% | PASS |
| MSID slope (combined) | 1.037 (R²=0.9693) | 1.0 ±20% | OK |
| MSID slope (large-s, n=[58, 171]) | 0.783 (R²=0.9946) | 1.0 ±20% | ⚠ non-Gaussian (large-s) |
| Torsion JS-divergence (last block-pair) | 2e-05 | ≤0.05 | OK (stable) |
| C(t) τ_relax | 98638.5 ps (18% decayed) | — | ⚠ partial |
| MSD kinetic trap | no (α=0.319, MSD=1789.18 Å²>>Rg²=511.139) | — | OK |
| R_ee mean ± std | 45.8 ± 15.5 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0254 ± 0.0079 | <0.10 | PASS |
| Finite size | L=44.89 Å · L/2r_cut=2.363 · L/2Rg=1.001 · L/R_ee=0.98 | ≥1.0 | PASS |
| Density homogeneity CV (signal) | 0.0% (raw 22.4% − Poisson 29.2%; 7³ grid, 23.3 atoms/voxel) | <11% | PASS |

**Warnings:** C(t) partially decayed: 18% decayed at end of trajectory (τ_relax=98638.5 ps vs T_traj=4951.0 ps)