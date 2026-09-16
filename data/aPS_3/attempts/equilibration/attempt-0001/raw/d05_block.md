## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=572.81 K · 5951 frames analysed (skip=50) · 2026-09-12 18:26

**Overall: PASS**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.1129% (p=0.0407) | <1%, p<0.01 | PASS |
| Energy drift | 0.2607% (p=0.0) | <1%, p<0.01 | PASS |
| Energy component drift | bond=0.1273%, angle=0.6215%, dihedral=1.6412%✗, vdw=0.6359%, coul=0.0546%, kspace=0.0201% | <1%, p<0.01 each | FAIL |
| Density block-SEM | 0.06% | <1% | PASS |
| Energy block-SEM | 0.0356% | <1% | PASS |
| τ_eff density | 0.3% of trajectory | — | OK |
| Independent density samples | 304 | ≥20 | PASS |
| Residual deviatoric stress | 65.5 atm von Mises (max |dev| 38.0 atm, z=2.21, resolved) | — | INFO |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 10.2% | <30% | PASS |
| MSID slope (combined) | 1.308 (R²=0.984) | 1.0 ±20% | ⚠ non-Gaussian |
| MSID slope (large-s, n=[19, 52]) | 0.947 (R²=0.9932) | 1.0 ±20% | OK |
| Torsion JS-divergence (last block-pair) | 0.00015 | ≤0.05 | OK (stable) |
| C(t) τ_relax | 132759.8 ps (18% decayed) | — | ⚠ partial |
| MSD kinetic trap | no (α=0.302, MSD=891.41 Å²>>Rg²=216.148) | — | OK |
| R_ee mean ± std | 29.78 ± 13.39 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0304 ± 0.0097 | <0.10 | PASS |
| Finite size | L=45.82 Å · L/2r_cut=2.411 · L/2Rg=1.569 · L/R_ee=1.538 | ≥1.0 | PASS |
| Density homogeneity CV (signal) | 6.9% (raw 28.2% − Poisson 27.4%; 7³ grid, 22.9 atoms/voxel) | <11% | PASS |

**Warnings:** MSID slope = 1.308 (expected 1.0 ±20% for Gaussian chain) — possible chain collapse or extension; C(t) partially decayed: 18% decayed at end of trajectory (τ_relax=132759.8 ps vs T_traj=4951.0 ps)