## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=572.95 K · 5951 frames analysed (skip=50) · 2026-09-11 11:39

**Overall: PASS**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.0766% (p=0.1874) | <1%, p<0.01 | PASS |
| Energy drift | 0.1596% (p=0.0006) | <1%, p<0.01 | PASS |
| Energy component drift | bond=0.054%, angle=0.5013%, dihedral=0.3503%, vdw=0.7758%, coul=0.0296%, kspace=0.0718% | <1%, p<0.01 each | PASS |
| Density block-SEM | 0.0778% | <1% | PASS |
| Energy block-SEM | 0.0419% | <1% | PASS |
| τ_eff density | 0.6% of trajectory | — | OK |
| Independent density samples | 157 | ≥20 | PASS |
| Residual deviatoric stress | 58.5 atm von Mises (max |dev| 37.4 atm, z=2.18, resolved) | — | INFO |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 9.2% | <30% | PASS |
| MSID slope (combined) | 1.334 (R²=0.9848) | 1.0 ±20% | ⚠ non-Gaussian |
| MSID slope (large-s, n=[19, 52]) | 0.966 (R²=0.995) | 1.0 ±20% | OK |
| Torsion JS-divergence (last block-pair) | 0.00022 | ≤0.05 | OK (stable) |
| C(t) τ_relax | 294192.2 ps (17% decayed) | — | ⚠ partial |
| MSD kinetic trap | no (α=0.26, MSD=1197.93 Å²>>Rg²=229.597) | — | OK |
| R_ee mean ± std | 34.32 ± 12.97 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0241 ± 0.0084 | <0.10 | PASS |
| Finite size | L=45.56 Å · L/2r_cut=2.398 · L/2Rg=1.512 · L/R_ee=1.327 | ≥1.0 | PASS |
| Density homogeneity CV (signal) | 7.1% (raw 28.3% − Poisson 27.4%; 7³ grid, 22.9 atoms/voxel) | <11% | PASS |

**Warnings:** MSID slope = 1.334 (expected 1.0 ±20% for Gaussian chain) — possible chain collapse or extension; C(t) partially decayed: 17% decayed at end of trajectory (τ_relax=294192.2 ps vs T_traj=4951.0 ps)