## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=299.88 K · 451 frames analysed (skip=50) · 2026-09-12 22:50

**Overall: PASS**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.059% (p=0.4731) | <1%, p<0.01 | PASS |
| Energy drift | 0.1958% (p=0.2455) | <1%, p<0.01 | PASS |
| Energy component drift | bond=0.3487%, angle=0.956%, dihedral=0.7055%, vdw=0.7793%, coul=0.076%, kspace=0.0009% | <1%, p<0.01 each | PASS |
| Density block-SEM | 0.0349% | <1% | PASS |
| Energy block-SEM | 0.0333% | <1% | PASS |
| τ_eff density | 0.4% of trajectory | — | OK |
| Independent density samples | 239 | ≥20 | PASS |
| Residual deviatoric stress | 124.5 atm von Mises (max |dev| 73.3 atm, z=1.43, not resolved (z<2)) | — | INFO |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 13.0% | <30% | PASS |
| MSID slope (combined) | 1.279 (R²=0.9793) | 1.0 ±20% | ⚠ non-Gaussian |
| MSID slope (large-s, n=[19, 52]) | 0.878 (R²=0.9949) | 1.0 ±20% | OK |
| Torsion JS-divergence (last block-pair) | 8e-05 | ≤0.05 | OK (stable) |
| C(t) τ_relax | 4694763905.8 ps (0% decayed) | — | ⚠ partial |
| MSD kinetic trap | yes (α=0.039, MSD=39.51 Å²>>Rg²=202.629) | — | ⚠ trapped |
| R_ee mean ± std | 29.91 ± 10.56 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0461 ± 0.0028 | <0.10 | PASS |
| Finite size | L=44.08 Å · L/2r_cut=2.32 · L/2Rg=1.561 · L/R_ee=1.474 | ≥1.0 | PASS |
| Density homogeneity CV (signal) | 0.0% (raw 24.2% − Poisson 27.4%; 7³ grid, 22.9 atoms/voxel) | <11% | PASS |

**Warnings:** MSID slope = 1.279 (expected 1.0 ±20% for Gaussian chain) — possible chain collapse or extension; C(t) partially decayed: 0% decayed at end of trajectory (τ_relax=4694763905.8 ps vs T_traj=451.0 ps); MSD kinetic trap: chains have not displaced their own size (MSD_max < Rg²) — expected below Tg, problematic in melt state