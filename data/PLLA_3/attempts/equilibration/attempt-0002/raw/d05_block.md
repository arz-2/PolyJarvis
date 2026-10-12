## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=619.97 K · 1951 frames analysed (skip=50) · 2026-09-12 02:57

**Overall: PASS**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.0559% (p=0.5063) | <1%, p<0.01 | PASS |
| Energy drift | 0.1972% (p=0.0003) | <1%, p<0.01 | PASS |
| Energy component drift | bond=0.1993%, angle=0.6315%, dihedral=1.7694%, vdw=1.1733%, coul=0.0022%, kspace=0.0021% | <1%, p<0.01 each | PASS |
| Density block-SEM | 0.0827% | <1% | PASS |
| Energy block-SEM | 0.0366% | <1% | PASS |
| τ_eff density | 1.6% of trajectory | — | OK |
| Independent density samples | 60 | ≥20 | PASS |
| Residual deviatoric stress | 32.2 atm von Mises (max |dev| 20.9 atm, z=0.6, not resolved (z<2)) | — | INFO |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 24.6% | <30% | PASS |
| MSID slope (combined) | 1.133 (R²=0.9888) | 1.0 ±20% | OK |
| MSID slope (large-s, n=[36, 105]) | 0.943 (R²=0.9985) | 1.0 ±20% | OK |
| Torsion JS-divergence (last block-pair) | 0.00029 | ≤0.05 | OK (stable) |
| C(t) τ_relax | 30686.7 ps (29% decayed) | — | ⚠ partial |
| MSD kinetic trap | no (α=0.261, MSD=626.15 Å²>>Rg²=314.537) | — | OK |
| R_ee mean ± std | 39.7 ± 18.22 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0146 ± 0.0047 | <0.10 | PASS |
| Finite size | L=42.52 Å · L/2r_cut=2.238 · L/2Rg=1.235 · L/R_ee=1.071 | ≥1.0 | PASS |
| Density homogeneity CV (signal) | 0.0% (raw 19.9% − Poisson 23.7%; 6³ grid, 29.3 atoms/voxel) | <11% | PASS |

**Warnings:** C(t) partially decayed: 29% decayed at end of trajectory (τ_relax=30686.7 ps vs T_traj=4951.0 ps)