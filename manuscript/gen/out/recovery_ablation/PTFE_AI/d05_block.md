## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=700.02 K · 1951 frames analysed (skip=50) · 2026-09-15 14:00

**Overall: PASS**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.4505% (p=0.173) | <1%, p<0.01 | PASS |
| Energy drift | 0.4852% (p=0.0011) | <1%, p<0.01 | PASS |
| Energy component drift | bond=0.0968%, angle=0.2273%, dihedral=0.4866%, vdw=1.7755%, coul=0.1233%, kspace=0.0334% | <1%, p<0.01 each | PASS |
| Density block-SEM | 0.386% | <1% | PASS |
| Energy block-SEM | 0.0883% | <1% | PASS |
| τ_eff density | 1.4% of trajectory | — | OK |
| Independent density samples | 73 | ≥20 | PASS |
| Residual deviatoric stress | 85.7 atm von Mises (max |dev| 54.3 atm, z=1.55, not resolved (z<2)) | — | INFO |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 15.3% | <30% | PASS |
| MSID slope (combined) | 1.517 (R²=0.9974) | 1.0 ±20% | ⚠ non-Gaussian |
| MSID slope (large-s, n=[18, 51]) | 1.359 (R²=0.9998) | 1.0 ±20% | ⚠ non-Gaussian (large-s) |
| Torsion JS-divergence (last block-pair) | 0.00027 | ≤0.05 | OK (stable) |
| C(t) τ_relax | 4004.2 ps (60% decayed) | — | ⚠ partial |
| MSD kinetic trap | no (α=0.263, MSD=1588.18 Å²>>Rg²=332.013) | — | OK |
| R_ee mean ± std | 46.27 ± 17.0 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0265 ± 0.0098 | <0.10 | PASS |
| Finite size | L=39.1 Å · L/2r_cut=n/a · L/2Rg=1.094 · L/R_ee=0.845 | ≥1.0 | PASS |
| Density homogeneity CV (signal, split_half) | 2.7% (structure shared by both halves of the hold, half-map r=0.263; 5³ grid, 24.2 atoms/voxel) | <11% | PASS |

**Warnings:** MSID slope = 1.517 (expected 1.0 ±20% for Gaussian chain) — possible chain collapse or extension; C(t) partially decayed: 60% decayed at end of trajectory (τ_relax=4004.2 ps vs T_traj=4951.0 ps)