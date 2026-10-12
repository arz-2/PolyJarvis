## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=300.01 K · 451 frames analysed (skip=50) · 2026-09-12 19:27

**Overall: PASS**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.0269% (p=0.7043) | <1%, p<0.01 | PASS |
| Energy drift | 0.0316% (p=0.7365) | <1%, p<0.01 | PASS |
| Energy component drift | bond=0.1154%, angle=0.2304%, dihedral=0.3169%, vdw=0.845%, coul=0.0201%, kspace=0.0036% | <1%, p<0.01 each | PASS |
| Density block-SEM | 0.0218% | <1% | PASS |
| Energy block-SEM | 0.0287% | <1% | PASS |
| τ_eff density | 0.7% of trajectory | — | OK |
| Independent density samples | 146 | ≥20 | PASS |
| Residual deviatoric stress | 104.6 atm von Mises (max |dev| 66.4 atm, z=1.15, not resolved (z<2)) | — | INFO |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 18.7% | <30% | PASS |
| MSID slope (combined) | 1.218 (R²=0.9832) | 1.0 ±20% | ⚠ non-Gaussian |
| MSID slope (large-s, n=[46, 135]) | 1.017 (R²=0.999) | 1.0 ±20% | OK |
| Torsion JS-divergence (last block-pair) | 0.0001 | ≤0.05 | OK (stable) |
| C(t) τ_relax | 1955345944.5 ps (0% decayed) | — | ⚠ partial |
| MSD kinetic trap | yes (α=-0.007, MSD=50.63 Å²>>Rg²=665.789) | — | ⚠ trapped |
| R_ee mean ± std | 67.85 ± 25.25 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0153 ± 0.002 | <0.10 | PASS |
| Finite size | L=41.59 Å · L/2r_cut=2.189 · L/2Rg=0.82 · L/R_ee=0.613 | ≥1.0 | SIZE_CHAIN_SELF_IMAGE_ADVISORY |
| Density homogeneity CV (signal) | 0.0% (raw 16.2% − Poisson 22.5%; 6³ grid, 28.4 atoms/voxel) | <11% | PASS |

**Warnings:** MSID slope = 1.218 (expected 1.0 ±20% for Gaussian chain) — possible chain collapse or extension; C(t) partially decayed: 0% decayed at end of trajectory (τ_relax=1955345944.5 ps vs T_traj=451.0 ps); MSD kinetic trap: chains have not displaced their own size (MSD_max < Rg²) — expected below Tg, problematic in melt state