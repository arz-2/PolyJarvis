## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=299.77 K · 451 frames analysed (skip=50) · 2026-09-12 19:16

**Overall: PASS**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.0233% (p=0.7822) | <1%, p<0.01 | PASS |
| Energy drift | 0.1282% (p=0.3281) | <1%, p<0.01 | PASS |
| Energy component drift | bond=0.2299%, angle=0.0432%, dihedral=0.3698%, vdw=3.34%, coul=0.0509%, kspace=0.024% | <1%, p<0.01 each | PASS |
| Density block-SEM | 0.0436% | <1% | PASS |
| Energy block-SEM | 0.0509% | <1% | PASS |
| τ_eff density | 2.0% of trajectory | — | OK |
| Independent density samples | 50 | ≥20 | PASS |
| Residual deviatoric stress | 165.1 atm von Mises (max |dev| 108.1 atm, z=2.16, resolved) | — | INFO |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 18.4% | <30% | PASS |
| MSID slope (combined) | 1.071 (R²=0.9507) | 1.0 ±20% | OK |
| MSID slope (large-s, n=[41, 120]) | 0.543 (R²=0.9598) | 1.0 ±20% | ⚠ non-Gaussian (large-s) |
| Torsion JS-divergence (last block-pair) | 8e-05 | ≤0.05 | OK (stable) |
| C(t) τ_relax | 5132979791.7 ps (0% decayed) | — | ⚠ partial |
| MSD kinetic trap | yes (α=0.096, MSD=184.76 Å²>>Rg²=336.568) | — | ⚠ trapped |
| R_ee mean ± std | 34.87 ± 15.23 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0104 ± 0.0022 | <0.10 | PASS |
| Finite size | L=41.96 Å · L/2r_cut=2.208 · L/2Rg=1.163 · L/R_ee=1.203 | ≥1.0 | PASS |
| Density homogeneity CV (signal) | 0.0% (raw 18.2% − Poisson 23.4%; 6³ grid, 30.1 atoms/voxel) | <11% | PASS |

**Warnings:** C(t) partially decayed: 0% decayed at end of trajectory (τ_relax=5132979791.7 ps vs T_traj=451.0 ps); MSD kinetic trap: chains have not displaced their own size (MSD_max < Rg²) — expected below Tg, problematic in melt state