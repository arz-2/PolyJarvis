## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=769.57 K · 1951 frames analysed (skip=50) · 2026-09-12 16:15

**Overall: PASS**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.1103% (p=0.3106) | <1%, p<0.01 | PASS |
| Energy drift | 0.0428% (p=0.479) | <1%, p<0.01 | PASS |
| Energy component drift | bond=0.1465%, angle=0.0626%, dihedral=0.2927%, vdw=0.1141%, coul=0.0349%, kspace=0.0462% | <1%, p<0.01 each | PASS |
| Density block-SEM | 0.0803% | <1% | PASS |
| Energy block-SEM | 0.0177% | <1% | PASS |
| τ_eff density | 0.9% of trajectory | — | OK |
| Independent density samples | 117 | ≥20 | PASS |
| Residual deviatoric stress | 43.7 atm von Mises (max |dev| 26.1 atm, z=0.67, not resolved (z<2)) | — | INFO |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 16.6% | <30% | PASS |
| MSID slope (combined) | 1.229 (R²=0.9776) | 1.0 ±20% | ⚠ non-Gaussian |
| MSID slope (large-s, n=[46, 135]) | 0.886 (R²=0.9978) | 1.0 ±20% | OK |
| Torsion JS-divergence (last block-pair) | 7e-05 | ≤0.05 | OK (stable) |
| C(t) τ_relax | 89076.0 ps (9% decayed) | — | ⚠ partial |
| MSD kinetic trap | no (α=0.323, MSD=1324.32 Å²>>Rg²=712.919) | — | OK |
| R_ee mean ± std | 76.32 ± 18.8 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0264 ± 0.0088 | <0.10 | PASS |
| Finite size | L=43.58 Å · L/2r_cut=2.293 · L/2Rg=0.828 · L/R_ee=0.571 | ≥1.0 | SIZE_CHAIN_SELF_IMAGE_ADVISORY |
| Density homogeneity CV (signal) | 0.0% (raw 19.6% − Poisson 22.5%; 6³ grid, 28.4 atoms/voxel) | <11% | PASS |

**Warnings:** MSID slope = 1.229 (expected 1.0 ±20% for Gaussian chain) — possible chain collapse or extension; C(t) partially decayed: 9% decayed at end of trajectory (τ_relax=89076.0 ps vs T_traj=4951.0 ps)