## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=700.09 K · 1951 frames analysed (skip=50) · 2026-09-13 02:48

**Overall: PASS**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.2644% (p=0.0137) | <1%, p<0.01 | PASS |
| Energy drift | 0.1105% (p=0.1154) | <1%, p<0.01 | PASS |
| Energy component drift | bond=0.2064%, angle=0.2594%, dihedral=0.2332%, vdw=2.6872%, coul=0.0538%, kspace=0.0036% | <1%, p<0.01 each | PASS |
| Density block-SEM | 0.0914% | <1% | PASS |
| Energy block-SEM | 0.0224% | <1% | PASS |
| τ_eff density | 1.2% of trajectory | — | OK |
| Independent density samples | 86 | ≥20 | PASS |
| Residual deviatoric stress | 25.2 atm von Mises (max |dev| 15.9 atm, z=0.45, not resolved (z<2)) | — | INFO |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 13.5% | <30% | PASS |
| MSID slope (combined) | 1.109 (R²=0.9667) | 1.0 ±20% | OK |
| MSID slope (large-s, n=[41, 120]) | 0.789 (R²=0.9871) | 1.0 ±20% | ⚠ non-Gaussian (large-s) |
| Torsion JS-divergence (last block-pair) | 0.0001 | ≤0.05 | OK (stable) |
| C(t) τ_relax | 1583197.4 ps (22% decayed) | — | ⚠ partial |
| MSD kinetic trap | no (α=0.296, MSD=1338.99 Å²>>Rg²=395.338) | — | OK |
| R_ee mean ± std | 45.17 ± 15.44 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.019 ± 0.0057 | <0.10 | PASS |
| Finite size | L=43.98 Å · L/2r_cut=2.315 · L/2Rg=1.117 · L/R_ee=0.974 | ≥1.0 | PASS |
| Density homogeneity CV (signal) | 0.0% (raw 21.4% − Poisson 23.4%; 6³ grid, 30.1 atoms/voxel) | <11% | PASS |

**Warnings:** C(t) partially decayed: 22% decayed at end of trajectory (τ_relax=1583197.4 ps vs T_traj=4951.0 ps)