## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=700.22 K · 1951 frames analysed (skip=50) · 2026-09-11 23:02

**Overall: PASS**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.2514% (p=0.0208) | <1%, p<0.01 | PASS |
| Energy drift | 0.1034% (p=0.149) | <1%, p<0.01 | PASS |
| Energy component drift | bond=0.3513%, angle=0.136%, dihedral=0.2642%, vdw=1.5508%, coul=0.0703%, kspace=0.0071% | <1%, p<0.01 each | PASS |
| Density block-SEM | 0.139% | <1% | PASS |
| Energy block-SEM | 0.0282% | <1% | PASS |
| τ_eff density | 1.5% of trajectory | — | OK |
| Independent density samples | 66 | ≥20 | PASS |
| Residual deviatoric stress | 198.8 atm von Mises (max |dev| 128.1 atm, z=3.57, resolved) | — | INFO |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 24.3% | <30% | PASS |
| MSID slope (combined) | 1.216 (R²=0.9864) | 1.0 ±20% | ⚠ non-Gaussian |
| MSID slope (large-s, n=[41, 120]) | 1.047 (R²=0.9956) | 1.0 ±20% | OK |
| Torsion JS-divergence (last block-pair) | 6e-05 | ≤0.05 | OK (stable) |
| C(t) τ_relax | 725124.0 ps (10% decayed) | — | ⚠ partial |
| MSD kinetic trap | no (α=0.315, MSD=1252.34 Å²>>Rg²=550.936) | — | OK |
| R_ee mean ± std | 58.78 ± 19.01 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0155 ± 0.0049 | <0.10 | PASS |
| Finite size | L=43.81 Å · L/2r_cut=2.306 · L/2Rg=0.961 · L/R_ee=0.745 | ≥1.0 | SIZE_CHAIN_SELF_IMAGE_ADVISORY |
| Density homogeneity CV (signal) | 0.0% (raw 21.4% − Poisson 23.4%; 6³ grid, 30.1 atoms/voxel) | <11% | PASS |

**Warnings:** MSID slope = 1.216 (expected 1.0 ±20% for Gaussian chain) — possible chain collapse or extension; C(t) partially decayed: 10% decayed at end of trajectory (τ_relax=725124.0 ps vs T_traj=4951.0 ps)