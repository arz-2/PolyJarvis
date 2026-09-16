## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=300.0 K · 451 frames analysed (skip=50) · 2026-09-11 06:52

**Overall: PASS**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.3903% (p=0.0) | <1%, p<0.01 | PASS |
| Energy drift | 0.0457% (p=0.5649) | <1%, p<0.01 | PASS |
| Energy component drift | bond=0.2982%, angle=0.3587%, dihedral=0.0741%, vdw=0.6111%, coul=0.0219%, kspace=0.0005% | <1%, p<0.01 each | PASS |
| Density block-SEM | 0.0504% | <1% | PASS |
| Energy block-SEM | 0.022% | <1% | PASS |
| τ_eff density | 1.7% of trajectory | — | OK |
| Independent density samples | 58 | ≥20 | PASS |
| Residual deviatoric stress | 452.8 atm von Mises (max |dev| 280.9 atm, z=5.33, resolved) | — | INFO |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 21.8% | <30% | PASS |
| MSID slope (combined) | 1.111 (R²=0.9922) | 1.0 ±20% | OK |
| MSID slope (large-s, n=[36, 105]) | 1.051 (R²=0.9991) | 1.0 ±20% | OK |
| Torsion JS-divergence (last block-pair) | 4e-05 | ≤0.05 | OK (stable) |
| C(t) τ_relax | 2915577925.7 ps (0% decayed) | — | ⚠ partial |
| MSD kinetic trap | yes (α=0.04, MSD=109.44 Å²>>Rg²=289.914) | — | ⚠ trapped |
| R_ee mean ± std | 39.3 ± 17.36 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0097 ± 0.0019 | <0.10 | PASS |
| Finite size | L=40.93 Å · L/2r_cut=2.154 · L/2Rg=1.23 · L/R_ee=1.041 | ≥1.0 | PASS |
| Density homogeneity CV (signal) | 0.0% (raw 18.6% − Poisson 23.7%; 6³ grid, 29.3 atoms/voxel) | <11% | PASS |

**Warnings:** C(t) partially decayed: 0% decayed at end of trajectory (τ_relax=2915577925.7 ps vs T_traj=451.0 ps); MSD kinetic trap: chains have not displaced their own size (MSD_max < Rg²) — expected below Tg, problematic in melt state