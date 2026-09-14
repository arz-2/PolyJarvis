## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=770.1 K · 1951 frames analysed (skip=50) · 2026-09-11 22:53

**Overall: PASS**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.453% (p=0.0001) | <1%, p<0.01 | PASS |
| Energy drift | 0.0102% (p=0.8773) | <1%, p<0.01 | PASS |
| Energy component drift | bond=0.2146%, angle=0.4482%, dihedral=0.0124%, vdw=11.4479%, coul=0.0336%, kspace=0.0484% | <1%, p<0.01 each | PASS |
| Density block-SEM | 0.1364% | <1% | PASS |
| Energy block-SEM | 0.0248% | <1% | PASS |
| τ_eff density | 1.9% of trajectory | — | OK |
| Independent density samples | 52 | ≥20 | PASS |
| Residual deviatoric stress | 71.4 atm von Mises (max |dev| 46.9 atm, z=1.22, not resolved (z<2)) | — | INFO |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 19.1% | <30% | PASS |
| MSID slope (combined) | 1.278 (R²=0.9847) | 1.0 ±20% | ⚠ non-Gaussian |
| MSID slope (large-s, n=[46, 135]) | 0.995 (R²=0.9991) | 1.0 ±20% | OK |
| Torsion JS-divergence (last block-pair) | 4e-05 | ≤0.05 | OK (stable) |
| C(t) τ_relax | 281825.6 ps (14% decayed) | — | ⚠ partial |
| MSD kinetic trap | no (α=0.308, MSD=1396.76 Å²>>Rg²=716.002) | — | OK |
| R_ee mean ± std | 64.94 ± 24.92 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0288 ± 0.0086 | <0.10 | PASS |
| Finite size | L=43.87 Å · L/2r_cut=2.309 · L/2Rg=0.835 · L/R_ee=0.676 | ≥1.0 | SIZE_CHAIN_SELF_IMAGE_ADVISORY |
| Density homogeneity CV (signal) | 0.0% (raw 19.5% − Poisson 22.5%; 6³ grid, 28.4 atoms/voxel) | <11% | PASS |

**Warnings:** MSID slope = 1.278 (expected 1.0 ±20% for Gaussian chain) — possible chain collapse or extension; C(t) partially decayed: 14% decayed at end of trajectory (τ_relax=281825.6 ps vs T_traj=4951.0 ps)