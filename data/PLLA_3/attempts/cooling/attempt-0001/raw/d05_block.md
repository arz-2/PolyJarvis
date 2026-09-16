## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=299.97 K · 451 frames analysed (skip=50) · 2026-09-12 07:48

**Overall: PASS**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.116% (p=0.1223) | <1%, p<0.01 | PASS |
| Energy drift | 0.0348% (p=0.6756) | <1%, p<0.01 | PASS |
| Energy component drift | bond=0.3239%, angle=0.2088%, dihedral=0.1097%, vdw=0.0142%, coul=0.0127%, kspace=0.0003% | <1%, p<0.01 each | PASS |
| Density block-SEM | 0.0444% | <1% | PASS |
| Energy block-SEM | 0.0149% | <1% | PASS |
| τ_eff density | 2.9% of trajectory | — | OK |
| Independent density samples | 33 | ≥20 | PASS |
| Residual deviatoric stress | 209.6 atm von Mises (max |dev| 131.3 atm, z=2.31, resolved) | — | INFO |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 25.6% | <30% | PASS |
| MSID slope (combined) | 1.117 (R²=0.9887) | 1.0 ±20% | OK |
| MSID slope (large-s, n=[36, 105]) | 0.947 (R²=0.9985) | 1.0 ±20% | OK |
| Torsion JS-divergence (last block-pair) | 8e-05 | ≤0.05 | OK (stable) |
| C(t) τ_relax | 2568956340.3 ps (0% decayed) | — | ⚠ partial |
| MSD kinetic trap | yes (α=0.074, MSD=0.04 Å²>>Rg²=300.472) | — | ⚠ trapped |
| R_ee mean ± std | 41.75 ± 19.3 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0181 ± 0.002 | <0.10 | PASS |
| Finite size | L=40.85 Å · L/2r_cut=2.15 · L/2Rg=1.216 · L/R_ee=0.978 | ≥1.0 | PASS |
| Density homogeneity CV (signal) | 0.0% (raw 18.0% − Poisson 23.7%; 6³ grid, 29.3 atoms/voxel) | <11% | PASS |

**Warnings:** C(t) partially decayed: 0% decayed at end of trajectory (τ_relax=2568956340.3 ps vs T_traj=451.0 ps); MSD kinetic trap: chains have not displaced their own size (MSD_max < Rg²) — expected below Tg, problematic in melt state