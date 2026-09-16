## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=299.98 K · 451 frames analysed (skip=50) · 2026-09-12 04:03

**Overall: PASS**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.1345% (p=0.1696) | <1%, p<0.01 | PASS |
| Energy drift | 1.7762% (p=0.4862) | <1%, p<0.01 | PASS |
| Energy component drift | bond=0.0678%, angle=0.4838%, dihedral=0.0855%, vdw=0.6531%, coul=0.0456%, kspace=0.0153% | <1%, p<0.01 each | PASS |
| Density block-SEM | 0.0395% | <1% | PASS |
| Energy block-SEM | 0.653% | <1% | PASS |
| τ_eff density | 0.5% of trajectory | — | OK |
| Independent density samples | 184 | ≥20 | PASS |
| Residual deviatoric stress | 19.0 atm von Mises (max |dev| 11.0 atm, z=0.23, not resolved (z<2)) | — | INFO |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 20.0% | <30% | PASS |
| MSID slope (combined) | 1.326 (R²=0.9898) | 1.0 ±20% | ⚠ non-Gaussian |
| MSID slope (large-s, n=[29, 82]) | 1.123 (R²=0.9999) | 1.0 ±20% | OK |
| Torsion JS-divergence (last block-pair) | 0.00016 | ≤0.05 | OK (stable) |
| C(t) τ_relax | 3190755297.9 ps (0% decayed) | — | ⚠ partial |
| MSD kinetic trap | yes (α=0.097, MSD=199.18 Å²>>Rg²=455.3) | — | ⚠ trapped |
| R_ee mean ± std | 49.68 ± 14.75 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0269 ± 0.0034 | <0.10 | PASS |
| Finite size | L=39.74 Å · L/2r_cut=2.092 · L/2Rg=0.95 · L/R_ee=0.8 | ≥1.0 | SIZE_CHAIN_SELF_IMAGE_ADVISORY |
| Density homogeneity CV (signal) | 0.0% (raw 18.8% − Poisson 32.3%; 6³ grid, 22.9 atoms/voxel) | <11% | PASS |

**Warnings:** MSID slope = 1.326 (expected 1.0 ±20% for Gaussian chain) — possible chain collapse or extension; C(t) partially decayed: 0% decayed at end of trajectory (τ_relax=3190755297.9 ps vs T_traj=451.0 ps); MSD kinetic trap: chains have not displaced their own size (MSD_max < Rg²) — expected below Tg, problematic in melt state