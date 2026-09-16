## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=300.28 K · 451 frames analysed (skip=50) · 2026-09-15 15:38

**Overall: PASS**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.0955% (p=0.2744) | <1%, p<0.01 | PASS |
| Energy drift | 0.1811% (p=0.3108) | <1%, p<0.01 | PASS |
| Energy component drift | bond=0.118%, angle=0.0213%, dihedral=0.3667%, vdw=1.8147%, coul=0.0825%, kspace=0.0392% | <1%, p<0.01 each | PASS |
| Density block-SEM | 0.0172% | <1% | PASS |
| Energy block-SEM | 0.0446% | <1% | PASS |
| τ_eff density | 0.5% of trajectory | — | OK |
| Independent density samples | 212 | ≥20 | PASS |
| Residual deviatoric stress | 232.5 atm von Mises (max |dev| 138.6 atm, z=2.8, resolved) | — | INFO |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 12.4% | <30% | PASS |
| MSID slope (combined) | 1.296 (R²=0.981) | 1.0 ±20% | ⚠ non-Gaussian |
| MSID slope (large-s, n=[19, 52]) | 0.899 (R²=0.9929) | 1.0 ±20% | OK |
| Torsion JS-divergence (last block-pair) | 0.00017 | ≤0.05 | OK (stable) |
| C(t) τ_relax | 2995868512.1 ps (0% decayed) | — | ⚠ partial |
| MSD kinetic trap | yes (α=0.022, MSD=18.0 Å²>>Rg²=218.236) | — | ⚠ trapped |
| R_ee mean ± std | 35.74 ± 9.83 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.021 ± 0.0029 | <0.10 | PASS |
| Finite size | L=44.08 Å · L/2r_cut=2.32 · L/2Rg=1.503 · L/R_ee=1.233 | ≥1.0 | PASS |
| Density homogeneity CV (signal, measured_floor) | 0.0% (raw 24.8% − melt floor 30.4%; 7³ grid, 22.9 atoms/voxel) | <11% | PASS |

**Warnings:** MSID slope = 1.296 (expected 1.0 ±20% for Gaussian chain) — possible chain collapse or extension; C(t) partially decayed: 0% decayed at end of trajectory (τ_relax=2995868512.1 ps vs T_traj=451.0 ps); MSD kinetic trap: chains have not displaced their own size (MSD_max < Rg²) — expected below Tg, problematic in melt state