## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=300.03 K · 1951 frames analysed (skip=50) · 2026-09-13 00:48

**Overall: PASS**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.1446% (p=0.0001) | <1%, p<0.01 | PASS |
| Energy drift | 0.067% (p=0.4495) | <1%, p<0.01 | PASS |
| Energy component drift | bond=0.2081%, angle=0.177%, dihedral=0.1179%, vdw=0.0861%, coul=0.0801%, kspace=0.0273% | <1%, p<0.01 each | PASS |
| Density block-SEM | 0.0392% | <1% | PASS |
| Energy block-SEM | 0.0739% | <1% | PASS |
| τ_eff density | 1.6% of trajectory | — | OK |
| Independent density samples | 62 | ≥20 | PASS |
| Residual deviatoric stress | 42.3 atm von Mises (max |dev| 26.5 atm, z=1.11, not resolved (z<2)) | — | INFO |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 22.0% | <30% | PASS |
| MSID slope (combined) | 1.071 (R²=0.9891) | 1.0 ±20% | OK |
| MSID slope (large-s, n=[51, 150]) | 0.944 (R²=0.9992) | 1.0 ±20% | OK |
| Torsion JS-divergence (last block-pair) | 2e-05 | ≤0.05 | OK (stable) |
| C(t) τ_relax | 35453138.7 ps (2% decayed) | — | ⚠ partial |
| MSD kinetic trap | yes (α=0.225, MSD=185.01 Å²>>Rg²=381.947) | — | ⚠ trapped |
| R_ee mean ± std | 45.95 ± 18.35 Å (N=20 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.009 ± 0.0027 | <0.10 | PASS |
| Finite size | L=50.65 Å · L/2r_cut=2.666 · L/2Rg=1.327 · L/R_ee=1.102 | ≥1.0 | PASS |
| Density homogeneity CV (signal) | 0.0% (raw 18.9% − Poisson 26.9%; 8³ grid, 27.4 atoms/voxel) | <11% | PASS |

**Warnings:** C(t) partially decayed: 2% decayed at end of trajectory (τ_relax=35453138.7 ps vs T_traj=1951.0 ps); MSD kinetic trap: chains have not displaced their own size (MSD_max < Rg²) — expected below Tg, problematic in melt state