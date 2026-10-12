## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=570.82 K · 3951 frames analysed (skip=50) · 2026-09-12 01:12

**Overall: PASS**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.2588% (p=0.0012) | <1%, p<0.01 | PASS |
| Energy drift | 0.3047% (p=0.0231) | <1%, p<0.01 | PASS |
| Energy component drift | bond=0.071%, angle=0.1911%, dihedral=0.1909%, vdw=4.8297%, coul=0.2335%, kspace=0.0592% | <1%, p<0.01 each | PASS |
| Density block-SEM | 0.0473% | <1% | PASS |
| Energy block-SEM | 0.0482% | <1% | PASS |
| τ_eff density | 0.3% of trajectory | — | OK |
| Independent density samples | 377 | ≥20 | PASS |
| Residual deviatoric stress | 29.5 atm von Mises (max |dev| 19.0 atm, z=0.93, not resolved (z<2)) | — | INFO |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 21.2% | <30% | PASS |
| MSID slope (combined) | 1.328 (R²=0.9879) | 1.0 ±20% | ⚠ non-Gaussian |
| MSID slope (large-s, n=[29, 82]) | 1.05 (R²=0.9982) | 1.0 ±20% | OK |
| Torsion JS-divergence (last block-pair) | 7e-05 | ≤0.05 | OK (stable) |
| C(t) τ_relax | 10397.9 ps (39% decayed) | — | ⚠ partial |
| MSD kinetic trap | no (α=0.355, MSD=1507.83 Å²>>Rg²=415.018) | — | OK |
| R_ee mean ± std | 35.28 ± 16.31 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0255 ± 0.0085 | <0.10 | PASS |
| Finite size | L=41.97 Å · L/2r_cut=2.209 · L/2Rg=1.058 · L/R_ee=1.19 | ≥1.0 | PASS |
| Density homogeneity CV (signal) | 0.0% (raw 22.0% − Poisson 32.3%; 6³ grid, 22.9 atoms/voxel) | <11% | PASS |

**Warnings:** MSID slope = 1.328 (expected 1.0 ±20% for Gaussian chain) — possible chain collapse or extension; C(t) partially decayed: 39% decayed at end of trajectory (τ_relax=10397.9 ps vs T_traj=4951.0 ps)