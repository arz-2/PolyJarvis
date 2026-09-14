## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=300.01 K · 1951 frames analysed (skip=50) · 2026-09-13 00:38

**Overall: PASS**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.0931% (p=0.0428) | <1%, p<0.01 | PASS |
| Energy drift | 0.1161% (p=0.6413) | <1%, p<0.01 | PASS |
| Energy component drift | bond=0.2489%, angle=0.0708%, dihedral=0.044%, vdw=0.4627%, coul=0.2005%, kspace=0.0893% | <1%, p<0.01 each | PASS |
| Density block-SEM | 0.0469% | <1% | PASS |
| Energy block-SEM | 0.1287% | <1% | PASS |
| τ_eff density | 0.7% of trajectory | — | OK |
| Independent density samples | 151 | ≥20 | PASS |
| Residual deviatoric stress | 8.6 atm von Mises (max |dev| 5.1 atm, z=0.2, not resolved (z<2)) | — | INFO |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 15.8% | <30% | PASS |
| MSID slope (combined) | 1.007 (R²=0.9568) | 1.0 ±20% | OK |
| MSID slope (large-s, n=[51, 150]) | 0.799 (R²=0.9819) | 1.0 ±20% | ⚠ non-Gaussian (large-s) |
| Torsion JS-divergence (last block-pair) | 9e-05 | ≤0.05 | OK (stable) |
| C(t) τ_relax | 3299255872.0 ps (1% decayed) | — | ⚠ partial |
| MSD kinetic trap | yes (α=0.106, MSD=154.53 Å²>>Rg²=410.129) | — | ⚠ trapped |
| R_ee mean ± std | 44.0 ± 18.55 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0316 ± 0.0041 | <0.10 | PASS |
| Finite size | L=40.97 Å · L/2r_cut=2.156 · L/2Rg=1.024 · L/R_ee=0.931 | ≥1.0 | PASS |
| Density homogeneity CV (signal) | 0.0% (raw 21.7% − Poisson 31.1%; 7³ grid, 20.5 atoms/voxel) | <11% | PASS |

**Warnings:** C(t) partially decayed: 1% decayed at end of trajectory (τ_relax=3299255872.0 ps vs T_traj=1951.0 ps); MSD kinetic trap: chains have not displaced their own size (MSD_max < Rg²) — expected below Tg, problematic in melt state