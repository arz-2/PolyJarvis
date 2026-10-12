## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=300.11 K · 451 frames analysed (skip=50) · 2026-09-09 18:27

**Overall: PASS**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.3078% (p=0.0) | <1%, p<0.01 | PASS |
| Energy drift | 0.0335% (p=0.6674) | <1%, p<0.01 | PASS |
| Energy component drift | bond=0.1729%, angle=0.0982%, dihedral=0.2135%, vdw=0.8274%, coul=0.006%, kspace=0.0028% | <1%, p<0.01 each | PASS |
| Density block-SEM | 0.0441% | <1% | PASS |
| Energy block-SEM | 0.0169% | <1% | PASS |
| τ_eff density | 1.0% of trajectory | — | OK |
| Independent density samples | 96 | ≥20 | PASS |
| Residual deviatoric stress | 366.2 atm von Mises (max |dev| 234.1 atm, z=4.32, resolved) | — | INFO |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 18.0% | <30% | PASS |
| MSID slope (combined) | 1.04 (R²=0.981) | 1.0 ±20% | OK |
| MSID slope (large-s, n=[36, 105]) | 0.857 (R²=0.999) | 1.0 ±20% | OK |
| Torsion JS-divergence (last block-pair) | 0.00011 | ≤0.05 | OK (stable) |
| C(t) τ_relax | 2323077714.7 ps (0% decayed) | — | ⚠ partial |
| MSD kinetic trap | yes (α=0.065, MSD=0.04 Å²>>Rg²=238.458) | — | ⚠ trapped |
| R_ee mean ± std | 37.22 ± 15.43 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0104 ± 0.002 | <0.10 | PASS |
| Finite size | L=40.76 Å · L/2r_cut=2.145 · L/2Rg=1.341 · L/R_ee=1.095 | ≥1.0 | PASS |
| Density homogeneity CV (signal) | 0.0% (raw 17.6% − Poisson 23.7%; 6³ grid, 29.3 atoms/voxel) | <11% | PASS |

**Warnings:** C(t) partially decayed: 0% decayed at end of trajectory (τ_relax=2323077714.7 ps vs T_traj=451.0 ps); MSD kinetic trap: chains have not displaced their own size (MSD_max < Rg²) — expected below Tg, problematic in melt state