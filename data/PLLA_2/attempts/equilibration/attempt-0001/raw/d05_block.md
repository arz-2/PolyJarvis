## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=620.14 K · 1951 frames analysed (skip=50) · 2026-09-11 02:03

**Overall: PASS**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.2087% (p=0.0156) | <1%, p<0.01 | PASS |
| Energy drift | 0.0992% (p=0.0642) | <1%, p<0.01 | PASS |
| Energy component drift | bond=0.4332%, angle=0.2067%, dihedral=1.2475%, vdw=0.4756%, coul=0.0159%, kspace=0.0004% | <1%, p<0.01 each | PASS |
| Density block-SEM | 0.0808% | <1% | PASS |
| Energy block-SEM | 0.035% | <1% | PASS |
| τ_eff density | 0.8% of trajectory | — | OK |
| Independent density samples | 131 | ≥20 | PASS |
| Residual deviatoric stress | 94.9 atm von Mises (max |dev| 61.9 atm, z=1.79, not resolved (z<2)) | — | INFO |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 20.0% | <30% | PASS |
| MSID slope (combined) | 1.124 (R²=0.992) | 1.0 ±20% | OK |
| MSID slope (large-s, n=[36, 105]) | 1.027 (R²=0.9994) | 1.0 ±20% | OK |
| Torsion JS-divergence (last block-pair) | 0.00013 | ≤0.05 | OK (stable) |
| C(t) τ_relax | 87543.6 ps (20% decayed) | — | ⚠ partial |
| MSD kinetic trap | no (α=0.345, MSD=917.63 Å²>>Rg²=296.801) | — | OK |
| R_ee mean ± std | 39.84 ± 19.91 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0146 ± 0.0055 | <0.10 | PASS |
| Finite size | L=42.24 Å · L/2r_cut=2.223 · L/2Rg=1.251 · L/R_ee=1.06 | ≥1.0 | PASS |
| Density homogeneity CV (signal) | 0.0% (raw 20.0% − Poisson 23.7%; 6³ grid, 29.3 atoms/voxel) | <11% | PASS |

**Warnings:** C(t) partially decayed: 20% decayed at end of trajectory (τ_relax=87543.6 ps vs T_traj=4951.0 ps)