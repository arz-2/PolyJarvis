## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=300.22 K · 451 frames analysed (skip=50) · 2026-09-15 03:34

**Overall: PASS**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.4382% (p=0.0) | <1%, p<0.01 | PASS |
| Energy drift | 2.7714% (p=0.2355) | <1%, p<0.01 | PASS |
| Energy component drift | bond=0.3192%, angle=0.8553%, dihedral=0.6436%, vdw=1.3163%, coul=0.0449%, kspace=0.0381% | <1%, p<0.01 each | PASS |
| Density block-SEM | 0.0699% | <1% | PASS |
| Energy block-SEM | 0.9503% | <1% | PASS |
| τ_eff density | 2.8% of trajectory | — | OK |
| Independent density samples | 35 | ≥20 | PASS |
| Residual deviatoric stress | 179.4 atm von Mises (max |dev| 118.2 atm, z=2.41, resolved) | — | INFO |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 23.5% | <30% | PASS |
| MSID slope (combined) | 1.338 (R²=0.9887) | 1.0 ±20% | ⚠ non-Gaussian |
| MSID slope (large-s, n=[29, 82]) | 1.096 (R²=0.9999) | 1.0 ±20% | OK |
| Torsion JS-divergence (last block-pair) | 0.00015 | ≤0.05 | OK (stable) |
| C(t) τ_relax | 3089076240.5 ps (0% decayed) | — | ⚠ partial |
| MSD kinetic trap | yes (α=0.06, MSD=17.8 Å²>>Rg²=532.716) | — | ⚠ trapped |
| R_ee mean ± std | 58.84 ± 25.83 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0326 ± 0.0037 | <0.10 | PASS |
| Finite size | L=39.88 Å · L/2r_cut=2.099 · L/2Rg=0.887 · L/R_ee=0.678 | ≥1.0 | SIZE_CHAIN_SELF_IMAGE_ADVISORY |
| Density homogeneity CV (signal, measured_floor) | 0.0% (raw 19.3% − melt floor 24.2%; 6³ grid, 22.9 atoms/voxel) | <11% | PASS |

**Warnings:** MSID slope = 1.338 (expected 1.0 ±20% for Gaussian chain) — possible chain collapse or extension; C(t) partially decayed: 0% decayed at end of trajectory (τ_relax=3089076240.5 ps vs T_traj=451.0 ps); MSD kinetic trap: chains have not displaced their own size (MSD_max < Rg²) — expected below Tg, problematic in melt state