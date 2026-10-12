## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=299.41 K · 201 frames analysed (skip=50) · 2026-09-13 18:24

**Overall: FAIL**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.4648% (p=0.0024) | <1%, p<0.01 | PASS |
| Energy drift | 2.4614% (p=0.0003) | <1%, p<0.01 | FAIL |
| Energy component drift | bond=0.5577%, angle=1.3749%, dihedral=2.026%✗, vdw=0.7828%✗, coul=0.0%, kspace=0.0% | <1%, p<0.01 each | FAIL |
| Density block-SEM | 0.1082% | <1% | PASS |
| Energy block-SEM | 0.3165% | <1% | PASS |
| τ_eff density | 6.4% of trajectory | — | OK |
| Independent density samples | 15 | ≥20 | FAIL |
| Residual deviatoric stress | 57.2 atm von Mises (max |dev| 37.6 atm, z=1.1, not resolved (z<2)) | — | INFO |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 21.2% | <30% | PASS |
| MSID slope (combined) | 1.145 (R²=0.9973) | 1.0 ±20% | OK |
| MSID slope (large-s, n=[61, 180]) | 1.074 (R²=0.9995) | 1.0 ±20% | OK |
| Torsion JS-divergence (last block-pair) | 0.00016 | ≤0.05 | OK (stable) |
| C(t) τ_relax | 755462671.2 ps (0% decayed) | — | ⚠ partial |
| MSD kinetic trap | yes (α=0.304, MSD=374.07 Å²>>Rg²=1298.154) | — | ⚠ trapped |
| R_ee mean ± std | 81.92 ± 21.34 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.064 ± 0.005 | <0.10 | PASS |
| Finite size | L=45.81 Å · L/2r_cut=1.636 · L/2Rg=0.65 · L/R_ee=0.559 | ≥1.0 | SIZE_CHAIN_SELF_IMAGE_ADVISORY |
| Density homogeneity CV (signal) | 0.0% (raw 10.6% − Poisson 18.6%; 5³ grid, 28.8 atoms/voxel) | <11% | PASS |

**Warnings:** C(t) partially decayed: 0% decayed at end of trajectory (τ_relax=755462671.2 ps vs T_traj=402.0 ps); MSD kinetic trap: chains have not displaced their own size (MSD_max < Rg²) — expected below Tg, problematic in melt state