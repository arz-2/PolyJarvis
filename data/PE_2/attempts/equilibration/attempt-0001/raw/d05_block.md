## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=549.94 K · 951 frames analysed (skip=50) · 2026-09-13 10:14

**Overall: PASS**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.695% (p=0.0002) | <1%, p<0.01 | PASS |
| Energy drift | 0.1397% (p=0.4738) | <1%, p<0.01 | PASS |
| Energy component drift | bond=1.3148%✗, angle=0.0013%, dihedral=0.2186%, vdw=0.9068%, coul=0.0%, kspace=0.0% | <1%, p<0.01 each | FAIL |
| Density block-SEM | 0.1186% | <1% | PASS |
| Energy block-SEM | 0.0545% | <1% | PASS |
| τ_eff density | 0.5% of trajectory | — | OK |
| Independent density samples | 214 | ≥20 | PASS |
| Residual deviatoric stress | 44.4 atm von Mises (max |dev| 27.4 atm, z=1.36, not resolved (z<2)) | — | INFO |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 17.8% | <30% | PASS |
| MSID slope (combined) | 1.104 (R²=0.9973) | 1.0 ±20% | OK |
| MSID slope (large-s, n=[61, 180]) | 1.055 (R²=0.9992) | 1.0 ±20% | OK |
| Torsion JS-divergence (last block-pair) | 4e-05 | ≤0.05 | OK (stable) |
| C(t) τ_relax | 207467.1 ps (24% decayed) | — | ⚠ partial |
| MSD kinetic trap | no (α=0.271, MSD=2394.11 Å²>>Rg²=975.571) | — | OK |
| R_ee mean ± std | 72.68 ± 18.74 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0181 ± 0.0058 | <0.10 | PASS |
| Finite size | L=49.14 Å · L/2r_cut=1.755 · L/2Rg=0.801 · L/R_ee=0.676 | ≥1.0 | SIZE_CHAIN_SELF_IMAGE_ADVISORY |
| Density homogeneity CV (signal) | 0.0% (raw 14.7% − Poisson 18.6%; 5³ grid, 28.8 atoms/voxel) | <11% | PASS |

**Warnings:** C(t) partially decayed: 24% decayed at end of trajectory (τ_relax=207467.1 ps vs T_traj=4902.0 ps)