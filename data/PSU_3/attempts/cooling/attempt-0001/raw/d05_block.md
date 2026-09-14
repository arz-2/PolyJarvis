## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=299.9 K · 451 frames analysed (skip=50) · 2026-09-13 05:39

**Overall: PASS**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.0076% (p=0.92) | <1%, p<0.01 | PASS |
| Energy drift | 0.1684% (p=0.2161) | <1%, p<0.01 | PASS |
| Energy component drift | bond=0.2215%, angle=0.2805%, dihedral=0.2072%, vdw=1.304%, coul=0.0301%, kspace=0.0056% | <1%, p<0.01 each | PASS |
| Density block-SEM | 0.0444% | <1% | PASS |
| Energy block-SEM | 0.0508% | <1% | PASS |
| τ_eff density | 0.9% of trajectory | — | OK |
| Independent density samples | 117 | ≥20 | PASS |
| Residual deviatoric stress | 413.9 atm von Mises (max |dev| 261.0 atm, z=4.51, resolved) | — | INFO |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 15.6% | <30% | PASS |
| MSID slope (combined) | 1.125 (R²=0.9723) | 1.0 ±20% | OK |
| MSID slope (large-s, n=[41, 120]) | 0.834 (R²=0.9936) | 1.0 ±20% | OK |
| Torsion JS-divergence (last block-pair) | 6e-05 | ≤0.05 | OK (stable) |
| C(t) τ_relax | 2612872420.4 ps (0% decayed) | — | ⚠ partial |
| MSD kinetic trap | yes (α=0.027, MSD=129.97 Å²>>Rg²=388.332) | — | ⚠ trapped |
| R_ee mean ± std | 43.78 ± 15.53 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0089 ± 0.0021 | <0.10 | PASS |
| Finite size | L=42.11 Å · L/2r_cut=2.216 · L/2Rg=1.081 · L/R_ee=0.962 | ≥1.0 | PASS |
| Density homogeneity CV (signal) | 0.0% (raw 17.8% − Poisson 23.4%; 6³ grid, 30.1 atoms/voxel) | <11% | PASS |

**Warnings:** C(t) partially decayed: 0% decayed at end of trajectory (τ_relax=2612872420.4 ps vs T_traj=451.0 ps); MSD kinetic trap: chains have not displaced their own size (MSD_max < Rg²) — expected below Tg, problematic in melt state