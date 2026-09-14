## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=299.86 K · 451 frames analysed (skip=50) · 2026-09-12 02:05

**Overall: PASS**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.3913% (p=0.0) | <1%, p<0.01 | PASS |
| Energy drift | 0.048% (p=0.7126) | <1%, p<0.01 | PASS |
| Energy component drift | bond=0.2331%, angle=0.5895%, dihedral=0.0179%, vdw=6.909%, coul=0.0856%, kspace=0.0088% | <1%, p<0.01 each | PASS |
| Density block-SEM | 0.051% | <1% | PASS |
| Energy block-SEM | 0.0423% | <1% | PASS |
| τ_eff density | 1.7% of trajectory | — | OK |
| Independent density samples | 57 | ≥20 | PASS |
| Residual deviatoric stress | 427.6 atm von Mises (max |dev| 247.4 atm, z=4.79, resolved) | — | INFO |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 23.0% | <30% | PASS |
| MSID slope (combined) | 1.2 (R²=0.9849) | 1.0 ±20% | ⚠ non-Gaussian |
| MSID slope (large-s, n=[41, 120]) | 0.986 (R²=0.9991) | 1.0 ±20% | OK |
| Torsion JS-divergence (last block-pair) | 0.0001 | ≤0.05 | OK (stable) |
| C(t) τ_relax | 2354484664.7 ps (0% decayed) | — | ⚠ partial |
| MSD kinetic trap | yes (α=-0.013, MSD=27.25 Å²>>Rg²=521.793) | — | ⚠ trapped |
| R_ee mean ± std | 55.62 ± 17.53 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0095 ± 0.0021 | <0.10 | PASS |
| Finite size | L=42.22 Å · L/2r_cut=2.222 · L/2Rg=0.948 · L/R_ee=0.759 | ≥1.0 | SIZE_CHAIN_SELF_IMAGE_ADVISORY |
| Density homogeneity CV (signal) | 0.0% (raw 18.3% − Poisson 23.4%; 6³ grid, 30.1 atoms/voxel) | <11% | PASS |

**Warnings:** MSID slope = 1.2 (expected 1.0 ±20% for Gaussian chain) — possible chain collapse or extension; C(t) partially decayed: 0% decayed at end of trajectory (τ_relax=2354484664.7 ps vs T_traj=451.0 ps); MSD kinetic trap: chains have not displaced their own size (MSD_max < Rg²) — expected below Tg, problematic in melt state