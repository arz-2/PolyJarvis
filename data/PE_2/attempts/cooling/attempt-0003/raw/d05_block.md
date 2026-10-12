## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=300.15 K · 2451 frames analysed (skip=50) · 2026-09-13 19:16

**Overall: FAIL**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.0317% (p=0.548) | <1%, p<0.01 | PASS |
| Energy drift | 1.3641% (p=0.0) | <1%, p<0.01 | FAIL |
| Energy component drift | bond=0.9915%, angle=0.0745%, dihedral=1.4303%✗, vdw=0.0889%, coul=0.0%, kspace=0.0% | <1%, p<0.01 each | FAIL |
| Density block-SEM | 0.042% | <1% | PASS |
| Energy block-SEM | 0.2425% | <1% | PASS |
| τ_eff density | 0.7% of trajectory | — | OK |
| Independent density samples | 148 | ≥20 | PASS |
| Residual deviatoric stress | 3.6 atm von Mises (max |dev| 2.4 atm, z=0.22, not resolved (z<2)) | — | INFO |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 15.6% | <30% | PASS |
| MSID slope (combined) | 1.115 (R²=0.9951) | 1.0 ±20% | OK |
| MSID slope (large-s, n=[61, 180]) | 1.025 (R²=0.9985) | 1.0 ±20% | OK |
| Torsion JS-divergence (last block-pair) | 3e-05 | ≤0.05 | OK (stable) |
| C(t) τ_relax | 97743.3 ps (2% decayed) | — | ⚠ partial |
| MSD kinetic trap | yes (α=0.319, MSD=664.12 Å²>>Rg²=1122.186) | — | ⚠ trapped |
| R_ee mean ± std | 71.01 ± 11.1 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0278 ± 0.0049 | <0.10 | PASS |
| Finite size | L=45.99 Å · L/2r_cut=1.643 · L/2Rg=0.695 · L/R_ee=0.648 | ≥1.0 | SIZE_CHAIN_SELF_IMAGE_ADVISORY |
| Density homogeneity CV (signal) | 0.0% (raw 10.7% − Poisson 18.6%; 5³ grid, 28.8 atoms/voxel) | <11% | PASS |

**Warnings:** C(t) partially decayed: 2% decayed at end of trajectory (τ_relax=97743.3 ps vs T_traj=4902.0 ps); MSD kinetic trap: chains have not displaced their own size (MSD_max < Rg²) — expected below Tg, problematic in melt state