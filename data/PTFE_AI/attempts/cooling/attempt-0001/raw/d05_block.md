## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=299.98 K · 451 frames analysed (skip=50) · 2026-09-14 16:06

**Overall: PASS**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.1923% (p=0.1602) | <1%, p<0.01 | PASS |
| Energy drift | 0.5179% (p=0.3387) | <1%, p<0.01 | PASS |
| Energy component drift | bond=0.1475%, angle=0.0734%, dihedral=0.1247%, vdw=5.0541%, coul=0.0118%, kspace=0.0238% | <1%, p<0.01 each | PASS |
| Density block-SEM | 0.0702% | <1% | PASS |
| Energy block-SEM | 0.1665% | <1% | PASS |
| τ_eff density | 1.3% of trajectory | — | OK |
| Independent density samples | 74 | ≥20 | PASS |
| Residual deviatoric stress | 83.8 atm von Mises (max |dev| 49.6 atm, z=0.87, not resolved (z<2)) | — | INFO |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 18.8% | <30% | PASS |
| MSID slope (combined) | 1.499 (R²=0.9952) | 1.0 ±20% | ⚠ non-Gaussian |
| MSID slope (large-s, n=[18, 51]) | 1.253 (R²=0.9934) | 1.0 ±20% | ⚠ non-Gaussian (large-s) |
| Torsion JS-divergence (last block-pair) | 0.00028 | ≤0.05 | OK (stable) |
| C(t) τ_relax | 4623480818.7 ps (0% decayed) | — | ⚠ partial |
| MSD kinetic trap | yes (α=0.049, MSD=257.22 Å²>>Rg²=267.537) | — | ⚠ trapped |
| R_ee mean ± std | 35.22 ± 13.23 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0251 ± 0.0032 | <0.10 | PASS |
| Finite size | L=34.98 Å · L/2r_cut=1.59 · L/2Rg=1.088 · L/R_ee=0.993 | ≥1.0 | PASS |
| Density homogeneity CV (signal, measured_floor) | 0.0% (raw 15.8% − melt floor 32.7%; 5³ grid, 24.2 atoms/voxel) | <11% | PASS |

**Warnings:** MSID slope = 1.499 (expected 1.0 ±20% for Gaussian chain) — possible chain collapse or extension; C(t) partially decayed: 0% decayed at end of trajectory (τ_relax=4623480818.7 ps vs T_traj=451.0 ps); MSD kinetic trap: chains have not displaced their own size (MSD_max < Rg²) — expected below Tg, problematic in melt state