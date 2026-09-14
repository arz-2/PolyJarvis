## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=699.73 K · 1951 frames analysed (skip=50) · 2026-09-12 16:23

**Overall: PASS**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.1006% (p=0.2842) | <1%, p<0.01 | PASS |
| Energy drift | 0.1279% (p=0.0659) | <1%, p<0.01 | PASS |
| Energy component drift | bond=0.0673%, angle=0.1624%, dihedral=0.0028%, vdw=1.4274%, coul=0.0616%, kspace=0.0094% | <1%, p<0.01 each | PASS |
| Density block-SEM | 0.0795% | <1% | PASS |
| Energy block-SEM | 0.0194% | <1% | PASS |
| τ_eff density | 0.7% of trajectory | — | OK |
| Independent density samples | 136 | ≥20 | PASS |
| Residual deviatoric stress | 144.1 atm von Mises (max |dev| 96.0 atm, z=2.79, resolved) | — | INFO |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 15.2% | <30% | PASS |
| MSID slope (combined) | 1.094 (R²=0.9563) | 1.0 ±20% | OK |
| MSID slope (large-s, n=[41, 120]) | 0.6 (R²=0.9733) | 1.0 ±20% | ⚠ non-Gaussian (large-s) |
| Torsion JS-divergence (last block-pair) | 3e-05 | ≤0.05 | OK (stable) |
| C(t) τ_relax | 28647.7 ps (22% decayed) | — | ⚠ partial |
| MSD kinetic trap | no (α=0.256, MSD=757.98 Å²>>Rg²=376.977) | — | OK |
| R_ee mean ± std | 41.87 ± 20.67 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0184 ± 0.0061 | <0.10 | PASS |
| Finite size | L=43.76 Å · L/2r_cut=2.303 · L/2Rg=1.141 · L/R_ee=1.045 | ≥1.0 | PASS |
| Density homogeneity CV (signal) | 0.0% (raw 21.5% − Poisson 23.4%; 6³ grid, 30.1 atoms/voxel) | <11% | PASS |

**Warnings:** C(t) partially decayed: 22% decayed at end of trajectory (τ_relax=28647.7 ps vs T_traj=4951.0 ps)