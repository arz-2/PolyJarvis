## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=770.07 K · 1951 frames analysed (skip=50) · 2026-09-13 01:08

**Overall: PASS**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.0706% (p=0.5395) | <1%, p<0.01 | PASS |
| Energy drift | 0.0085% (p=0.8929) | <1%, p<0.01 | PASS |
| Energy component drift | bond=0.3661%, angle=0.3543%, dihedral=0.193%, vdw=3.26%, coul=0.0179%, kspace=0.0058% | <1%, p<0.01 each | PASS |
| Density block-SEM | 0.1737% | <1% | PASS |
| Energy block-SEM | 0.026% | <1% | PASS |
| τ_eff density | 4.2% of trajectory | — | OK |
| Independent density samples | 23 | ≥20 | PASS |
| Residual deviatoric stress | 71.4 atm von Mises (max |dev| 47.5 atm, z=1.22, not resolved (z<2)) | — | INFO |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 19.5% | <30% | PASS |
| MSID slope (combined) | 1.301 (R²=0.9882) | 1.0 ±20% | ⚠ non-Gaussian |
| MSID slope (large-s, n=[46, 135]) | 1.069 (R²=0.9992) | 1.0 ±20% | OK |
| Torsion JS-divergence (last block-pair) | 8e-05 | ≤0.05 | OK (stable) |
| C(t) τ_relax | 123213.9 ps (20% decayed) | — | ⚠ partial |
| MSD kinetic trap | no (α=0.293, MSD=1096.21 Å²>>Rg²=738.615) | — | OK |
| R_ee mean ± std | 65.97 ± 26.54 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0362 ± 0.0081 | <0.10 | PASS |
| Finite size | L=43.57 Å · L/2r_cut=2.293 · L/2Rg=0.817 · L/R_ee=0.66 | ≥1.0 | SIZE_CHAIN_SELF_IMAGE_ADVISORY |
| Density homogeneity CV (signal) | 0.0% (raw 19.4% − Poisson 22.5%; 6³ grid, 28.4 atoms/voxel) | <11% | PASS |

**Warnings:** MSID slope = 1.301 (expected 1.0 ±20% for Gaussian chain) — possible chain collapse or extension; C(t) partially decayed: 20% decayed at end of trajectory (τ_relax=123213.9 ps vs T_traj=4951.0 ps)