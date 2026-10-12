## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=299.99 K · 1951 frames analysed (skip=50) · 2026-09-15 05:30

**Overall: PASS**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.183% (p=0.0003) | <1%, p<0.01 | PASS |
| Energy drift | 0.4977% (p=0.0) | <1%, p<0.01 | PASS |
| Energy component drift | bond=0.0296%, angle=0.0278%, dihedral=0.4881%, vdw=0.3152%, coul=0.0488%, kspace=0.0907% | <1%, p<0.01 each | PASS |
| Density block-SEM | 0.0593% | <1% | PASS |
| Energy block-SEM | 0.0726% | <1% | PASS |
| τ_eff density | 1.6% of trajectory | — | OK |
| Independent density samples | 63 | ≥20 | PASS |
| Residual deviatoric stress | 44.5 atm von Mises (max |dev| 29.1 atm, z=1.13, not resolved (z<2)) | — | INFO |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 15.1% | <30% | PASS |
| MSID slope (combined) | 1.09 (R²=0.991) | 1.0 ±20% | OK |
| MSID slope (large-s, n=[58, 171]) | 0.924 (R²=0.9962) | 1.0 ±20% | OK |
| Torsion JS-divergence (last block-pair) | 0.00015 | ≤0.05 | OK (stable) |
| C(t) τ_relax | 302786.2 ps (2% decayed) | — | ⚠ partial |
| MSD kinetic trap | yes (α=0.197, MSD=254.0 Å²>>Rg²=445.595) | — | ⚠ trapped |
| R_ee mean ± std | 45.73 ± 16.4 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0128 ± 0.004 | <0.10 | PASS |
| Finite size | L=42.07 Å · L/2r_cut=2.214 · L/2Rg=1.008 · L/R_ee=0.92 | ≥1.0 | PASS |
| Density homogeneity CV (signal) | 0.0% (raw 20.5% − Poisson 29.2%; 7³ grid, 23.3 atoms/voxel) | <11% | PASS |

**Warnings:** C(t) partially decayed: 2% decayed at end of trajectory (τ_relax=302786.2 ps vs T_traj=1951.0 ps); MSD kinetic trap: chains have not displaced their own size (MSD_max < Rg²) — expected below Tg, problematic in melt state