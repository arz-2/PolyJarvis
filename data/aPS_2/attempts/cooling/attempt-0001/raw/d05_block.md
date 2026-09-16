## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=300.04 K · 451 frames analysed (skip=50) · 2026-09-11 16:11

**Overall: PASS**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.0007% (p=0.9945) | <1%, p<0.01 | PASS |
| Energy drift | 0.0282% (p=0.8708) | <1%, p<0.01 | PASS |
| Energy component drift | bond=0.0924%, angle=0.9675%, dihedral=0.4186%, vdw=6.4383%, coul=0.0628%, kspace=0.0513% | <1%, p<0.01 each | PASS |
| Density block-SEM | 0.0437% | <1% | PASS |
| Energy block-SEM | 0.0457% | <1% | PASS |
| τ_eff density | 1.8% of trajectory | — | OK |
| Independent density samples | 54 | ≥20 | PASS |
| Residual deviatoric stress | 229.3 atm von Mises (max |dev| 144.9 atm, z=2.98, resolved) | — | INFO |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 13.6% | <30% | PASS |
| MSID slope (combined) | 1.337 (R²=0.9872) | 1.0 ±20% | ⚠ non-Gaussian |
| MSID slope (large-s, n=[19, 52]) | 1.002 (R²=0.989) | 1.0 ±20% | OK |
| Torsion JS-divergence (last block-pair) | 0.00022 | ≤0.05 | OK (stable) |
| C(t) τ_relax | 4094409516.0 ps (0% decayed) | — | ⚠ partial |
| MSD kinetic trap | yes (α=0.03, MSD=43.15 Å²>>Rg²=222.38) | — | ⚠ trapped |
| R_ee mean ± std | 31.43 ± 11.85 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0266 ± 0.0031 | <0.10 | PASS |
| Finite size | L=44.05 Å · L/2r_cut=2.318 · L/2Rg=1.49 · L/R_ee=1.401 | ≥1.0 | PASS |
| Density homogeneity CV (signal) | 0.0% (raw 23.8% − Poisson 27.4%; 7³ grid, 22.9 atoms/voxel) | <11% | PASS |

**Warnings:** MSID slope = 1.337 (expected 1.0 ±20% for Gaussian chain) — possible chain collapse or extension; C(t) partially decayed: 0% decayed at end of trajectory (τ_relax=4094409516.0 ps vs T_traj=451.0 ps); MSD kinetic trap: chains have not displaced their own size (MSD_max < Rg²) — expected below Tg, problematic in melt state